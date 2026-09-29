import { describe, expect, it } from 'vitest'
import { ApiError, describeError, entryForCode, fromEnvelope, isNotFoundError, isRetryableError, normalizeError } from './errors'

describe('fromEnvelope', () => {
  it('parses the contract error envelope', () => {
    const error = fromEnvelope(404, {
      error: { code: 'TEMPLATE_NOT_FOUND', message: 'Template was not found.', details: null },
    })
    expect(error.status).toBe(404)
    expect(error.code).toBe('TEMPLATE_NOT_FOUND')
    expect(error.message).toBe('Template was not found.')
  })

  it('keeps details when the contract supplies them', () => {
    const error = fromEnvelope(422, {
      error: { code: 'INVALID_XLSX', message: 'nope', details: { reason: 'missing worksheet' } },
    })
    expect(error.details).toEqual({ reason: 'missing worksheet' })
  })

  it('falls back to INTERNAL_ERROR for a non-envelope body', () => {
    const error = fromEnvelope(500, { detail: 'boom' })
    expect(error.code).toBe('INTERNAL_ERROR')
  })

  it('falls back for an empty body', () => {
    const error = fromEnvelope(401, null)
    expect(error.code).toBe('INTERNAL_ERROR')
  })
})

describe('normalizeError', () => {
  it('passes ApiError through unchanged', () => {
    const original = new ApiError(409, 'DATABASE_CONFLICT', 'conflict')
    expect(normalizeError(original)).toBe(original)
  })

  it('turns unknown throwables into NETWORK_ERROR', () => {
    const error = normalizeError(new TypeError('Failed to fetch'))
    expect(error.code).toBe('NETWORK_ERROR')
    expect(error.status).toBe(0)
  })

  it('turns aborts into NETWORK_ERROR', () => {
    const abort = new DOMException('Aborted', 'AbortError')
    expect(normalizeError(abort).code).toBe('NETWORK_ERROR')
  })
})

describe('user-facing mapping (§20)', () => {
  it('maps 401 codes to a sign-in message', () => {
    expect(entryForCode('AUTHENTICATION_REQUIRED').message).toMatch(/sign in/i)
    expect(entryForCode('INVALID_TOKEN').message).toMatch(/sign in/i)
  })

  it('maps not-found codes', () => {
    expect(entryForCode('TEMPLATE_NOT_FOUND').message).toMatch(/isn't available/i)
  })

  it('maps import errors', () => {
    expect(entryForCode('INVALID_FILE').message).toMatch(/Spectora export/i)
    expect(entryForCode('INVALID_XLSX').message).toMatch(/valid XLSX/i)
    expect(entryForCode('FILE_TOO_LARGE').message).toMatch(/10 MiB/i)
  })

  it('prefers the server message for validation errors', () => {
    const described = describeError(new ApiError(422, 'VALIDATION_ERROR', 'Request validation failed.'))
    expect(described.message).toBe('Request validation failed.')
  })

  it('falls back for an unknown code', () => {
    expect(entryForCode('SOMETHING_NEW').message).toBeTruthy()
  })
})

describe('classification', () => {
  it('detects the not-found family', () => {
    expect(isNotFoundError(new ApiError(404, 'COMMENT_NOT_FOUND', 'x'))).toBe(true)
    expect(isNotFoundError(new ApiError(500, 'INTERNAL_ERROR', 'x'))).toBe(false)
  })

  it('detects retryable failures', () => {
    expect(isRetryableError(new ApiError(0, 'NETWORK_ERROR', 'x'))).toBe(true)
    expect(isRetryableError(new ApiError(500, 'INTERNAL_ERROR', 'x'))).toBe(true)
    expect(isRetryableError(new ApiError(422, 'VALIDATION_ERROR', 'x'))).toBe(false)
  })
})
