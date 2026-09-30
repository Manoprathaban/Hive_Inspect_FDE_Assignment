/**
 * LogOutButton unit tests — the control's own contract, with the session source mocked:
 * hidden without a session, calls logout, and cannot be double-submitted.
 *
 * The end-to-end sign-out flow lives in `logoutFlow.test.tsx`, which needs the real
 * AuthProvider and therefore cannot share this file's module mock.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { useSession } from './AuthProvider'
import { LogOutButton } from './LogOutButton'

vi.mock('./AuthProvider', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./AuthProvider')>()
  return { ...actual, useSession: vi.fn() }
})

const mockUseSession = vi.mocked(useSession)

function session(overrides: Partial<ReturnType<typeof useSession>> = {}) {
  return {
    session: { accessToken: 'dev-token' },
    isInitializing: false,
    isDevMode: true,
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
    ...overrides,
  } as unknown as ReturnType<typeof useSession>
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

function renderButton() {
  return render(
    <MemoryRouter>
      <LogOutButton />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mockUseSession.mockReset()
})

describe('LogOutButton', () => {
  it('renders nothing without a session', () => {
    mockUseSession.mockReturnValue(session({ session: null }))
    const { container } = renderButton()
    expect(container.innerHTML).toBe('')
  })

  it('calls logout when clicked', () => {
    const logout = vi.fn().mockResolvedValue(undefined)
    mockUseSession.mockReturnValue(session({ logout }))

    renderButton()

    fireEvent.click(screen.getByRole('button', { name: 'Log out' }))
    expect(logout).toHaveBeenCalledTimes(1)
  })

  it('disables the control while signing out and ignores repeat clicks', async () => {
    const { promise, resolve } = deferred<void>()
    const logout = vi.fn().mockReturnValue(promise)
    mockUseSession.mockReturnValue(session({ logout }))

    renderButton()

    fireEvent.click(screen.getByRole('button', { name: 'Log out' }))

    const pending = await screen.findByRole('button', { name: 'Logging out…' })
    expect(pending.hasAttribute('disabled')).toBe(true)

    fireEvent.click(pending)
    expect(logout).toHaveBeenCalledTimes(1)

    resolve()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Log out' })).toBeTruthy())
  })
})
