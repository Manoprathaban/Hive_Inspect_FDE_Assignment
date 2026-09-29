/**
 * The single HTTP boundary (FRONTEND_DESIGN §17). No component calls fetch directly;
 * feature code goes through features/templates/api.ts. Attaches the bearer token from the
 * current session, follows the contract envelope, normalizes errors, and treats any 401
 * as a session problem (clears the session so the router guard redirects to /login).
 */

import { ApiError, fromEnvelope, normalizeError } from './errors'
import {
  isImportIssueList,
  isImportResult,
  isTemplate,
  isTemplateSummaryList,
} from './types'
import type { ImportIssue, ImportResult, Template, TemplateSummary } from './types'

export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '')

const REQUEST_TIMEOUT_MS = 30_000
// Import runs the whole server-side parse + persist pipeline inside one request; a cold
// run of the committed Spectora export on the deployed database takes over a minute, so
// this budget is deliberately generous (matching the manual API battery's 600s).
const UPLOAD_TIMEOUT_MS = 600_000
const INVALID_RESPONSE = 'INVALID_RESPONSE'

let authToken: string | null = null
let unauthorizedHandler: (() => void) | null = null

/** Session token set by AuthProvider on every auth change. */
export function setAuthToken(token: string | null): void {
  authToken = token
}

/** Registered by AuthProvider: any API 401 signs the user out (never shown raw). */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler
}

function handleUnauthorized(): void {
  unauthorizedHandler?.()
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text) as unknown
  } catch {
    return null
  }
}

async function request<T>(
  path: string,
  method: string,
  options: { json?: unknown; body?: BodyInit; guard?: (value: unknown) => value is T } = {},
): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  const headers: Record<string, string> = { Accept: 'application/json' }
  if (authToken) headers.Authorization = `Bearer ${authToken}`
  let body: BodyInit | undefined
  if (options.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.json)
  } else if (options.body !== undefined) {
    body = options.body
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body,
      signal: controller.signal,
    })

    if (response.status === 204) return undefined as T

    const text = await response.text()
    const json = text ? parseJson(text) : null

    if (!response.ok) {
      if (response.status === 401) handleUnauthorized()
      throw fromEnvelope(response.status, json)
    }

    if (options.guard && !options.guard(json)) {
      throw new Error(INVALID_RESPONSE)
    }
    return json as T
  } catch (error) {
    if (error instanceof Error && error.message === INVALID_RESPONSE) {
      throw fromEnvelope(502, {
        error: { code: 'INTERNAL_ERROR', message: 'The server returned an unexpected response.', details: null },
      } as import('./types').ApiErrorEnvelope)
    }
    if (error instanceof ApiError) throw error
    throw normalizeError(error)
  } finally {
    clearTimeout(timer)
  }
}

/** Upload import via XHR for progress events (fetch has no upload progress). */
function uploadImport(
  file: File,
  onProgress: ((fraction: number) => void) | undefined,
): Promise<ImportResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE_URL}/api/templates/import`)
    if (authToken) xhr.setRequestHeader('Authorization', `Bearer ${authToken}`)
    xhr.responseType = 'text'
    xhr.timeout = UPLOAD_TIMEOUT_MS

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress(event.loaded / event.total)
    }

    xhr.onload = () => {
      const json = xhr.responseText ? parseJson(xhr.responseText) : null
      if (xhr.status >= 200 && xhr.status < 300) {
        if (isImportResult(json)) {
          resolve(json)
          return
        }
        reject(fromEnvelope(502, null))
        return
      }
      if (xhr.status === 401) handleUnauthorized()
      reject(fromEnvelope(xhr.status, json))
    }
    xhr.onerror = () => reject(normalizeError(new Error('xhr error')))
    xhr.ontimeout = () =>
      reject(fromEnvelope(0, {
        error: { code: 'NETWORK_ERROR', message: 'Upload timed out.', details: null },
      } as import('./types').ApiErrorEnvelope))

    const form = new FormData()
    form.append('file', file)
    xhr.send(form)
  })
}

/** Template endpoints — the one allowed path to features/templates/api.ts. */
export const api = {
  /** GET /api/templates — the caller's summaries, newest first. */
  listTemplates(): Promise<TemplateSummary[]> {
    return request('/api/templates', 'GET', { guard: isTemplateSummaryList })
  },

  /** GET /api/templates/{template_id} — full hierarchy. */
  getTemplate(templateId: string): Promise<Template> {
    return request(`/api/templates/${encodeURIComponent(templateId)}`, 'GET', { guard: isTemplate })
  },

  /** GET /api/templates/{template_id}/import-issues. */
  getImportIssues(templateId: string): Promise<ImportIssue[]> {
    return request(`/api/templates/${encodeURIComponent(templateId)}/import-issues`, 'GET', {
      guard: isImportIssueList,
    })
  },

  /** POST /api/templates/import — multipart upload with progress. */
  importFile(file: File, onProgress?: (fraction: number) => void): Promise<ImportResult> {
    return uploadImport(file, onProgress)
  },

  /** POST /api/templates/{template_id}/duplicate — optional {"name"}. */
  duplicateTemplate(templateId: string, name?: string): Promise<Template> {
    return request(`/api/templates/${encodeURIComponent(templateId)}/duplicate`, 'POST', {
      json: name === undefined ? null : { name },
      guard: isTemplate,
    })
  },

  /** PATCH .../sections/{id} — {"name"}, 204. */
  renameSection(templateId: string, sectionId: string, name: string): Promise<void> {
    return request(
      `/api/templates/${encodeURIComponent(templateId)}/sections/${encodeURIComponent(sectionId)}`,
      'PATCH',
      { json: { name } },
    )
  },

  /** PATCH .../items/{id} — {"name"}, 204. */
  renameItem(templateId: string, itemId: string, name: string): Promise<void> {
    return request(
      `/api/templates/${encodeURIComponent(templateId)}/items/${encodeURIComponent(itemId)}`,
      'PATCH',
      { json: { name } },
    )
  },

  /** PATCH .../comments/{id} — {"content"}, 204. */
  editComment(templateId: string, commentId: string, content: string): Promise<void> {
    return request(
      `/api/templates/${encodeURIComponent(templateId)}/comments/${encodeURIComponent(commentId)}`,
      'PATCH',
      { json: { content } },
    )
  },
}