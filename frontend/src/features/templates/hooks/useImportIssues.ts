import { useQuery } from '../../../lib/query'
import { templateApi } from '../api'

/** Import issues for one template, fetched lazily when the panel first opens (§13/§16). */
export function useImportIssues(templateId: string | undefined, enabled: boolean) {
  return useQuery(
    ['import-issues', templateId],
    () => templateApi.getImportIssues(String(templateId)),
    { enabled: enabled && typeof templateId === 'string' },
  )
}