import { useState } from 'react'
import { useQueryStore } from '../../../lib/query'
import type { ImportIssue, ImportResult } from '../types'
import { templateApi } from '../api'

export type ImportPhase = 'idle' | 'uploading' | 'importing' | 'done' | 'error'

export interface ImportState {
  runImport: (file: File) => Promise<ImportResult>
  phase: ImportPhase
  progress: number
  error: unknown
  result: { templateId: string; issues: ImportIssue[] } | null
  clear: () => void
}

/** Import mutation: upload with progress, seed the template cache, invalidate the list. */
export function useImport(): ImportState {
  const store = useQueryStore()
  const [phase, setPhase] = useState<ImportPhase>('idle')
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<unknown>(undefined)
  const [result, setResult] = useState<{ templateId: string; issues: ImportIssue[] } | null>(null)

  async function runImport(file: File): Promise<ImportResult> {
    setPhase('uploading')
    setProgress(0)
    setError(undefined)
    setResult(null)
    try {
      const res = await templateApi.importFile(file, (fraction) => {
        setProgress(fraction)
        if (fraction >= 1) setPhase('importing')
      })
      store.update(['template', res.template.id], () => res.template)
      store.invalidate([['templates']])
      setResult({ templateId: res.template.id, issues: res.issues })
      setPhase('done')
      return res
    } catch (caught) {
      setError(caught)
      setPhase('error')
      throw caught
    }
  }

  function clear() {
    setPhase('idle')
    setProgress(0)
    setError(undefined)
    setResult(null)
  }

  return { runImport, phase, progress, error, result, clear }
}