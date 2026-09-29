/**
 * Minimal server-state cache + hooks (FRONTEND_DESIGN §16).
 *
 * A single process-wide store keyed by query key ('templates', 'template/<id>',
 * 'import-issues/<id>'). Hooks expose { data, isLoading, error, refetch };
 * mutations invalidate/refresh keys and can apply a confirmed value first (design: apply
 * then refetch — PATCH is 204, so the backend stays the only truth). The entire cache is
 * cleared on logout so no data crosses users.
 *
 * Dependency-free on purpose (D1); TanStack Query would drop in behind this interface.
 */

/* eslint-disable react/only-export-components -- this module intentionally exports the
   QueryProvider component together with its hooks; the fast-refresh advisory does not apply. */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react'
import type { ReactNode } from 'react'
import { normalizeError } from './errors'

export type QueryKey = readonly unknown[]

export type QueryStatus = 'idle' | 'loading' | 'success' | 'error'

export interface QueryResult<T> {
  data: T | undefined
  status: QueryStatus
  isLoading: boolean
  error: unknown
  refetch: (force?: boolean) => void
}

export interface MutationResult<TArgs, TResult> {
  run: (args: TArgs) => Promise<TResult>
  isPending: boolean
  error: unknown
}

type CacheEntry<T> = {
  data: T | undefined
  status: QueryStatus
  error: unknown
  fetchedAt: number
  pending: Promise<void> | null
}

const DEFAULT_STALE_MS = 30_000

export function keyString(key: QueryKey): string {
  return JSON.stringify(key)
}

export function keyMatches(pattern: QueryKey, key: QueryKey): boolean {
  if (pattern.length > key.length) return false
  for (let i = 0; i < pattern.length; i++) {
    if (!Object.is(pattern[i], key[i])) return false
  }
  return true
}

export interface QueryManager {
  getStatus(key: QueryKey): QueryStatus
  getData<T>(key: QueryKey): T | undefined
  getError(key: QueryKey): unknown
  start(key: QueryKey, fetcher: () => Promise<unknown>, options?: { force?: boolean; staleMs?: number }): void
  update<T>(key: QueryKey, updater: (current: T | undefined) => T): void
  invalidate(patterns: QueryKey[]): void
  refresh(patterns: QueryKey[]): void
  clearAll(): void
  subscribe(listener: () => void): () => void
  getVersion(): number
}

export function createQueryManager(staleMs = DEFAULT_STALE_MS): QueryManager {
  const entries = new Map<string, CacheEntry<unknown>>()
  let version = 0
  const listeners = new Set<() => void>()

  function notify(): void {
    version++
    for (const listener of listeners) listener()
  }

  function entry(key: QueryKey): CacheEntry<unknown> {
    const k = keyString(key)
    let existing = entries.get(k)
    if (!existing) {
      existing = { data: undefined, status: 'idle', error: undefined, fetchedAt: 0, pending: null }
      entries.set(k, existing)
    }
    return existing
  }

  function runFetch(key: QueryKey, fetcher: () => Promise<unknown>): void {
    const current = entry(key)
    if (current.pending) return
    const promise = (async () => {
      try {
        const data = await fetcher()
        signalSuccess(key, data)
      } catch (error) {
        signalError(key, error)
      }
    })()
    current.pending = promise
    current.status = 'loading'
    if (current.data === undefined) notify()
    void promise.finally(() => {
      const latest = entries.get(keyString(key))
      if (latest) latest.pending = null
      notify()
    })
  }

  function signalSuccess(key: QueryKey, data: unknown): void {
    const current = entry(key)
    current.data = data
    current.status = 'success'
    current.error = undefined
    current.fetchedAt = Date.now()
    notify()
  }

  function signalError(key: QueryKey, error: unknown): void {
    const safeError = normalizeError(error)
    const current = entry(key)
    current.status = 'error'
    current.error = safeError
    notify()
  }

  function getData<T>(key: QueryKey): T | undefined {
    return entries.get(keyString(key))?.data as T | undefined
  }

  const manager: QueryManager = {
    getStatus(key) {
      const current = entries.get(keyString(key))
      return current?.status ?? 'idle'
    },
    getData,
    getError(key) {
      return entries.get(keyString(key))?.error
    },
    start(key, fetcher, options) {
      const current = entry(key)
      if (current.status === 'success' && !options?.force) {
        if (Date.now() - current.fetchedAt < (options?.staleMs ?? staleMs)) return
      }
      runFetch(key, fetcher)
    },
    update<T>(key: QueryKey, updater: (current: T | undefined) => T) {
      const current = entry(key)
      const next = updater(current.data as T | undefined)
      current.data = next
      current.status = 'success'
      current.error = undefined
      current.fetchedAt = Date.now()
      notify()
    },
    invalidate(patterns) {
      const removed = [...entries.keys()].filter((k) =>
        patterns.some((p) => {
          try {
            return keyMatches(p, JSON.parse(k) as QueryKey)
          } catch {
            return false
          }
        }),
      )
      for (const k of removed) entries.delete(k)
      if (removed.length) notify()
    },
    refresh(patterns) {
      for (const [k, current] of [...entries.entries()]) {
        const key = JSON.parse(k) as QueryKey
        const matched = patterns.some((p) => keyMatches(p, key))
        if (matched && current.status === 'success') {
          current.fetchedAt = 0
        }
      }
      notify()
    },
    clearAll() {
      entries.clear()
      notify()
    },
    subscribe(listener) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    getVersion() {
      return version
    },
  }

  return manager
}

