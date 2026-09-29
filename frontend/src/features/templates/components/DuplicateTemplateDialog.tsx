import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { describeError } from '../../../lib/errors'
import type { Template } from '../types'
import { validateName } from '../api'
import { useDuplicate } from '../hooks/useDuplicate'

interface DuplicateTemplateDialogProps {
  /** Only id + name are needed to seed the dialog and build the duplicate call. */
  template: { id: string; name: string }
  onClose: () => void
  onDuplicated: (copy: Template) => void
}

/** Confirmation dialog for duplication (§15): optional name, pre-filled <source> (Copy). */
export function DuplicateTemplateDialog({
  template,
  onClose,
  onDuplicated,
}: DuplicateTemplateDialogProps) {
  const { duplicate, isPending, error } = useDuplicate(template.id)
  const [name, setName] = useState(`${template.name} (Copy)`)
  const [nameError, setNameError] = useState<string | null>(null)

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && !isPending) onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [isPending, onClose])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmed = name.trim()
    const problem = validateName(trimmed)
    if (problem) {
      setNameError(problem)
      return
    }
    setNameError(null)
    try {
      const copy = await duplicate(trimmed)
      onDuplicated(copy)
    } catch {
      /* error surface below */
    }
  }

  const duplicateError = error ? describeError(error) : null

  return (
    <div className="modal-backdrop" onClick={isPending ? undefined : onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="Duplicate template"
        onClick={(event) => event.stopPropagation()}
      >
        <form onSubmit={handleSubmit}>
          <div className="modal-heading">
            <h2>Duplicate template</h2>
            <button type="button" className="icon-button" aria-label="Close" onClick={onClose} disabled={isPending}>
              ✕
            </button>
          </div>
          <p className="muted">
            Creates an independent copy of “{template.name}”. Later edits of the copy do not touch the
            original.
          </p>
          <label htmlFor="duplicate-name">Copy name</label>
          <input
            id="duplicate-name"
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={200}
            disabled={isPending}
          />
          {nameError && (
            <p className="field-error" role="alert">
              {nameError}
            </p>
          )}
          {duplicateError && (
            <p className="field-error" role="alert">
              {duplicateError.message}
              {duplicateError.hint ? <span className="error-hint-inline"> {duplicateError.hint}</span> : null}
            </p>
          )}
          <div className="modal-footer">
            <button type="button" className="button button--secondary" onClick={onClose} disabled={isPending}>
              Cancel
            </button>
            <button type="submit" className="button button--primary" disabled={isPending}>
              {isPending ? 'Duplicating…' : 'Duplicate'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}