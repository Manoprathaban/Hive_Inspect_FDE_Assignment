import { describe, expect, it } from 'vitest'
import { loginReducer } from './loginMachine'

describe('loginReducer', () => {
  it('starts idle', () => {
    expect(loginReducer({ phase: 'idle' }, { type: 'reset' })).toEqual({ phase: 'idle' })
  })

  it('moves to submitting and clears any prior error', () => {
    const state = { phase: 'error' as const, message: 'bad password' }
    expect(loginReducer(state, { type: 'submit' })).toEqual({ phase: 'submitting' })
  })

  it('moves to authenticated on success', () => {
    expect(loginReducer({ phase: 'submitting' }, { type: 'success' })).toEqual({ phase: 'authenticated' })
  })

  it('records the error message on failure', () => {
    expect(loginReducer({ phase: 'submitting' }, { type: 'error', message: 'Sign-in failed' })).toEqual({
      phase: 'error',
      message: 'Sign-in failed',
    })
  })
})