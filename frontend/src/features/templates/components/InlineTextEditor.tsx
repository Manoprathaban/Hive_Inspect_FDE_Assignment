/**
 * Inline editor for one value (name or content) — FRONTEND_DESIGN §11/§14/§21. Owns the
 * draft text so editing state never leaks into the viewer; validates client-side,
 * disables double-submit while saving, collapses with a brief "Saved" affordance on
 * success, and keeps the user's text + inline error on failure (never silently
 * discarded).
 */

import { useEffect, useId, useRef, useState } from 'react'
import type { KeyboardEvent, Ref } from 'react'
import { describeError } from '../../../lib/errors'
import { validateContent, validateName } from '../api'

type Mode = 'name' | 'content'

interface InlineTextEditorProps {
  value: string
  onSave: (value: string) => Promise<void>
  mode: Mode
  label: string
  disabled?: boolean
}

export function InlineTextEditor({ value, onSave, mode, label, disabled }: InlineTextEditorProps) {
  const [editing, setEditing] = useState(false)
  // `draft` is only read while editing; openEditor seeds it from the current value,
  // so no effect is needed to resync when the server value changes.
  const [draft, setDraft] = useState(value)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null)
  const errorId = `${useId()}-error`
  const savedTimer = useRef<number | null>(null)

  useEffect(() => {
    if (editing) inputRef.current?.focus()
  }, [editing])

  useEffect(() => {
    return () => {
      if (savedTimer.current !== null) window.clearTimeout(savedTimer.current)
    }
  }, [])

  function openEditor() {
    if (disabled) return
    setDraft(value)
    setError(null)
    setEditing(true)
  }

  function cancel() {
    setEditing(false)
    setDraft(value)
    setError(null)
  }

  function validate(): string | null {
    return mode === 'name' ? validateName(draft) : validateContent(draft)
  }

  async function handleSave() {
    const problem = validate()
    if (problem) {
      setError(problem)
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onSave(mode === 'name' ? draft.trim() : draft)
      setSaving(false)
      setSaved(true)
      savedTimer.current = window.setTimeout(() => {
        savedTimer.current = null
        setSaved(false)
        setEditing(false)
      }, 1200)
    } catch (caught) {
      setSaving(false)
      setError(describeError(caught).message)
    }
  }

  function handleKeyDown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      event.preventDefault()
      cancel()
      return
    }
    if (mode === 'name' && event.key === 'Enter') {
      event.preventDefault()
      void handleSave()
    }
  }

  if (!editing) {
    return (
      <span className="inline-editor-view">
        {value ? (
          <span className={mode === 'content' ? 'inline-editor-content' : ''}>{value}</span>
        ) : (
          <span className="inline-editor-placeholder">No text</span>
        )}
        <button
          type="button"
          className="icon-button"
          aria-label={`Edit ${label}`}
          onClick={openEditor}
          disabled={disabled}
        >
          ✎
        </button>
      </span>
    )
  }

  return (
    <span className="inline-editor">
      {mode === 'name' ? (
        <input
          ref={inputRef as Ref<HTMLInputElement>}
          type="text"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          aria-label={label}
          aria-describedby={error ? errorId : undefined}
          disabled={saving}
        />
      ) : (
        <textarea
          ref={inputRef as Ref<HTMLTextAreaElement>}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={Math.min(6, Math.max(2, draft.split('\n').length))}
          aria-label={label}
          aria-describedby={error ? errorId : undefined}
          disabled={saving}
        />
      )}
      <button type="button" className="icon-button" aria-label={`Save ${label}`} onClick={() => void handleSave()} disabled={saving}>
        ✓
      </button>
      <button type="button" className="icon-button" aria-label={`Cancel editing ${label}`} onMouseDown={(event) => event.preventDefault()} onClick={cancel} disabled={saving}>
        ✕
      </button>
      {saving && <span className="saving">Saving…</span>}
      {saved && <span className="saved">
        ✓ Saved
      </span>}
      {error && (
        <span className="field-error" id={errorId} role="alert">
          {error}
        </span>
      )}
    </span>
  )
}