interface QueryContextValue {
  manager: QueryManager
}

const QueryContext = createContext<QueryContextValue | null>(null)

export function QueryProvider({
  children,
  manager,
}: {
  children: ReactNode
  manager?: QueryManager
}) {
  // The manager is created once per provider and is fixed for its lifetime.
  const [contextValue] = useState<QueryContextValue>(() => ({
    manager: manager ?? createQueryManager(),
  }))
  return <QueryContext.Provider value={contextValue}>{children}</QueryContext.Provider>
}

export function useQuery<T>(
  key: QueryKey,
  fetcher: () => Promise<T>,
  options?: { enabled?: boolean; staleMs?: number },
): QueryResult<T> {
  const context = useContext(QueryContext)
  if (!context) throw new Error('useQuery must be used inside a QueryProvider')
  const manager = context.manager

  // A stable array identity for the key, so effects/callbacks do not re-run on
  // every render just because callers pass an inline array literal.
  const keyId = JSON.stringify(key)
  const stableKey = useMemo(() => JSON.parse(keyId) as QueryKey, [keyId])

  const enabled = options?.enabled !== false
  const staleMs = options?.staleMs

  // The latest fetcher is kept in a ref written by an effect, so starting a fetch
  // never has to re-subscribe when callers pass an inline arrow function.
  const fetcherRef = useRef(fetcher)
  useEffect(() => {
    fetcherRef.current = fetcher
  })

  const version = useSyncExternalStore(manager.subscribe, manager.getVersion, manager.getVersion)

  useEffect(() => {
    if (!enabled) return
    manager.start(stableKey, () => fetcherRef.current(), { staleMs })
  }, [manager, stableKey, enabled, staleMs, version])

  const refetch = useCallback(
    (force = false) => {
      manager.start(stableKey, () => fetcherRef.current(), { force })
    },
    [manager, stableKey],
  )

  const status = manager.getStatus(stableKey)
  return {
    data: manager.getData<T>(stableKey),
    status,
    // An enabled query that has not resolved yet is still "loading" on the very
    // first render, so consumers never briefly render an undefined payload.
    isLoading: enabled && (status === 'idle' || status === 'loading'),
    error: status === 'error' ? manager.getError(stableKey) : undefined,
    refetch,
  }
}

export function useMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>): MutationResult<TArgs, TResult> {
  const fnRef = useRef(fn)
  useEffect(() => {
    fnRef.current = fn
  })
  const [state, setState] = useState<{ isPending: boolean; error: unknown }>({
    isPending: false,
    error: undefined,
  })

  const run = useCallback(async (args: TArgs): Promise<TResult> => {
    setState({ isPending: true, error: undefined })
    try {
      const result = await fnRef.current(args)
      setState({ isPending: false, error: undefined })
      return result
    } catch (error) {
      const safe = normalizeError(error)
      setState({ isPending: false, error: safe })
      throw safe
    }
  }, [])

  return { run, isPending: state.isPending, error: state.error }
}

export function useCacheUpdater<T>(): (key: QueryKey, updater: (current: T | undefined) => T) => void {
  const context = useContext(QueryContext)
  if (!context) throw new Error('useCacheUpdater must be used inside a QueryProvider')
  const manager = context.manager
  return useCallback(
    (key, updater) => {
      manager.update(key, updater)
    },
    [manager],
  )
}

/** Expose store-level operations for feature hooks (invalidate/refresh/clear). */
export function useQueryStore() {
  const context = useContext(QueryContext)
  if (!context) throw new Error('useQueryStore must be used inside a QueryProvider')
  return context.manager
}