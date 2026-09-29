"""HTTP request/response schemas for the template API (presentation layer).

Mirror ``docs/API-CONTRACTS.md`` §12/§13 exactly (Pydantic v2, ``extra="forbid"``). Field
names match the database/domain; exclusions follow the contract: ``owner_id`` and FK
columns are never exposed, and the nested Template payload (``TemplateResponse``) never
carries ``import_issues`` — issues travel at the top level of ``ImportResultResponse``
and via the dedicated import-issues endpoint. Request bodies enforce §12 field semantics
(trimmed 1–200 names; ``content`` is free-form and verbatim).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.models.template import (
    AnswerType,
    Comment,
    CommentOption,
    CommentType,
    ImportIssue,
    IssueSeverity,
    IssueType,
    Item,
    OptionType,
    Section,
    Template,
    TemplateSummary,
)

__all__ = [
    "DuplicateRequest",
    "EditCommentRequest",
    "ImportResultResponse",
    "RenameRequest",
    "TemplateResponse",
    "TemplateSummaryResponse",
]


class RenameRequest(BaseModel):
    """Rename body for sections/items, §12.1: ``{"name": str}``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def _name_trimmed_1_200(cls, value: str) -> str:
        return _trimmed_name(value)


class EditCommentRequest(BaseModel):
    """Edit body for comments, §12.2: ``{"content": str}`` (empty clears)."""

    model_config = ConfigDict(extra="forbid")

    content: str


class DuplicateRequest(BaseModel):
    """Optional duplicate body, §12.3: ``{"name": str | null}``."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def _name_optional_trimmed_1_200(cls, value: str | None) -> str | None:
        return _trimmed_name(value) if value is not None else None


class CommentOptionResponse(BaseModel):
    """A single option value (``comment_options`` row), §13.2."""

    model_config = ConfigDict(extra="forbid")

    option_type: OptionType
    value: str
    display_order: int

    @classmethod
    def from_domain(cls, option: CommentOption) -> CommentOptionResponse:
        return cls(
            option_type=option.option_type,
            value=option.value,
            display_order=option.display_order,
        )


class CommentResponse(BaseModel):
    """A comment/checklist row, §13.2."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    content: str
    comment_type: CommentType
    category: int | None
    answer_type: AnswerType
    display_order: int
    recommendation: str | None
    default_value: str | None
    default_value_2: str | None
    default_unit_type: str | None
    estimate_min: float | None
    estimate_max: float | None
    source_row: int | None
    options: list[CommentOptionResponse]

    @classmethod
    def from_domain(cls, comment: Comment) -> CommentResponse:
        return cls(
            id=_required_id(comment.id),
            name=comment.name,
            content=comment.content,
            comment_type=comment.comment_type,
            category=comment.category,
            answer_type=comment.answer_type,
            display_order=comment.display_order,
            recommendation=comment.recommendation,
            default_value=comment.default_value,
            default_value_2=comment.default_value_2,
            default_unit_type=comment.default_unit_type,
            estimate_min=_to_float(comment.estimate_min),
            estimate_max=_to_float(comment.estimate_max),
            source_row=comment.source_row,
            options=[
                CommentOptionResponse.from_domain(option) for option in comment.options
            ],
        )


class ItemResponse(BaseModel):
    """A checklist item, §13.2."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    display_order: int
    comments: list[CommentResponse]

    @classmethod
    def from_domain(cls, item: Item) -> ItemResponse:
        return cls(
            id=_required_id(item.id),
            name=item.name,
            display_order=item.display_order,
            comments=[CommentResponse.from_domain(comment) for comment in item.comments],
        )


class SectionResponse(BaseModel):
    """A template section, §13.2."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    display_order: int
    items: list[ItemResponse]

    @classmethod
    def from_domain(cls, section: Section) -> SectionResponse:
        return cls(
            id=_required_id(section.id),
            name=section.name,
            display_order=section.display_order,
            items=[ItemResponse.from_domain(item) for item in section.items],
        )


class TemplateResponse(BaseModel):
    """Full template hierarchy, §13.2 (no ``owner_id``, no FK columns, no issues)."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    source: str
    source_filename: str | None
    copied_from_id: UUID | None
    created_at: datetime
    updated_at: datetime
    sections: list[SectionResponse]

    @classmethod
    def from_domain(cls, template: Template) -> TemplateResponse:
        return cls(
            id=_required_id(template.id),
            name=template.name,
            source=template.source,
            source_filename=template.source_filename,
            copied_from_id=template.copied_from_id,
            created_at=_required_timestamp(template.created_at),
            updated_at=_required_timestamp(template.updated_at),
            sections=[SectionResponse.from_domain(section) for section in template.sections],
        )


class TemplateSummaryResponse(BaseModel):
    """One list card for ``GET /templates``, §13.1 (no hierarchy, no issues)."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    source: str
    source_filename: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, summary: TemplateSummary) -> TemplateSummaryResponse:
        return cls(
            id=summary.id,
            name=summary.name,
            source=summary.source,
            source_filename=summary.source_filename,
            created_at=_required_timestamp(summary.created_at),
            updated_at=_required_timestamp(summary.updated_at),
        )


class ImportIssueResponse(BaseModel):
    """One persisted import diagnostic, §13.5."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    issue_type: IssueType
    severity: IssueSeverity
    message: str
    source_row: int | None
    source_field: str | None
    raw_value: str | None

    @classmethod
    def from_domain(cls, issue: ImportIssue) -> ImportIssueResponse:
        return cls(
            id=_required_id(issue.id),
            issue_type=issue.issue_type,
            severity=issue.severity,
            message=issue.message,
            source_row=issue.source_row,
            source_field=issue.source_field,
            raw_value=issue.raw_value,
        )


class ImportResultResponse(BaseModel):
    """Response of ``POST /templates/import``, §13.4."""

    model_config = ConfigDict(extra="forbid")

    template: TemplateResponse
    issues: list[ImportIssueResponse]

    @classmethod
    def from_domain(cls, template: Template) -> ImportResultResponse:
        """Build the response from a freshly persisted aggregate.

        Contract §13.4 reports issues newest-first, which is the reverse of the aggregate's
        insertion order for a single import batch (see the in-memory repository adapter).
        """
        return cls(
            template=TemplateResponse.from_domain(template),
            issues=[
                ImportIssueResponse.from_domain(issue)
                for issue in reversed(template.issues)
            ],
        )


def _required_id(value: UUID | None) -> UUID:
    """Return a persisted id; a missing one is a programming error, not a client error."""

    if value is None:
        raise ValueError("resource id is not set; the aggregate must be persisted first")
    return value


def _required_timestamp(value: datetime | None) -> datetime:
    if value is None:
        raise ValueError("resource timestamp is not set; the aggregate must be persisted first")
    return value


def _to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _trimmed_name(value: str) -> str:
    """Validate §12: a name is trimmed and 1–200 characters after trimming.

    ``null`` fails type validation earlier (422); an empty or whitespace-only string and
    an over-long name raise a validation error that FastAPI turns into ``422
    VALIDATION_ERROR``. The returned value is the stored, trimmed name.
    """

    trimmed = value.strip()
    if not 1 <= len(trimmed) <= 200:
        raise ValueError("must be 1-200 characters after trimming")
    return trimmed