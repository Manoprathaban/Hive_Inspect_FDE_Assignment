/**
 * Login UI-state machine (FRONTEND_DESIGN §7/§21, loginMachine.ts). Pure reducer so the
 * phase transitions are unit-testable; the submit/success/error transitions are wired by
 * the page.
 */

import { useCallback, useReducer } from 'react'

export type LoginPhase = 'idle' | 'submitting' | 'error' | 'info' | 'authenticated'
export type AuthMode = 'signin' | 'signup'

export interface LoginState {
  phase: LoginPhase
  mode: AuthMode
  message?: string
}

export type LoginAction =
  | { type: 'submit' }
  | { type: 'success' }
  | { type: 'error'; message?: string }
  | { type: 'info'; message: string }
  | { type: 'set_mode'; mode: AuthMode }
  | { type: 'reset' }

export function loginReducer(state: LoginState, action: LoginAction): LoginState {
  switch (action.type) {
    case 'submit':
      return { ...state, phase: 'submitting', message: undefined }
    case 'success':
      return { ...state, phase: 'authenticated', message: undefined }
    case 'error':
      return { ...state, phase: 'error', message: action.message }
    case 'info':
      return { ...state, phase: 'info', message: action.message }
    case 'set_mode':
      return { phase: 'idle', mode: action.mode, message: undefined }
    case 'reset':
      return { phase: 'idle', mode: state.mode, message: undefined }
  }
}

export function useLoginMachine(initialMode: AuthMode = 'signin') {
  const [state, dispatch] = useReducer(loginReducer, { phase: 'idle', mode: initialMode })

  const submit = useCallback(() => dispatch({ type: 'submit' }), [])
  const succeed = useCallback(() => dispatch({ type: 'success' }), [])
  const fail = useCallback((message?: string) => dispatch({ type: 'error', message }), [])
  const showInfo = useCallback((message: string) => dispatch({ type: 'info', message }), [])
  const setMode = useCallback((mode: AuthMode) => dispatch({ type: 'set_mode', mode }), [])
  const reset = useCallback(() => dispatch({ type: 'reset' }), [])

  return { state, submit, succeed, fail, showInfo, setMode, reset }
}