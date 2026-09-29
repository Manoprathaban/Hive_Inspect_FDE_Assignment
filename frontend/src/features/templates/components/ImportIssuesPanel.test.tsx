import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ImportIssuesPanel } from './ImportIssuesPanel'
import type { ImportIssue } from '../types'

const issues: ImportIssue[] = [
  {
    id: 'issue-1',
    issue_type: 'UNSUPPORTED_CONTENT',
    severity: 'warning',
    message: 'Photos column is not supported yet.',
    source_row: 12,
    source_field: 'Photo',
    raw_value: 'a'.repeat(200),
  },
  {
    id: 'issue-2',
    issue_type: 'SOURCE_DATA_MISSING',
    severity: 'info',
    message: 'Order (w/i item) was empty in the export.',
    source_row: null,
    source_field: null,
    raw_value: null,
  },
]

describe('ImportIssuesPanel', () => {
  it('answers what was skipped and why (never console-only)', () => {
    render(<ImportIssuesPanel issues={issues} isLoading={false} onClose={() => {}} />)

    expect(screen.getByText('Photos column is not supported yet.')).toBeTruthy()
    expect(screen.getByText('Order (w/i item) was empty in the export.')).toBeTruthy()
    expect(screen.getByText('UNSUPPORTED_CONTENT')).toBeTruthy()
    expect(screen.getByText('row 12')).toBeTruthy()
  })

  it('truncates a long raw value', () => {
    render(<ImportIssuesPanel issues={issues} isLoading={false} onClose={() => {}} />)
    const raw = screen.getByText(/^a+a…$/)
    expect(raw.textContent?.length).toBeLessThanOrEqual(121)
  })

  it('shows the empty state when there are no issues', () => {
    render(<ImportIssuesPanel issues={[]} isLoading={false} onClose={() => {}} />)
    expect(screen.getByText('No issues recorded for this template.')).toBeTruthy()
  })

  it('shows a loading line and closes on demand', () => {
    const onClose = vi.fn()
    render(<ImportIssuesPanel issues={[]} isLoading onClose={onClose} />)

    expect(screen.getByText('Loading issues…')).toBeTruthy()
    fireEvent.click(screen.getByLabelText('Close import issues'))
    expect(onClose).toHaveBeenCalled()
  })
})