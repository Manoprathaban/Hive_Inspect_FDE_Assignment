import { memo } from 'react'
import type { ImportIssue } from '../types'
import { IssueBadge } from './IssueBadge'

interface ImportIssuesPanelProps {
  issues: ImportIssue[]
  isLoading: boolean
  onClose: () => void
}

const MAX_RAW_VALUE_CHARS = 120

/** The "what was not imported, and why?" panel (§13). Never console-only. */
export const ImportIssuesPanel = memo(function ImportIssuesPanel({
  issues,
  isLoading,
  onClose,
}: ImportIssuesPanelProps) {
  return (
    <aside className="issues-panel" aria-label="Import issues">
      <div className="issues-panel-heading">
        <h2>Import issues</h2>
        <button type="button" className="icon-button" aria-label="Close import issues" onClick={onClose}>
          ✕
        </button>
      </div>
      {isLoading ? (
        <p className="muted">Loading issues…</p>
      ) : issues.length === 0 ? (
        <p className="muted">No issues recorded for this template.</p>
      ) : (
        <ul className="issues-list">
          {issues.map((issue) => (
            <li key={issue.id} className="issue-row">
              <div className="issue-row-main">
                <IssueBadge issue={issue} />
                <span className="issue-type">{issue.issue_type}</span>
              </div>
              <p className="issue-message">{issue.message}</p>
              {(issue.source_field !== null || issue.source_row !== null) && (
                <p className="issue-meta">
                  {issue.source_field !== null && <code>{issue.source_field}</code>}
                  {issue.source_row !== null && <code>row {issue.source_row}</code>}
                </p>
              )}
              {issue.raw_value !== null && (
                <p className="issue-raw">
                  <code>
                    {issue.raw_value.length > MAX_RAW_VALUE_CHARS
                      ? `${issue.raw_value.slice(0, MAX_RAW_VALUE_CHARS)}…`
                      : issue.raw_value}
                  </code>
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
})