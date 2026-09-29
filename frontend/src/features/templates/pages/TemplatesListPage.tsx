import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { ImportIssue, Template, TemplateSummary } from '../types'
import { useTemplateList } from '../hooks/useTemplateList'
import { TemplateList } from '../components/TemplateList'
import { ImportDialog } from '../components/ImportDialog'
import { DuplicateTemplateDialog } from '../components/DuplicateTemplateDialog'

/** /templates — list + import dialog + duplicate dialog (§10/§12/§15). */
export function TemplatesListPage() {
  const { data, isLoading, error, refetch } = useTemplateList()
  const [importOpen, setImportOpen] = useState(false)
  const [duplicateTarget, setDuplicateTarget] = useState<TemplateSummary | null>(null)
  const navigate = useNavigate()

  function handleImported(templateId: string, issues: ImportIssue[]) {
    setImportOpen(false)
    navigate(`/templates/${templateId}`, { state: { importIssues: issues } })
  }

  function handleDuplicated(copy: Template) {
    setDuplicateTarget(null)
    navigate(`/templates/${copy.id}`)
  }

  return (
    <div className="page">
      <TemplateList
        summaries={data ?? []}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch(true)}
        onImport={() => setImportOpen(true)}
        onDuplicate={setDuplicateTarget}
      />
      {importOpen && <ImportDialog onClose={() => setImportOpen(false)} onImported={handleImported} />}
      {duplicateTarget && (
        <DuplicateTemplateDialog
          template={duplicateTarget}
          onClose={() => setDuplicateTarget(null)}
          onDuplicated={handleDuplicated}
        />
      )}
    </div>
  )
}