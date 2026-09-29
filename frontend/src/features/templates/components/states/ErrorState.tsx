import { Link } from 'react-router-dom'

/** Shared error chrome (FRONTEND_DESIGN §20/§21). */

interface ErrorStateProps {
  message: string
  hint?: string
  onRetry?: () => void
  backTo?: { to: string; label: string }
}

export function ErrorState({ message, hint, onRetry, backTo }: ErrorStateProps) {
  return (
    <div className="error-state" role="alert">
      <p className="error-title">{message}</p>
      {hint && <p className="error-hint">{hint}</p>}
      <div className="error-actions">
        {onRetry && (
          <button type="button" className="button" onClick={onRetry}>
            Retry
          </button>
        )}
        {backTo && (
          <Link className="button button--secondary" to={backTo.to}>
            {backTo.label}
          </Link>
        )}
      </div>
    </div>
  )
}