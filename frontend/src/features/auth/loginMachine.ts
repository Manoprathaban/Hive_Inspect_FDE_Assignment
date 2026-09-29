/**
 * Login UI-state machine (FRONTEND_DESIGN §7/§21, loginMachine.ts). Pure reducer so the
 * phase transitions are unit-testable; the submit/success/error transitions are wired by
 * the page.
 */

import { useCallback, useReducer } from 'react'

export type LoginPhase = 'idle' | 'submitting' | 'error' | 'authenticated'

export interface LoginState {
  phase: LoginPhase
  message?: string
}

export type LoginAction =
  | { type: 'submit' }
  | { type: 'success' }
  | { type: 'error'; message?: string }
  | { type: 'reset' }

export function loginReducer(_state: LoginState, action: LoginAction): LoginState {
  switch (action.type) {
    case 'submit':
      return { phase: 'submitting' }
    case 'success':
      return { phase: 'authenticated' }
    case 'error':
      return { phase: 'error', message: action.message }
    case 'reset':
      return { phase: 'idle' }
  }
}

export function useLoginMachine() {
  const [state, dispatch] = useReducer(loginReducer, { phase: 'idle' })

  const submit = useCallback(() => dispatch({ type: 'submit' }), [])
  const succeed = useCallback(() => dispatch({ type: 'success' }), [])
  const fail = useCallback((message?: string) => dispatch({ type: 'error', message }), [])
  const reset = useCallback(() => dispatch({ type: 'reset' }), [])

  return { state, submit, succeed, fail, reset }
}