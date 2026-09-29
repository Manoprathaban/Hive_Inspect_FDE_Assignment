import { memo } from 'react'
import type { Comment } from '../types'
import { InlineTextEditor } from './InlineTextEditor'

interface CommentViewProps {
  comment: Comment
  onEditContent: (commentId: string, content: string) => Promise<void>
}

/** One comment/checklist row: identity, type badges + editable content + read-only meta. */
export const CommentView = memo(function CommentView({ comment, onEditContent }: CommentViewProps) {
  return (
    <li className="comment-row">
      <div className="comment-main">
        <div className="comment-heading">
          <span className="comment-name">{comment.name}</span>
          <span className="badge badge--type">{comment.comment_type}</span>
          {comment.category !== null && <span className="badge badge--meta">cat {comment.category}</span>}
          <span className="badge badge--meta">{comment.answer_type}</span>
          {comment.source_row !== null && <span className="badge badge--meta">row {comment.source_row}</span>}
        </div>
        <InlineTextEditor
          value={comment.content}
          onSave={(content) => onEditContent(comment.id, content)}
          mode="content"
          label={`content of comment "${comment.name}"`}
        />
      </div>
      {comment.options.length > 0 && (
        <ul className="option-list" aria-label="Comment options">
          {comment.options.map((option) => (
            <li key={`${option.option_type}:${option.value}:${option.display_order}`}>
              <span className="badge badge--meta">{option.option_type}</span> {option.value}
            </li>
          ))}
        </ul>
      )}
      {(comment.recommendation ||
        comment.default_value ||
        comment.default_value_2 ||
        comment.default_unit_type ||
        comment.estimate_min !== null ||
        comment.estimate_max !== null) && (
        <dl className="comment-meta">
          {comment.recommendation !== null && (
            <>
              <dt>Recommendation</dt>
              <dd>{comment.recommendation}</dd>
            </>
          )}
          {comment.default_value !== null && (
            <>
              <dt>Default</dt>
              <dd>
                {comment.default_value}
                {comment.default_unit_type ? ` ${comment.default_unit_type}` : ''}
              </dd>
            </>
          )}
          {comment.default_value_2 !== null && (
            <>
              <dt>Default 2</dt>
              <dd>{comment.default_value_2}</dd>
            </>
          )}
          {(comment.estimate_min !== null || comment.estimate_max !== null) && (
            <>
              <dt>Estimate</dt>
              <dd>
                {comment.estimate_min === null ? '–' : comment.estimate_min}–
                {comment.estimate_max === null ? '–' : comment.estimate_max}
              </dd>
            </>
          )}
        </dl>
      )}
    </li>
  )
})