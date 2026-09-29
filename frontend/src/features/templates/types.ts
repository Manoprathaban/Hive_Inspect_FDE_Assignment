/**
 * Template-scoped re-export of the contract types (FRONTEND_DESIGN §5/§22). Keep the
 * single source in lib/types.ts; this file only narrows the surface for the feature.
 */

export type {
  Template,
  TemplateSummary,
  Section,
  Item,
  Comment,
  CommentOption,
  ImportIssue,
  ImportResult,
  CommentType,
  AnswerType,
  OptionType,
  IssueType,
  IssueSeverity,
} from '../../lib/types'