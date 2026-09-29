import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ErrorState } from './ErrorState'
import { LoadingState } from './LoadingState'

describe('LoadingState', () => {
  it('renders card skeletons with an accessible label', () => {
    const { container } = render(<LoadingState label="Loading templates" count={4} />)
    expect(container.querySelectorAll('.skeleton--card')).toHaveLength(4)
    expect(screen.getByRole('status').getAttribute('aria-label')).toBe('Loading templates')
  })

  it('renders row skeletons for the hierarchy view', () => {
    const { container } = render(<LoadingState label="Loading template" variant="rows" count={6} />)
    expect(container.querySelectorAll('.skeleton--row')).toHaveLength(6)
  })
})

describe('ErrorState', () => {
  it('shows the mapped message and hint as an alert', () => {
    render(
      <ErrorState message="Couldn't load templates." hint="Check that the backend is running." />,
    )

    const alert = screen.getByRole('alert')
    expect(alert.textContent).toContain("Couldn't load templates.")
    expect(alert.textContent).toContain('Check that the backend is running.')
  })

  it('offers a retry that calls back', () => {
    const onRetry = vi.fn()
    render(<ErrorState message="Network error." onRetry={onRetry} />)

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('offers a back link when no retry makes sense (not-found)', () => {
    render(
      <MemoryRouter>
        <ErrorState message="This template isn't available anymore." backTo={{ to: '/templates', label: 'Back to templates' }} />
      </MemoryRouter>,
    )

    const link = screen.getByRole('link', { name: 'Back to templates' })
    expect(link.getAttribute('href')).toBe('/templates')
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull()
  })
})
