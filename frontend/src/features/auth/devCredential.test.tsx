/**
 * Development credentials must identify a workspace, not a shared session.
 *
 * Regression cover for the reported bug: a hard-coded 'dev-token' meant every developer
 * signed in as the same seeded user, so a different set of credentials still showed that
 * user's templates. The real AuthProvider is used in its dev-mode fallback, so this exercises
 * the genuine path.
 */

import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AuthProvider, { useSession } from './AuthProvider'
import { QueryProvider } from '../../lib/query'
import type { QueryManager } from '../../lib/query'

// No Supabase configured, so the provider takes its development path.
vi.mock('@supabase/supabase-js', () => ({ createClient: vi.fn(() => null) }))

function DevSignIn({ email }: { email: string }) {
  const { session, login } = useSession()
  if (session) return <p>token:{session.accessToken}</p>
  return (
    <button type="button" onClick={() => void login(email, 'irrelevant')}>
      sign in
    </button>
  )
}

function managerStub(): QueryManager {
  return { clearAll: vi.fn(), invalidateAll: vi.fn(), set: vi.fn(), get: vi.fn() } as unknown as QueryManager
}

async function signInAs(email: string): Promise<HTMLElement> {
  const user = userEvent.setup()
  render(
    <QueryProvider manager={managerStub()}>
      <AuthProvider>
        <DevSignIn email={email} />
      </AuthProvider>
    </QueryProvider>,
  )
  await user.click(await screen.findByRole('button', { name: 'sign in' }))
  return screen.findByText(/^token:/)
}

describe('development credentials', () => {
  it('sends the entered email so the backend resolves a per-credential identity', async () => {
    const token = await signInAs('  Someone@Example.test  ')
    expect(token.textContent).toBe('token:dev:someone@example.test')
  })

  it('never sends the shared dev-token that leaked one workspace', async () => {
    const token = await signInAs('demo@hive.test')
    expect(token.textContent).toBe('token:dev:demo@hive.test')
    expect(token.textContent).not.toContain('dev-token')
  })

  it('never puts the password in the credential', async () => {
    const token = await signInAs('demo@hive.test')
    expect(token.textContent).not.toContain('irrelevant')
  })
})
