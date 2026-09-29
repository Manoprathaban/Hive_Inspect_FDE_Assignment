import { describe, expect, it } from 'vitest'
import { loginReducer } from './loginMachine'

describe('loginReducer', () => {
  it('starts idle', () => {
    expect(loginReducer({ phase: 'idle', mode: 'signin' }, { type: 'reset' })).toEqual({
      phase: 'idle',
      mode: 'signin',
      message: undefined,
    })
  })

  it('moves to submitting and clears any prior error', () => {
    const state = { phase: 'error' as const, mode: 'signin' as const, message: 'bad password' }
    expect(loginReducer(state, { type: 'submit' })).toEqual({
      phase: 'submitting',
      mode: 'signin',
      message: undefined,
    })
  })

  it('moves to authenticated on success', () => {
    expect(loginReducer({ phase: 'submitting', mode: 'signin' }, { type: 'success' })).toEqual({
      phase: 'authenticated',
      mode: 'signin',
      message: undefined,
    })
  })

  it('records the error message on failure', () => {
    expect(
      loginReducer(
        { phase: 'submitting', mode: 'signin' },
        { type: 'error', message: 'Sign-in failed' },
      ),
    ).toEqual({
      phase: 'error',
      mode: 'signin',
      message: 'Sign-in failed',
    })
  })

  it('handles info message state', () => {
    expect(
      loginReducer(
        { phase: 'submitting', mode: 'signup' },
        { type: 'info', message: 'Check your email' },
      ),
    ).toEqual({
      phase: 'info',
      mode: 'signup',
      message: 'Check your email',
    })
  })

  it('switches auth modes and resets state', () => {
    expect(
      loginReducer(
        { phase: 'error', mode: 'signin', message: 'failed' },
        { type: 'set_mode', mode: 'signup' },
      ),
    ).toEqual({
      phase: 'idle',
      mode: 'signup',
      message: undefined,
    })
  })
})