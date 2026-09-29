import { useQuery } from '../../../lib/query'
import { templateApi } from '../api'

/** Server state for the template list ('templates' key, §16). */
export function useTemplateList() {
  return useQuery(['templates'], () => templateApi.listTemplates())
}