import { memo } from 'react'
import { formatDateTime } from '../../../lib/format'
import type { ImportIssue, Template } from '../types'
import { ImportIssuesPanel } from './ImportIssuesPanel'
import { SectionView } from './SectionView'

interface TemplateViewerProps {
  template: Template
  issues: ImportIssue[]
  issuesLoading: boolean
  issuesOpen: boolean
  onToggleIssues: () => void
  banner: ImportIssue[] | null
  onDismissBanner: () => void
  onDuplicate: () => void
  onRenameSection: (sectionId: string, name: string) => Promise<void>
  onRenameItem: (itemId: string, name: string) => Promise<void>
  onEditContent: (commentId: string, content: string) => Promise<void>
}

/** Core screen (§11): header, issues banner, ordered hierarchy, issues side rail. */
export const TemplateViewer = memo(function TemplateViewer({
  template,
  issues,
  issuesLoading,
  issuesOpen,
  onToggleIssues,
  banner,
  onDismissBanner,
  onDuplicate,
  onRenameSection,
  onRenameItem,
  onEditContent,
}: TemplateViewerProps) {
  return (
    <div className="viewer">
      <header className="viewer-header">
        <div>
          <h1>{template.name}</h1>
          <p className="viewer-meta">
            <span className="badge badge--meta">{template.source}</span>
            {template.copied_from_id !== null && <span className="badge badge--meta">copy</span>}
            <span>Updated {formatDateTime(template.updated_at)}</span>
            {template.source_filename !== null && <span className="muted">{template.source_filename}</span>}
          </p>
        </div>
        <div className="viewer-actions">
          <button type="button" className="button button--secondary" onClick={onToggleIssues}>
            {issuesOpen ? 'Hide issues' : `Import issues${issues.length > 0 ? ` (${issues.length})` : ''}`}
          </button>
          <button type="button" className="button button--primary" onClick={onDuplicate}>
            Duplicate
          </button>
        </div>
      </header>

      {banner && banner.length > 0 && (
        <div className="issue-banner" role="status">
          <span>
            {banner.length} {banner.length === 1 ? 'item was' : 'items were'} skipped or not fully
            imported. Review the import issues.
          </span>
          <button type="button" className="button button--secondary" onClick={onDismissBanner}>
            Dismiss
          </button>
        </div>
      )}

      <div className={`viewer-layout${issuesOpen ? ' viewer-layout--with-panel' : ''}`}>
        <main className="viewer-main">
          {template.sections.length === 0 ? (
            <p className="muted">This template has no sections.</p>
          ) : (
            template.sections.map((section) => (
              <SectionView
                key={section.id}
                section={section}
                onRenameSection={onRenameSection}
                onRenameItem={onRenameItem}
                onEditContent={onEditContent}
              />
            ))
          )}
        </main>
        {issuesOpen && (
          <ImportIssuesPanel issues={issues} isLoading={issuesLoading} onClose={onToggleIssues} />
        )}
      </div>
    </div>
  )
})