import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ImportDialog } from './ImportDialog'
import { useImport } from '../hooks/useImport'
import { ApiError } from '../../../lib/errors'
import type { ImportIssue, ImportResult } from '../types'

vi.mock('../hooks/useImport')

const runImport = vi.fn<(file: File) => Promise<ImportResult>>()
const mockUseImport = vi.mocked(useImport)

function state(overrides: Partial<ReturnType<typeof useImport>> = {}) {
  return {
    runImport,
    phase: 'idle' as const,
    progress: 0,
    error: undefined,
    result: null,
    clear: vi.fn(),
    ...overrides,
  } as unknown as ReturnType<typeof useImport>
}

function pickFile(name: string, size = 8) {
  const file = new File([new Uint8Array(size)], name)
  fireEvent.change(screen.getByLabelText('Worksheet file'), { target: { files: [file] } })
  return file
}

beforeEach(() => {
  runImport.mockReset()
  mockUseImport.mockReturnValue(state())
})

describe('ImportDialog', () => {
  it('rejects a non-export file before calling the API (FLOW 4)', () => {
    render(<ImportDialog onClose={vi.fn()} onImported={vi.fn()} />)

    pickFile('notes.txt')

    expect(screen.getByRole('alert').textContent).toBe('Choose a Spectora worksheet export (.xlsx or .xml).')
    expect(runImport).not.toHaveBeenCalled()
  })

  it('rejects a file over the contract size limit', () => {
    render(<ImportDialog onClose={vi.fn()} onImported={vi.fn()} />)

    const tooBig = new File([], 'sheet.xlsx')
    Object.defineProperty(tooBig, 'size', { value: 11 * 1024 * 1024 })
    fireEvent.change(screen.getByLabelText('Worksheet file'), { target: { files: [tooBig] } })

    expect(screen.getByRole('alert').textContent).toMatch(/10 MiB/)
    expect(runImport).not.toHaveBeenCalled()
  })

  it('uploads an accepted file and hands the new id plus issues to the page', async () => {
    const issues: ImportIssue[] = [
      {
        id: 'i1',
        issue_type: 'UNSUPPORTED_CONTENT',
        severity: 'warning',
        message: 'Photos skipped.',
        source_row: 4,
        source_field: 'Photo',
        raw_value: null,
      },
    ]
    runImport.mockResolvedValue({
      template: {
        id: 't-1',
        name: 'sheet1',
        source: 'spectora',
        source_filename: 'sheet1.xml',
        copied_from_id: null,
        created_at: '2026-09-29T00:00:00Z',
        updated_at: '2026-09-29T00:00:00Z',
        sections: [],
      },
      issues,
    } as unknown as ImportResult)
    const onImported = vi.fn()
    render(<ImportDialog onClose={vi.fn()} onImported={onImported} />)

    const file = pickFile('sheet1.xml')

    await waitFor(() =>
      expect(onImported).toHaveBeenCalledWith('t-1', issues),
    )
    expect(runImport).toHaveBeenCalledWith(file)
  })

  it('shows upload progress, then the non-cancellable importing state', () => {
    const onClose = vi.fn()
    mockUseImport.mockReturnValue(state({ phase: 'uploading', progress: 0.4 }))
    const { rerender } = render(<ImportDialog onClose={onClose} onImported={vi.fn()} />)

    expect(screen.getByText('Uploading… 40%')).toBeTruthy()
    expect(screen.getByLabelText('Close').hasAttribute('disabled')).toBe(true)

    mockUseImport.mockReturnValue(state({ phase: 'uploading', progress: 1 }))
    rerender(<ImportDialog onClose={onClose} onImported={vi.fn()} />)
    expect(screen.getByText('Importing…')).toBeTruthy()

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).not.toHaveBeenCalled()
  })

  it('surfaces a contract error from the server inside the dialog', () => {
    mockUseImport.mockReturnValue(
      state({ phase: 'error', error: new ApiError(415, 'INVALID_FILE', 'bad file', null) }),
    )
    render(<ImportDialog onClose={vi.fn()} onImported={vi.fn()} />)

    expect(screen.getByRole('alert').textContent).toMatch(/Spectora export/i)
  })

  it('moves focus into the dialog on open (accessibility)', () => {
    render(<ImportDialog onClose={vi.fn()} onImported={vi.fn()} />)
    expect(screen.getByLabelText('Close')).toBe(document.activeElement)
  })
})
