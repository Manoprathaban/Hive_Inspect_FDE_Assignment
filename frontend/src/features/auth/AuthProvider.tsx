/**
 * Auth state (:FRONTEND_DESIGN §7). Holds the session, exposes useSession(), keeps the
 * API client's token in sync, and clears the whole server-state cache on logout so no
 * data crosses users. When Supabase is not configured (dev), falls back to a
 * deterministic dev session exactly mirroring the production flow.
 */

/* eslint-disable react/only-export-components -- the provider and its useSession() hook
   belong together; the fast-refresh advisory does not apply. */
import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { createClient } from '@supabase/supabase-js'
import { setAuthToken, setUnauthorizedHandler } from '../../lib/apiClient'
import { useQueryStore } from '../../lib/query'

export interface Session {
  accessToken: string
}

export interface SignupResult {
  sessionCreated: boolean
  message?: string
}

interface AuthContextValue {
  session: Session | null
  isInitializing: boolean
  isDevMode: boolean
  login: (email: string, password: string) => Promise<void>
  signup: (email: string, password: string) => Promise<SignupResult>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL as string | undefined
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined

function buildClient() {
  if (SUPABASE_URL && SUPABASE_ANON_KEY) {
    return createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
  }
  return null
}

function AuthProvider({ children }: { children: ReactNode }) {
  // The Supabase client is built once and lives for the provider's lifetime.
  const [client] = useState(buildClient)
  const store = useQueryStore()

  const [state, setState] = useState({ session: null as Session | null, isInitializing: true })

  const logout = useCallback(async () => {
    if (client) {
      try {
        await client.auth.signOut()
      } catch {
        // Ignore Supabase logout errors (e.g. 403 on expired sessions) so local state clears
      }
    }
    setAuthToken(null)
    store.clearAll()
    setState({ session: null, isInitializing: false })
  }, [client, store])

  const login = useCallback(async (email: string, password: string) => {
    if (!client) {
      setState({ session: { accessToken: 'dev-token' }, isInitializing: false })
      return
    }
    const { data, error } = await client.auth.signInWithPassword({ email, password })
    if (error) throw error
    const accessToken = data.session?.access_token
    if (!accessToken) throw new Error('No session returned from Supabase.')
    setState({ session: { accessToken }, isInitializing: false })
  }, [client])

  const signup = useCallback(
    async (email: string, password: string): Promise<SignupResult> => {
      if (!client) {
        setState({ session: { accessToken: 'dev-token' }, isInitializing: false })
        return { sessionCreated: true }
      }
      const { data, error } = await client.auth.signUp({ email, password })
      if (error) throw error
      const accessToken = data.session?.access_token
      if (accessToken) {
        setState({ session: { accessToken }, isInitializing: false })
        return { sessionCreated: true }
      }
      return {
        sessionCreated: false,
        message: 'Account created! Please check your email to confirm your sign up.',
      }
    },
    [client],
  )

  // Register the 401 handler once: any API 401 signs out (never shown raw).
  useEffect(() => {
    const handler = () => {
      void logout()
    }
    setUnauthorizedHandler(handler)
    return () => setUnauthorizedHandler(null)
  }, [logout])

  // Keep the API client's bearer token in sync with the session.
  useEffect(() => {
    setAuthToken(state.session?.accessToken ?? null)
    if (state.session === null && !state.isInitializing) {
      store.clearAll()
    }
  }, [state.session, state.isInitializing, store])

  // Restore an existing Supabase session, then subscribe to auth changes. This is a
  // genuine external-system sync, so the resulting state update belongs in an effect.
  /* eslint-disable react/set-state-in-effect */
  useEffect(() => {
    if (!client) {
      setState({ session: null, isInitializing: false })
      return
    }
    let cancelled = false
    client.auth
      .getSession()
      .then(({ data }) => {
        if (cancelled) return
        const accessToken = data.session?.access_token
        setState({ session: accessToken ? { accessToken } : null, isInitializing: false })
      })
      .catch(() => {
        if (!cancelled) setState({ session: null, isInitializing: false })
      })

    const {
      data: { subscription },
    } = client.auth.onAuthStateChange((_event, session) => {
      if (cancelled) return
      const accessToken = session?.access_token
      setState({ session: accessToken ? { accessToken } : null, isInitializing: false })
    })

    return () => {
      cancelled = true
      subscription.unsubscribe()
    }
  }, [client])
  /* eslint-enable react/set-state-in-effect */

  const value: AuthContextValue = {
    session: state.session,
    isInitializing: state.isInitializing,
    isDevMode: !client,
    login,
    signup,
    logout,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useSession(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useSession must be used inside an AuthProvider')
  return context
}

export default AuthProvider