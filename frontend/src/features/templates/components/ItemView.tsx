import { memo } from 'react'
import type { Item } from '../types'
import { CommentView } from './CommentView'
import { InlineTextEditor } from './InlineTextEditor'

interface ItemViewProps {
  item: Item
  onRenameItem: (itemId: string, name: string) => Promise<void>
  onEditContent: (commentId: string, content: string) => Promise<void>
}

/** One checklist item, ordered, with its comments nested. */
export const ItemView = memo(function ItemView({ item, onRenameItem, onEditContent }: ItemViewProps) {
  return (
    <li className="item-row">
      <h4 className="item-heading">
        <InlineTextEditor
          value={item.name}
          onSave={(name) => onRenameItem(item.id, name)}
          mode="name"
          label={`item "${item.name}"`}
        />
      </h4>
      {item.comments.length > 0 && (
        <ul className="comment-list">
          {item.comments.map((comment) => (
            <CommentView key={comment.id} comment={comment} onEditContent={onEditContent} />
          ))}
        </ul>
      )}
    </li>
  )
})