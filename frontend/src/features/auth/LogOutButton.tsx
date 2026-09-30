/**
 * "Log out" control (:FRONTEND_DESIGN §7 — logout calls `supabase.auth.signOut()`, clears
 * the whole server-state cache, and routes to `/login`).
 *
 * Rendered from the app shell rather than a page, so it is reachable from every protected
 * route (both `/templates` and `/templates/:templateId`) instead of only one screen. It
 * renders nothing without a session, mirroring `DevBadge`.
 *
 * The navigation to `/login` is explicit: `AuthProvider` has no router access, and the
 * design requires logout to land on the login route. `RequireAuth` would redirect anyway,
 * but doing it here keeps the intent local and makes the destination deterministic (the
 * guard preserves a `from` location that logout should not resurrect).
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useSession } from './AuthProvider'

export function LogOutButton() {
  const { session, logout } = useSession()
  const navigate = useNavigate()
  const [isPending, setIsPending] = useState(false)

  // No session means there is nothing to sign out of, and the control would be inert.
  if (!session) return null

  const handleClick = async () => {
    // Guard against a double click firing two signOut calls while the first is in flight.
    if (isPending) return
    setIsPending(true)
    try {
      await logout()
      navigate('/login', { replace: true })
    } finally {
      // Reset unconditionally so the control cannot get stuck if logout ever fails. On the
      // success path this lands on an already-unmounted component, which React ignores.
      setIsPending(false)
    }
  }

  return (
    <button
      type="button"
      className="button button--secondary"
      onClick={handleClick}
      disabled={isPending}
    >
      {isPending ? 'Logging out…' : 'Log out'}
    </button>
  )
}
