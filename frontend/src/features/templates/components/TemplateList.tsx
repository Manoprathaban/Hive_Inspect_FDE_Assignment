import { memo } from 'react'
import { describeError } from '../../../lib/errors'
import type { TemplateSummary } from '../types'
import { TemplateCard } from './TemplateCard'
import { LoadingState } from './states/LoadingState'
import { ErrorState } from './states/ErrorState'

interface TemplateListProps {
  summaries: TemplateSummary[]
  isLoading: boolean
  error: unknown
  onRetry: () => void
  onImport: () => void
  onDuplicate: (summary: TemplateSummary) => void
}

/** List page body (§10): skeleton / error / empty / grid. */
export const TemplateList = memo(function TemplateList({
  summaries,
  isLoading,
  error,
  onRetry,
  onImport,
  onDuplicate,
}: TemplateListProps) {
  return (
    <div>
      <header className="page-header">
        <h1>Templates</h1>
        <button type="button" className="button button--primary" onClick={onImport}>
          Import a template
        </button>
      </header>

      {isLoading && <LoadingState label="Loading templates" variant="card" count={3} />}

      {!isLoading && Boolean(error) && (
        <ErrorState message={describeError(error).message} hint={describeError(error).hint} onRetry={onRetry} />
      )}

      {!isLoading && !error && summaries.length === 0 && (
        <div className="empty-state">
          <p>No templates yet.</p>
          <button type="button" className="button button--primary" onClick={onImport}>
            Import a template
          </button>
        </div>
      )}

      {!isLoading && !error && summaries.length > 0 && (
        <div className="template-grid">
          {summaries.map((summary) => (
            <TemplateCard key={summary.id} summary={summary} onDuplicate={onDuplicate} />
          ))}
        </div>
      )}
    </div>
  )
})