import { memo } from 'react'
import { Link } from 'react-router-dom'
import { formatDateTime } from '../../../lib/format'
import type { TemplateSummary } from '../types'

interface TemplateCardProps {
  summary: TemplateSummary
  onDuplicate: (summary: TemplateSummary) => void
}

/** One list card (no counts — counts would be N+1 calls; §10/§25). */
export const TemplateCard = memo(function TemplateCard({ summary, onDuplicate }: TemplateCardProps) {
  return (
    <article className="template-card">
      <h2 className="template-card-name">{summary.name}</h2>
      <p className="template-card-meta">
        <span className="badge badge--meta">{summary.source}</span>
        <span>Updated {formatDateTime(summary.updated_at)}</span>
      </p>
      <footer className="template-card-actions">
        <Link className="button button--primary" to={`/templates/${summary.id}`}>
          Open
        </Link>
        <button type="button" className="button button--secondary" onClick={() => onDuplicate(summary)}>
          Duplicate
        </button>
      </footer>
    </article>
  )
})