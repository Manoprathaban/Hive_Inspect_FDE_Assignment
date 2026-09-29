import { describe, expect, it } from 'vitest'
import { clientFileError, validateContent, validateName } from './api'

describe('validateName (mirrors contract §12.1)', () => {
  it('accepts a trimmed 1-200 character name', () => {
    expect(validateName('Roof')).toBeNull()
    expect(validateName('  Roof  ')).toBeNull()
    expect(validateName('a'.repeat(200))).toBeNull()
  })

  it('rejects empty/whitespace-only names', () => {
    expect(validateName('')).toBeTruthy()
    expect(validateName('   ')).toBeTruthy()
  })

  it('rejects names longer than 200 characters', () => {
    expect(validateName('a'.repeat(201))).toBeTruthy()
  })
})

describe('validateContent (mirrors contract §12.2)', () => {
  it('allows any content including empty', () => {
    expect(validateContent('')).toBeNull()
    expect(validateContent('anything at all')).toBeNull()
  })
})

describe('clientFileError (client-side upload gate, §12)', () => {
  const file = (name: string, size = 10) => new File([new Uint8Array(size)], name)

  it('accepts .xlsx and .xml exports', () => {
    expect(clientFileError(file('sheet.xlsx'))).toBeNull()
    expect(clientFileError(file('sheet.xml'))).toBeNull()
  })

  it('rejects other file types', () => {
    expect(clientFileError(file('notes.txt'))).toBeTruthy()
    expect(clientFileError(file('noextension'))).toBeTruthy()
  })

  it('rejects files over the 10 MiB contract limit', () => {
    const tooBig = new File([], 'sheet.xlsx')
    Object.defineProperty(tooBig, 'size', { value: 11 * 1024 * 1024 })
    expect(clientFileError(tooBig)).toMatch(/10 MiB/)
  })
})
