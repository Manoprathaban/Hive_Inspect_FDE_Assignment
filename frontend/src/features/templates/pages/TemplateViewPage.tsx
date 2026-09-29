import { useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { describeError, isNotFoundError } from '../../../lib/errors'
import type { ImportIssue, Template } from '../types'
import { useTemplate } from '../hooks/useTemplate'
import { useImportIssues } from '../hooks/useImportIssues'
import { useEditScopes } from '../hooks/useEditScopes'
import { TemplateViewer } from '../components/TemplateViewer'
import { DuplicateTemplateDialog } from '../components/DuplicateTemplateDialog'
import { LoadingState } from '../components/states/LoadingState'
import { ErrorState } from '../components/states/ErrorState'

interface ViewLocationState {
  importIssues?: ImportIssue[]
}

/** /templates/:templateId — viewer + inline editor + duplicate + issues (§11/§13/§15). */
export function TemplateViewPage() {
  const params = useParams<{ templateId: string }>()
  const templateId = params.templateId
  const location = useLocation()
  const navigate = useNavigate()

  const { data: template, isLoading, error, refetch } = useTemplate(templateId)
  const [issuesOpen, setIssuesOpen] = useState(false)
  const issues = useImportIssues(templateId, issuesOpen || Boolean((location.state as ViewLocationState | null)?.importIssues?.length))
  const [duplicateOpen, setDuplicateOpen] = useState(false)
  const [bannerDismissed, setBannerDismissed] = useState(false)

  const edits = useEditScopes(templateId ?? '')
  const navigationState = location.state as ViewLocationState | null
  const bannerIssues = navigationState?.importIssues ?? null

  if (isLoading) return <LoadingState label="Loading template" variant="rows" count={6} />

  if (error) {
    const entry = describeError(error)
    if (isNotFoundError(error)) {
      return (
        <ErrorState
          message={entry.message}
          hint={entry.hint}
          backTo={{ to: '/templates', label: 'Back to templates' }}
        />
      )
    }
    return (
      <ErrorState
        message={entry.message}
        hint={entry.hint}
        onRetry={() => refetch(true)}
        backTo={{ to: '/templates', label: 'Back to templates' }}
      />
    )
  }

  if (!template) return <LoadingState label="Loading template" variant="rows" count={6} />

  const current = template as Template

  return (
    <div className="page">
      <nav className="breadcrumb">
        <a href="/templates" onClick={(event) => { event.preventDefault(); navigate('/templates') }}>
          ← Templates
        </a>
      </nav>
      <TemplateViewer
        template={current}
        issues={issues.data ?? []}
        issuesLoading={issues.isLoading}
        issuesOpen={issuesOpen}
        onToggleIssues={() => setIssuesOpen((open) => !open)}
        banner={bannerDismissed ? null : bannerIssues}
        onDismissBanner={() => setBannerDismissed(true)}
        onDuplicate={() => setDuplicateOpen(true)}
        onRenameSection={edits.renameSection}
        onRenameItem={edits.renameItem}
        onEditContent={edits.editComment}
      />
      {duplicateOpen && (
        <DuplicateTemplateDialog
          template={current}
          onClose={() => setDuplicateOpen(false)}
          onDuplicated={(copy) => {
            setDuplicateOpen(false)
            navigate(`/templates/${copy.id}`, { replace: true })
          }}
        />
      )}
    </div>
  )
}