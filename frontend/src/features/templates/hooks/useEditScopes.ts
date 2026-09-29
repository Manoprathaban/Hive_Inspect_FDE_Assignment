import { useMutation, useQueryStore } from '../../../lib/query'
import type { QueryKey } from '../../../lib/query'
import type { Template } from '../types'
import { templateApi } from '../api'

interface EditScopesValue {
  renameSection: (sectionId: string, name: string) => Promise<void>
  renameItem: (itemId: string, name: string) => Promise<void>
  editComment: (commentId: string, content: string) => Promise<void>
  isPending: boolean
  lastError: unknown
}

function updateTemplateField(
  current: Template | undefined,
  kind: 'section' | 'item' | 'comment',
  id: string,
  value: string,
): Template | undefined {
  if (!current) return current
  if (kind === 'section') {
    return {
      ...current,
      sections: current.sections.map((s) => (s.id === id ? { ...s, name: value } : s)),
    }
  }
  if (kind === 'item') {
    return {
      ...current,
      sections: current.sections.map((s) => ({
        ...s,
        items: s.items.map((i) => (i.id === id ? { ...i, name: value } : i)),
      })),
    }
  }
  return {
    ...current,
    sections: current.sections.map((s) => ({
      ...s,
      items: s.items.map((i) => ({
        ...i,
        comments: i.comments.map((c) => (c.id === id ? { ...c, content: value } : c)),
      })),
    })),
  }
}

/** PATCH mutations for section/item/comment edits. Apply the confirmed value to the
 * cache immediately, then refresh the template from the backend (design D7). */
export function useEditScopes(templateId: string): EditScopesValue {
  const store = useQueryStore()
  const key: QueryKey = ['template', templateId]

  function applyAndRefresh(kind: 'section' | 'item' | 'comment', id: string, value: string) {
    store.update(key, (current) => updateTemplateField(current as Template | undefined, kind, id, value))
    store.refresh([key])
  }

  const renameSection = useMutation(
    async ({ sectionId, name }: { sectionId: string; name: string }) => {
      await templateApi.renameSection(templateId, sectionId, name)
      applyAndRefresh('section', sectionId, name)
    },
  )

  const renameItem = useMutation(async ({ itemId, name }: { itemId: string; name: string }) => {
    await templateApi.renameItem(templateId, itemId, name)
    applyAndRefresh('item', itemId, name)
  })

  const editComment = useMutation(
    async ({ commentId, content }: { commentId: string; content: string }) => {
      await templateApi.editComment(templateId, commentId, content)
      applyAndRefresh('comment', commentId, content)
    },
  )

  const lastError = renameSection.error ?? renameItem.error ?? editComment.error

  return {
    renameSection: (sectionId, name) => renameSection.run({ sectionId, name }),
    renameItem: (itemId, name) => renameItem.run({ itemId, name }),
    editComment: (commentId, content) => editComment.run({ commentId, content }),
    isPending: renameSection.isPending || renameItem.isPending || editComment.isPending,
    lastError,
  }
}