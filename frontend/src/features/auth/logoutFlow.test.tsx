/**
 * Logout flow end-to-end (FRONTEND_DESIGN §7 — logout signs out, clears the whole
 * server-state cache so no data crosses users, and routes to `/login`).
 *
 * Uses the real AuthProvider in its dev-mode fallback (no Supabase configured), so this
 * exercises the genuine path: sign in -> control appears -> log out -> cache cleared,
 * session gone, login route shown.
 */

import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import AuthProvider, { useSession } from './AuthProvider'
import { LogOutButton } from './LogOutButton'
import { QueryProvider } from '../../lib/query'
import type { QueryManager } from '../../lib/query'

function SignInButton() {
  const { login } = useSession()
  return (
    <button type="button" onClick={() => void login('inspector@example.com', 'dev-password')}>
      sign in
    </button>
  )
}

function renderApp(manager: QueryManager) {
  return render(
    <QueryProvider manager={manager}>
      <AuthProvider>
        <MemoryRouter initialEntries={['/templates']}>
          <SignInButton />
          <Routes>
            <Route path="/login" element={<p>login page</p>} />
            <Route path="/templates" element={<LogOutButton />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryProvider>,
  )
}

describe('logout flow', () => {
  it('signs out, clears the query cache, and routes to /login', async () => {
    const clearAll = vi.fn()
    const manager = { clearAll } as unknown as QueryManager

    renderApp(manager)

    // Dev mode: no Supabase configured, so signing in yields the deterministic dev token.
    fireEvent.click(screen.getByRole('button', { name: 'sign in' }))
    await screen.findByRole('button', { name: 'Log out' })

    fireEvent.click(screen.getByRole('button', { name: 'Log out' }))

    // The whole server-state cache is dropped so the next user cannot read this one's data.
    await waitFor(() => expect(clearAll).toHaveBeenCalled())
    // The control disappears with the session, and /login is rendered. Both are awaited:
    // the session clears (unmounting the control) in the same tick that navigation is
    // issued, so the button can disappear a tick before the route swaps.
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Log out' })).toBeNull())
    await waitFor(() => expect(screen.getByText('login page')).toBeTruthy())
  })
})
