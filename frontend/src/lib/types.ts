/**
 * Types mirroring docs/API-CONTRACTS.md §13 exactly (snake_case preserved; no second,
 * divergent representation). Single source for the whole app; feature folders import
 * from here. Lightweight guards validate decoded responses so the UI only ever sees
 * contract-shaped data.
 */

export type UUID = string
export type DateTime = string // RFC 3339 UTC

export type CommentType = 'info' | 'limit' | 'defect'
export type AnswerType = 'boolean' | 'checkbox' | 'date' | 'number' | 'range' | 'text'
export type OptionType = 'multiple_choice' | 'unit_type'
export type IssueType = 'SOURCE_DATA_MISSING' | 'UNSUPPORTED_CONTENT' | 'INVALID_SOURCE_DATA'
export type IssueSeverity = 'info' | 'warning' | 'error'

export interface TemplateSummary {
  id: UUID
  name: string
  source: string
  source_filename: string | null
  created_at: DateTime
  updated_at: DateTime
}

export interface Template {
  id: UUID
  name: string
  source: string
  source_filename: string | null
  copied_from_id: UUID | null
  created_at: DateTime
  updated_at: DateTime
  sections: Section[]
}

export interface Section {
  id: UUID
  name: string
  display_order: number
  items: Item[]
}

export interface Item {
  id: UUID
  name: string
  display_order: number
  comments: Comment[]
}

export interface Comment {
  id: UUID
  name: string
  content: string
  comment_type: CommentType
  category: number | null
  answer_type: AnswerType
  display_order: number
  recommendation: string | null
  default_value: string | null
  default_value_2: string | null
  default_unit_type: string | null
  estimate_min: number | null
  estimate_max: number | null
  source_row: number | null
  options: CommentOption[]
}

export interface CommentOption {
  option_type: OptionType
  value: string
  display_order: number
}

export interface ImportIssue {
  id: UUID
  issue_type: IssueType
  severity: IssueSeverity
  message: string
  source_row: number | null
  source_field: string | null
  raw_value: string | null
}

export interface ImportResult {
  template: Template
  issues: ImportIssue[]
}

export interface ApiErrorEnvelope {
  error: { code: string; message: string; details: unknown }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isString(value: unknown): value is string {
  return typeof value === 'string'
}

/** Guard for one list summary (§13.1). */
export function isTemplateSummary(value: unknown): value is TemplateSummary {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.name) &&
    isString(value.source) &&
    ('source_filename' in value ? (value.source_filename === null || isString(value.source_filename)) : true) &&
    isString(value.created_at) &&
    isString(value.updated_at)
  )
}

/** Structural check for a single import issue (§13.5). */
export function isImportIssue(value: unknown): value is ImportIssue {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.issue_type) &&
    isString(value.severity) &&
    isString(value.message)
  )
}

/** Structural check for a full template hierarchy (§13.2). */
export function isTemplate(value: unknown): value is Template {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.name) &&
    isString(value.source) &&
    isString(value.created_at) &&
    isString(value.updated_at) &&
    Array.isArray(value.sections)
  )
}

/** Guard for a list of summaries. */
export function isTemplateSummaryList(value: unknown): value is TemplateSummary[] {
  return Array.isArray(value) && value.every(isTemplateSummary)
}

/** Guard for a list of issues. */
export function isImportIssueList(value: unknown): value is ImportIssue[] {
  return Array.isArray(value) && value.every(isImportIssue)
}

/** Guard for an import result (§13.4). */
export function isImportResult(value: unknown): value is ImportResult {
  return isRecord(value) && isTemplate(value.template) && Array.isArray(value.issues)
}