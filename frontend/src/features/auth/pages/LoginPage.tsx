/**
 * /login — Supabase Auth email/password, or the deterministic dev fallback when Supabase
 * is not configured (FRONTEND_DESIGN §7/§31). No signup form; signup is Supabase-side.
 */

import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { describeError } from '../../../lib/errors'
import { useSession } from '../AuthProvider'
import { useLoginMachine } from '../loginMachine'
import { LoadingState } from '../../templates/components/states/LoadingState'

interface LocationState {
  from?: string
}

export function LoginPage() {
  const { session, isInitializing, isDevMode, login } = useSession()
  const machine = useLoginMachine()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()
  const location = useLocation()

  if (isInitializing) return <LoadingState label="Checking session…" />

  if (session) {
    const from = (location.state as LocationState | null)?.from ?? '/templates'
    return <Navigate to={from} replace />
  }

  const destination = (location.state as LocationState | null)?.from ?? '/templates'

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    machine.submit()
    try {
      await login(email, password)
      machine.succeed()
      navigate(destination, { replace: true })
    } catch (error) {
      const entry = describeError(error)
      machine.fail(entry.message)
    }
  }

  async function handleDevLogin() {
    machine.submit()
    try {
      await login('dev@example.com', '')
      machine.succeed()
      navigate(destination, { replace: true })
    } catch (error) {
      const entry = describeError(error)
      machine.fail(entry.message)
    }
  }

  return (
    <section className="page login-page">
      <div className="card login-card">
        <h1>Hive Inspect</h1>
        <p className="tagline">Template Importer sign in</p>

        {isDevMode ? (
          <div className="dev-login">
            <p className="dev-note">
              Development mode — Supabase Auth is not configured. Continue with the demo
              session to exercise the UI against the dev backend.
            </p>
            <button
              type="button"
              className="button button--primary"
              onClick={handleDevLogin}
              disabled={machine.state.phase === 'submitting'}
            >
              {machine.state.phase === 'submitting' ? 'Signing in…' : 'Continue as demo user'}
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="login-form">
            <label htmlFor="login-email">Email</label>
            <input
              id="login-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              required
            />
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
            {machine.state.phase === 'error' && (
              <p className="field-error" aria-live="polite">
                {machine.state.message}
              </p>
            )}
            <button
              type="submit"
              className="button button--primary"
              disabled={machine.state.phase === 'submitting'}
            >
              {machine.state.phase === 'submitting' ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        )}

        {machine.state.phase === 'error' && !isDevMode && (
          <p className="field-error" aria-live="polite">
            {machine.state.message}
          </p>
        )}
      </div>
    </section>
  )
}