import { useQuery } from '../../../lib/query'
import { templateApi } from '../api'

/** Server state for one template's full hierarchy ('template/<id>', §16). */
export function useTemplate(templateId: string | undefined) {
  const enabled = typeof templateId === 'string'
  return useQuery(['template', templateId], () => templateApi.getTemplate(String(templateId)), {
    enabled,
  })
}