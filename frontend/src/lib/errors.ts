/**
 * Error normalization + the single user-facing code→message map (FRONTEND_DESIGN §20).
 * Every API error is an ApiError { status, code, message, details }; network/timeout
 * failures become synthetic NETWORK_ERROR. Messages live in one table so copy is
 * consistent; recoverable hints travel with them when useful.
 */

import type { ApiErrorEnvelope } from './types'

export interface ApiErrorData {
  status: number
  code: string
  message: string
  details: unknown
}

/** Contract-shaped API error. `status` 0 marks a transport-level failure. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: unknown

  constructor(status: number, code: string, message: string, details: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.message = message
    this.details = details
  }
}

export type ErrorEntry = { message: string; hint?: string }

/** §20 table: every contract error code maps to an explicit user-facing message. */
const CODE_MESSAGES: Record<string, ErrorEntry> = {
  AUTHENTICATION_REQUIRED: {
    message: 'Your session has ended. Please sign in again.',
  },
  INVALID_TOKEN: {
    message: 'Your session has ended. Please sign in again.',
  },
  FORBIDDEN: {
    message: "You can't do that.",
    hint: 'Reload the page or go back.',
  },
  TEMPLATE_NOT_FOUND: {
    message: "This template isn't available anymore.",
    hint: 'It may have been removed.',
  },
  SECTION_NOT_FOUND: {
    message: 'That section is no longer there.',
    hint: 'Reload the page.',
  },
  ITEM_NOT_FOUND: {
    message: 'That item is no longer there.',
    hint: 'Reload the page.',
  },
  COMMENT_NOT_FOUND: {
    message: 'That comment is no longer there.',
    hint: 'Reload the page.',
  },
  DATABASE_CONFLICT: {
    message: "The change wasn't saved.",
    hint: 'Reload and try again.',
  },
  VALIDATION_ERROR: {
    message: 'One of the values you entered is not valid.',
  },
  FILE_TOO_LARGE: {
    message: 'File exceeds the 10 MiB limit.',
  },
  INVALID_FILE: {
    message: "That doesn't look like a Spectora export.",
    hint: 'Upload an .xlsx worksheet export.',
  },
  INVALID_XLSX: {
    message: 'The file could not be read as a valid XLSX.',
    hint: 'Upload a Spectora worksheet export.',
  },
  INTERNAL_ERROR: {
    message: 'Something went wrong on the server.',
  },
  NETWORK_ERROR: {
    message: 'Could not reach the server.',
    hint: 'Check your connection and try again.',
  },
}

const FALLBACK_ENTRY: ErrorEntry = {
  message: 'Something went wrong.',
  hint: 'Try again.',
}

export function entryForCode(code: string): ErrorEntry {
  return CODE_MESSAGES[code] ?? FALLBACK_ENTRY
}

/** Parse the contract error envelope, or fall back to an INTERNAL_ERROR shape. */
export function fromEnvelope(status: number, body: unknown): ApiError {
  const envelope = body as ApiErrorEnvelope | null
  const error = envelope?.error
  if (error && typeof error.code === 'string' && typeof error.message === 'string') {
    return new ApiError(status, error.code, error.message, error.details)
  }
  const entry = FALLBACK_ENTRY
  return new ApiError(status, 'INTERNAL_ERROR', entry.message)
}

/** Normalize any thrown value into an ApiError (never lets raw errors leak out). */
export function normalizeError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  if (error instanceof DOMException && error.name === 'AbortError') {
    return new ApiError(0, 'NETWORK_ERROR', CODE_MESSAGES.NETWORK_ERROR.message)
  }
  return new ApiError(0, 'NETWORK_ERROR', CODE_MESSAGES.NETWORK_ERROR.message)
}

/** User-facing copy for an error; used by pages and dialogs. */
export function describeError(error: unknown): ErrorEntry {
  const apiError = normalizeError(error)
  const entry = entryForCode(apiError.code)
  if (apiError.code === 'VALIDATION_ERROR') {
    return { message: apiError.message || entry.message }
  }
  return entry
}

/** True when the error maps to the "not found" family (§20). */
export function isNotFoundError(error: unknown): boolean {
  const apiError = normalizeError(error)
  return apiError.code.endsWith('_NOT_FOUND')
}

/** True when the error is transient and a retry is appropriate. */
export function isRetryableError(error: unknown): boolean {
  const apiError = normalizeError(error)
  return apiError.status === 0 || apiError.status >= 500
}