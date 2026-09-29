import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, API_BASE_URL, setAuthToken, setUnauthorizedHandler } from './apiClient'
import { ApiError } from './errors'

function makeResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? '' : JSON.stringify(body)),
  } as unknown as Response
}

const templatePayload = {
  id: '11111111-1111-1111-1111-111111111111',
  name: 'sheet1',
  source: 'spectora',
  source_filename: 'sheet1.xml',
  copied_from_id: null,
  created_at: '2026-09-29T00:00:00Z',
  updated_at: '2026-09-29T00:00:00Z',
  sections: [],
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  setAuthToken(null)
  setUnauthorizedHandler(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api requests', () => {
  it('GETs the template list at the documented path', async () => {
    fetchMock.mockResolvedValue(makeResponse(200, []))
    await api.listTemplates()

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(`${API_BASE_URL}/api/templates`)
    expect(init.method).toBe('GET')
  })

  it('attaches the bearer token from the session', async () => {
    setAuthToken('jwt-123')
    fetchMock.mockResolvedValue(makeResponse(200, templatePayload))
    await api.getTemplate(templatePayload.id)

    const [, init] = fetchMock.mock.calls[0]
    const headers = init.headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer jwt-123')
  })

  it('sends only the contract field for a rename (extra=forbid is server-side)', async () => {
    fetchMock.mockResolvedValue(makeResponse(204, undefined))
    await api.renameSection('t1', 's1', 'Roof')

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(`${API_BASE_URL}/api/templates/t1/sections/s1`)
    expect(init.method).toBe('PATCH')
    expect(JSON.parse(init.body)).toEqual({ name: 'Roof' })
  })

  it('returns undefined on 204', async () => {
    fetchMock.mockResolvedValue(makeResponse(204, undefined))
    await expect(api.editComment('t1', 'c1', 'text')).resolves.toBeUndefined()
  })

  it('sends a null body when duplicating without a name', async () => {
    fetchMock.mockResolvedValue(makeResponse(201, templatePayload))
    await api.duplicateTemplate('t1')

    const [, init] = fetchMock.mock.calls[0]
    expect(JSON.parse(init.body)).toBeNull()
  })

  it('sends {"name"} when duplicating with a name', async () => {
    fetchMock.mockResolvedValue(makeResponse(201, templatePayload))
    await api.duplicateTemplate('t1', 'Copy of sheet1')

    const [, init] = fetchMock.mock.calls[0]
    expect(JSON.parse(init.body)).toEqual({ name: 'Copy of sheet1' })
  })
})

describe('error normalization', () => {
  it('converts a contract error envelope into ApiError', async () => {
    fetchMock.mockResolvedValue(
      makeResponse(404, { error: { code: 'TEMPLATE_NOT_FOUND', message: 'Template was not found.', details: null } }),
    )

    await expect(api.getTemplate('missing')).rejects.toMatchObject({
      status: 404,
      code: 'TEMPLATE_NOT_FOUND',
    })
  })

  it('rejects a 200 payload that violates the contract shape', async () => {
    fetchMock.mockResolvedValue(makeResponse(200, { unexpected: true }))

    await expect(api.getTemplate('t1')).rejects.toBeInstanceOf(ApiError)
  })

  it('triggers the unauthorized handler on 401 and throws INVALID_TOKEN', async () => {
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    fetchMock.mockResolvedValue(
      makeResponse(401, { error: { code: 'AUTHENTICATION_REQUIRED', message: 'Authentication required.', details: null } }),
    )

    await expect(api.listTemplates()).rejects.toMatchObject({ status: 401 })
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('maps a transport failure to NETWORK_ERROR', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(api.listTemplates()).rejects.toMatchObject({ code: 'NETWORK_ERROR', status: 0 })
  })
})
