import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { InlineTextEditor } from './InlineTextEditor'

describe('InlineTextEditor', () => {
  it('shows the value and opens the editor on the pencil', () => {
    render(<InlineTextEditor value="Roof" onSave={async () => {}} mode="name" label="section name" />)

    expect(screen.getByText('Roof')).toBeTruthy()
    fireEvent.click(screen.getByLabelText('Edit section name'))
    expect(screen.getByLabelText('section name')).toBeTruthy()
  })

  it('saves the trimmed name', async () => {
    const calls: string[] = []
    render(
      <InlineTextEditor
        value="Old"
        onSave={async (value) => {
          calls.push(value)
        }}
        mode="name"
        label="section name"
      />,
    )

    fireEvent.click(screen.getByLabelText('Edit section name'))
    const input = screen.getByLabelText('section name') as HTMLInputElement
    fireEvent.change(input, { target: { value: '  New name  ' } })
    fireEvent.click(screen.getByLabelText('Save section name'))

    await waitFor(() => expect(calls).toEqual(['New name']))
  })

  it('rejects an empty name client-side without calling the API', async () => {
    const onSave = vi.fn()
    render(<InlineTextEditor value="Old" onSave={onSave} mode="name" label="item name" />)

    fireEvent.click(screen.getByLabelText('Edit item name'))
    fireEvent.change(screen.getByLabelText('item name'), { target: { value: '   ' } })
    fireEvent.click(screen.getByLabelText('Save item name'))

    expect(onSave).not.toHaveBeenCalled()
    expect(await screen.findByRole('alert')).toBeTruthy()
  })

  it('keeps the draft and shows an inline error when saving fails', async () => {
    render(
      <InlineTextEditor
        value="Old"
        onSave={async () => {
          throw new Error('nope')
        }}
        mode="name"
        label="section name"
      />,
    )

    fireEvent.click(screen.getByLabelText('Edit section name'))
    fireEvent.change(screen.getByLabelText('section name'), { target: { value: 'Draft kept' } })
    fireEvent.click(screen.getByLabelText('Save section name'))

    await screen.findByRole('alert')
    // editor stays open with the user's text — never silently discarded
    expect((screen.getByLabelText('section name') as HTMLInputElement).value).toBe('Draft kept')
  })

  it('cancels with Escape, discarding the draft', () => {
    render(<InlineTextEditor value="Old" onSave={async () => {}} mode="name" label="section name" />)

    fireEvent.click(screen.getByLabelText('Edit section name'))
    fireEvent.change(screen.getByLabelText('section name'), { target: { value: 'Discarded' } })
    fireEvent.keyDown(screen.getByLabelText('section name'), { key: 'Escape' })

    expect(screen.queryByLabelText('section name')).toBeNull()
    expect(screen.getByText('Old')).toBeTruthy()
  })

  it('allows empty comment content (empty clears, per contract)', async () => {
    const calls: string[] = []
    render(
      <InlineTextEditor
        value="Some content"
        onSave={async (value) => {
          calls.push(value)
        }}
        mode="content"
        label="comment content"
      />,
    )

    fireEvent.click(screen.getByLabelText('Edit comment content'))
    fireEvent.change(screen.getByLabelText('comment content'), { target: { value: '' } })
    fireEvent.click(screen.getByLabelText('Save comment content'))

    await waitFor(() => expect(calls).toEqual(['']))
  })
})