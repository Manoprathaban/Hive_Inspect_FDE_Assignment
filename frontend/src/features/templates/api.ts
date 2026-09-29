/**
 * Template API surface (FRONTEND_DESIGN §18) + client-side validation rules that mirror
 * the contract (§12) exactly. Functions map 1:1 to endpoints; no UI component calls the
 * HTTP layer directly (FRONTEND_DESIGN §4/§17).
 */

import { api } from '../../lib/apiClient'

export const templateApi = api

/** Client-side copy of the §12.1 name rule (trimmed, 1–200 chars). */
export function validateName(value: string): string | null {
  const trimmed = value.trim()
  if (trimmed.length < 1) return 'Name is required.'
  if (trimmed.length > 200) return 'Name must be 1–200 characters.'
  return null
}

/** Client-side copy of the §12.2 content rule (verbatim; empty clears). Always valid. */
export function validateContent(_value: string): string | null {
  return null
}

/** The three editable things, for scoped mutations. */
export type EditKind = 'section' | 'item' | 'comment'

/** Recognized import containers (matches the backend's authoritative check). */
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024

export function clientFileError(file: File): string | null {
  const suffix = file.name.toLowerCase().split('.').pop()
  if (suffix !== 'xlsx' && suffix !== 'xml') {
    return 'Choose a Spectora worksheet export (.xlsx or .xml).'
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return 'File exceeds the 10 MiB limit.'
  }
  return null
}