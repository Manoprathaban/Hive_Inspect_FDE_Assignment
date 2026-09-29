import { memo } from 'react'
import type { ImportIssue } from '../types'

interface IssueBadgeProps {
  issue: ImportIssue
}

const SEVERITY_LABELS: Record<ImportIssue['severity'], string> = {
  info: 'Info',
  warning: 'Warning',
  error: 'Error',
}

const TYPE_ICONS: Record<ImportIssue['issue_type'], string> = {
  SOURCE_DATA_MISSING: '⌀',
  UNSUPPORTED_CONTENT: '⊘',
  INVALID_SOURCE_DATA: '!',
}

/** Severity chip with icon + color + text (never color alone, §13/§26). */
export const IssueBadge = memo(function IssueBadge({ issue }: IssueBadgeProps) {
  return (
    <span className={`issue-badge issue-badge--${issue.severity}`}>
      <span className="issue-badge-icon" aria-hidden="true">
        {TYPE_ICONS[issue.issue_type]}
      </span>
      <span className="issue-badge-text">{SEVERITY_LABELS[issue.severity]}</span>
    </span>
  )
})