import { describe, expect, it, vi } from 'vitest'
import { createQueryManager, keyMatches } from './query'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const flush = () => new Promise((r) => setTimeout(r, 0))

describe('keyMatches', () => {
  it('matches by prefix', () => {
    expect(keyMatches(['template'], ['template', 'abc'])).toBe(true)
    expect(keyMatches(['template', 'abc'], ['template'])).toBe(false)
    expect(keyMatches(['template'], ['templates'])).toBe(false)
  })
})

describe('createQueryManager', () => {
  it('fetches, stores, and serves data for a key', async () => {
    const manager = createQueryManager()
    const gate = deferred<string[]>()
    const fetcher = vi.fn(() => gate.promise)

    manager.start(['templates'], fetcher)
    expect(manager.getStatus(['templates'])).toBe('loading')
    gate.resolve(['a'])
    await flush()

    expect(manager.getStatus(['templates'])).toBe('success')
    expect(manager.getData(['templates'])).toEqual(['a'])
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('serves fresh data without refetching (stale time)', async () => {
    const manager = createQueryManager(30_000)
    const fetcher = vi.fn(async () => 'value')

    manager.start(['templates'], fetcher)
    await flush()
    manager.start(['templates'], fetcher)
    await flush()

    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('refetches stale data and can be forced', async () => {
    const manager = createQueryManager(0)
    const fetcher = vi.fn(async () => 'value')

    manager.start(['templates'], fetcher)
    await flush()
    manager.start(['templates'], fetcher)
    await flush()
    expect(fetcher).toHaveBeenCalledTimes(2)

    manager.start(['templates'], fetcher, { force: true })
    await flush()
    expect(fetcher).toHaveBeenCalledTimes(3)
  })

  it('records a normalized error on failure and keeps it queryable', async () => {
    const manager = createQueryManager()
    manager.start(['template', 'x'], async () => {
      throw new TypeError('Failed to fetch')
    })
    await flush()

    expect(manager.getStatus(['template', 'x'])).toBe('error')
    const error = manager.getError(['template', 'x']) as { code: string }
    expect(error.code).toBe('NETWORK_ERROR')
  })

  it('shares a single in-flight request per key', async () => {
    const manager = createQueryManager()
    const gate = deferred<string>()
    const fetcher = vi.fn(() => gate.promise)

    manager.start(['templates'], fetcher)
    manager.start(['templates'], fetcher)
    gate.resolve('once')
    await flush()

    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('update() applies a confirmed value and marks it fresh', async () => {
    const manager = createQueryManager()
    manager.update(['template', '1'], () => ({ name: 'before' }))
    manager.update(['template', '1'], (current) => ({ name: `${(current as { name: string }).name}!` }))

    expect(manager.getData(['template', '1'])).toEqual({ name: 'before!' })
    expect(manager.getStatus(['template', '1'])).toBe('success')
  })

  it('invalidate() drops matching entries and leaves others alone', async () => {
    const manager = createQueryManager()
    manager.update(['templates'], () => ['a'])
    manager.update(['template', '1'], () => 'one')

    manager.invalidate([['templates']])

    expect(manager.getStatus(['templates'])).toBe('idle')
    expect(manager.getData(['template', '1'])).toBe('one')
  })

  it('refresh() keeps data but marks it stale', async () => {
    const manager = createQueryManager(30_000)
    manager.update(['template', '1'], () => 'one')

    manager.refresh([['template', '1']])

    expect(manager.getData(['template', '1'])).toBe('one')
    const fetcher = vi.fn(async () => 'one')
    manager.start(['template', '1'], fetcher)
    await flush()
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('clearAll() removes everything (logout safety)', () => {
    const manager = createQueryManager()
    manager.update(['templates'], () => ['a'])
    manager.update(['template', '1'], () => 'one')

    manager.clearAll()

    expect(manager.getStatus(['templates'])).toBe('idle')
    expect(manager.getStatus(['template', '1'])).toBe('idle')
  })

  it('notifies subscribers when data changes', async () => {
    const manager = createQueryManager()
    const listener = vi.fn()
    const unsubscribe = manager.subscribe(listener)

    manager.update(['templates'], () => ['a'])
    expect(listener).toHaveBeenCalled()

    unsubscribe()
    listener.mockClear()
    manager.update(['templates'], () => ['b'])
    expect(listener).not.toHaveBeenCalled()
  })
})
