/**
 * /login — Supabase Auth email/password sign-in and sign-up, or the deterministic dev
 * fallback when Supabase is not configured (FRONTEND_DESIGN §7/§31).
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

// The seeded development identity. Must match DEV_AUTH_USERS in backend/.env, which maps
// this email onto the user id that owns the seeded templates.
const DEMO_EMAIL = 'demo@hive.test'

export function LoginPage() {
  const { session, isInitializing, isDevMode, login, signup } = useSession()
  const machine = useLoginMachine('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const navigate = useNavigate()
  const location = useLocation()

  if (isInitializing) return <LoadingState label="Checking session…" />

  if (session) {
    const from = (location.state as LocationState | null)?.from ?? '/templates'
    return <Navigate to={from} replace />
  }

  const destination = (location.state as LocationState | null)?.from ?? '/templates'

  const isSignUp = machine.state.mode === 'signup'

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()

    if (isSignUp) {
      if (password !== confirmPassword) {
        machine.fail('Passwords do not match.')
        return
      }
      if (password.length < 6) {
        machine.fail('Password must be at least 6 characters.')
        return
      }
    }

    machine.submit()

    try {
      if (isSignUp) {
        const result = await signup(email, password)
        if (result.sessionCreated) {
          machine.succeed()
          navigate(destination, { replace: true })
        } else {
          machine.showInfo(result.message ?? 'Sign up successful! Please check your email to confirm.')
        }
      } else {
        await login(email, password)
        machine.succeed()
        navigate(destination, { replace: true })
      }
    } catch (error) {
      const entry = describeError(error)
      machine.fail(entry.message)
    }
  }

  async function handleDevLogin() {
    machine.submit()
    try {
      if (isSignUp) {
        await signup(DEMO_EMAIL, 'devpass')
      } else {
        await login(DEMO_EMAIL, '')
      }
      machine.succeed()
      navigate(destination, { replace: true })
    } catch (error) {
      const entry = describeError(error)
      machine.fail(entry.message)
    }
  }

  const toggleMode = (mode: 'signin' | 'signup') => {
    machine.setMode(mode)
    setPassword('')
    setConfirmPassword('')
  }

  return (
    <section className="page login-page">
      <div className="card login-card">
        <h1>Hive Inspect</h1>
        <p className="tagline">
          {isSignUp ? 'Create your account' : 'Template Importer sign in'}
        </p>

        <div className="auth-tabs" role="tablist" aria-label="Authentication Options">
          <button
            type="button"
            role="tab"
            aria-selected={!isSignUp}
            className={`auth-tab ${!isSignUp ? 'auth-tab--active' : ''}`}
            onClick={() => toggleMode('signin')}
          >
            Sign In
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={isSignUp}
            className={`auth-tab ${isSignUp ? 'auth-tab--active' : ''}`}
            onClick={() => toggleMode('signup')}
          >
            Sign Up
          </button>
        </div>

        {isDevMode && (
          <p className="dev-note">
            Development mode — Supabase Auth is not configured. Every email is its own
            workspace, so you only ever see what you import yourself. Sign in as
            demo@hive.test for the seeded templates.
          </p>
        )}

        <form onSubmit={handleSubmit} className="login-form">
            <label htmlFor="auth-email">Email</label>
            <input
              id="auth-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              required
            />
            <label htmlFor="auth-password">Password</label>
            <input
              id="auth-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={isSignUp ? 'new-password' : 'current-password'}
              required
            />
            {isSignUp && (
              <>
                <label htmlFor="auth-confirm-password">Confirm Password</label>
                <input
                  id="auth-confirm-password"
                  type="password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  autoComplete="new-password"
                  required
                />
              </>
            )}

            {machine.state.phase === 'error' && (
              <p className="field-error" aria-live="polite">
                {machine.state.message}
              </p>
            )}

            {machine.state.phase === 'info' && (
              <p className="field-info" aria-live="polite">
                {machine.state.message}
              </p>
            )}

            <button
              type="submit"
              className="button button--primary"
              disabled={machine.state.phase === 'submitting'}
            >
              {machine.state.phase === 'submitting'
                ? isSignUp
                  ? 'Creating account…'
                  : 'Signing in…'
                : isSignUp
                  ? 'Sign Up'
                  : 'Sign In'}
            </button>
        </form>

        {isDevMode && (
          <button
            type="button"
            className="button button--primary"
            onClick={handleDevLogin}
            disabled={machine.state.phase === 'submitting'}
          >
            Continue as demo user
          </button>
        )}

        <div className="auth-footer">
          {isSignUp ? (
            <p>
              Already have an account?{' '}
              <button
                type="button"
                className="link-button"
                onClick={() => toggleMode('signin')}
              >
                Sign In
              </button>
            </p>
          ) : (
            <p>
              Don't have an account?{' '}
              <button
                type="button"
                className="link-button"
                onClick={() => toggleMode('signup')}
              >
                Sign Up
              </button>
            </p>
          )}
        </div>
      </div>
    </section>
  )
}