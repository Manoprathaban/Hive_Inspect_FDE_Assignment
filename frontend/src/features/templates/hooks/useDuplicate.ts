import { useMutation, useQueryStore } from '../../../lib/query'
import type { Template } from '../types'
import { templateApi } from '../api'

interface DuplicateValue {
  duplicate: (name?: string) => Promise<Template>
  isPending: boolean
  error: unknown
}

/** Duplicate mutation: seed the copy's cache from the 201 response, invalidate the list. */
export function useDuplicate(templateId: string): DuplicateValue {
  const store = useQueryStore()

  const mutation = useMutation(async (name?: string) => {
    const copy = await templateApi.duplicateTemplate(templateId, name)
    store.update(['template', copy.id], () => copy)
    store.invalidate([['templates']])
    return copy
  })

  return { duplicate: mutation.run, isPending: mutation.isPending, error: mutation.error }
}