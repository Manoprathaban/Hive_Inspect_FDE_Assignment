import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { describeError } from '../../../lib/errors'
import { useModalFocus } from '../../../lib/useModalFocus'
import type { ImportIssue } from '../types'
import { clientFileError } from '../api'
import { useImport } from '../hooks/useImport'

interface ImportDialogProps {
  onClose: () => void
  onImported: (templateId: string, issues: ImportIssue[]) => void
}

/** One-shot import flow (§12): choose → client checks → upload with progress → navigate. */
export function ImportDialog({ onClose, onImported }: ImportDialogProps) {
  const { runImport, phase, progress, error } = useImport()
  const [clientError, setClientError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement | null>(null)
  const dialogRef = useModalFocus<HTMLDivElement>()

  const busy = phase === 'uploading' || phase === 'importing'

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && !busy) onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [busy, onClose])

  async function handleFilePick(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    const problem = clientFileError(file)
    if (problem) {
      setClientError(problem)
      return
    }
    setClientError(null)
    try {
      const result = await runImport(file)
      onImported(result.template.id, result.issues)
    } catch {
      /* error surface is the dialog's inline message */
    }
  }

  const importError = phase === 'error' ? describeError(error) : null

  return (
    <div className="modal-backdrop" onClick={busy ? undefined : onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="Import a template"
        ref={dialogRef}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-heading">
          <h2>Import a template</h2>
          <button type="button" className="icon-button" aria-label="Close" onClick={onClose} disabled={busy}>
            ✕
          </button>
        </div>
        <p className="muted">Choose a Spectora worksheet export (.xlsx or .xml). Content is read on the server.</p>

        {phase === 'idle' && (
          <>
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xml"
              onChange={handleFilePick}
              aria-label="Worksheet file"
            />
            {clientError && (
              <p className="field-error" role="alert">
                {clientError}
              </p>
            )}
          </>
        )}

        {phase === 'uploading' && (
          <div className="upload-progress">
            <div className="progress-track">
              <div className="progress-bar" style={{ width: `${Math.round(progress * 100)}%` }} />
            </div>
            <p className="muted">
              {progress < 1 ? `Uploading… ${Math.round(progress * 100)}%` : 'Importing…'}
            </p>
          </div>
        )}

        {phase === 'importing' && <p className="muted">Importing…</p>}

        {importError && (
          <p className="field-error" role="alert">
            {importError.message}
            {importError.hint ? <span className="error-hint-inline"> {importError.hint}</span> : null}
          </p>
        )}

        <div className="modal-footer">
          <button type="button" className="button button--secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}