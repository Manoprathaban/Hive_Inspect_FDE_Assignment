import { describe, expect, it, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { QueryProvider, createQueryManager } from '../../../lib/query'
import { useEditScopes } from './useEditScopes'

const renameSection = vi.fn().mockResolvedValue(undefined)
const renameItem = vi.fn().mockResolvedValue(undefined)
const editComment = vi.fn().mockResolvedValue(undefined)

vi.mock('../api', () => ({
  templateApi: {
    renameSection: (...args: unknown[]) => renameSection(...args),
    renameItem: (...args: unknown[]) => renameItem(...args),
    editComment: (...args: unknown[]) => editComment(...args),
  },
  validateName: () => null,
  validateContent: () => null,
}))

function wrapper({ children }: { children: ReactNode }) {
  return <QueryProvider manager={createQueryManager()}>{children}</QueryProvider>
}

const TEMPLATE_ID = '11111111-1111-1111-1111-111111111111'

describe('useEditScopes callback identity', () => {
  beforeEach(() => {
    renameSection.mockClear()
    renameItem.mockClear()
    editComment.mockClear()
  })

  // Regression guard. These three callbacks are handed to memo()'d SectionView / ItemView /
  // CommentView. A fresh closure per render makes every memo() miss, which re-renders all
  // 392 comment rows of the canonical template on any unrelated state change (opening the
  // issues panel, dismissing the banner, a mutation flipping isPending).
  it('returns referentially stable callbacks across re-renders', () => {
    const { result, rerender } = renderHook(() => useEditScopes(TEMPLATE_ID), { wrapper })

    const first = result.current
    expect(first.renameSection).toBeTypeOf('function')

    rerender()
    const second = result.current

    expect(second.renameSection).toBe(first.renameSection)
    expect(second.renameItem).toBe(first.renameItem)
    expect(second.editComment).toBe(first.editComment)
  })

  it('keeps callbacks stable when a mutation flips isPending', async () => {
    const { result, rerender } = renderHook(() => useEditScopes(TEMPLATE_ID), { wrapper })

    const before = result.current
    const pending = before.editComment('comment-1', 'edited')

    // Re-render while the mutation is in flight, as React would after setState.
    rerender()
    expect(result.current.isPending).toBe(true)
    expect(result.current.editComment).toBe(before.editComment)

    await pending
    rerender()
    expect(result.current.isPending).toBe(false)
    expect(result.current.editComment).toBe(before.editComment)
  })

  // Behaviour must be unchanged by the useCallback wrapping.
  it('still routes each callback to the right endpoint with the right arguments', async () => {
    const { result } = renderHook(() => useEditScopes(TEMPLATE_ID), { wrapper })

    await result.current.renameSection('section-1', 'Exterior')
    await result.current.renameItem('item-1', 'Siding')
    await result.current.editComment('comment-1', 'new text')

    expect(renameSection).toHaveBeenCalledWith(TEMPLATE_ID, 'section-1', 'Exterior')
    expect(renameItem).toHaveBeenCalledWith(TEMPLATE_ID, 'item-1', 'Siding')
    expect(editComment).toHaveBeenCalledWith(TEMPLATE_ID, 'comment-1', 'new text')
  })
})
