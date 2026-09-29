/** Shared async chrome (FRONTEND_DESIGN §19/§21). */

interface LoadingStateProps {
  label: string
  variant?: 'card' | 'rows'
  count?: number
}

export function LoadingState({ label, variant = 'card', count = 3 }: LoadingStateProps) {
  if (variant === 'rows') {
    return (
      <div className="loading-rows" role="status" aria-label={label}>
        {Array.from({ length: count }, (_, i) => (
          <div key={i} className="skeleton skeleton--row" />
        ))}
        <span className="sr-only">{label}</span>
      </div>
    )
  }
  return (
    <div className="loading-cards" role="status" aria-label={label}>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="skeleton skeleton--card" />
      ))}
      <span className="sr-only">{label}</span>
    </div>
  )
}