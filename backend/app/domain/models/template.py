"""Template domain aggregate and supporting entities.

Pure domain, persistence-agnostic. Field names and enums mirror the PostgreSQL schema
(``database/migrations/0001_create_template_schema.sql``). The hierarchy is the Spectora
HTML-text export structure: template -> sections -> items -> comments -> comment_options,
with import issues attached to the template.

Ordering is explicit: ``display_order`` at every level, zero-based.
``content`` may contain markup (Spectora comment text is free-form); the whole template is
never stored as one opaque blob.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

__all__ = [
    "CommentType",
    "AnswerType",
    "OptionType",
    "IssueType",
    "IssueSeverity",
    "Template",
    "TemplateSummary",
    "Section",
    "Item",
    "Comment",
    "CommentOption",
    "ImportIssue",
]


class CommentType(enum.StrEnum):
    """Comment kind as exported by Spectora."""

    INFO = "info"
    LIMIT = "limit"
    DEFECT = "defect"


class AnswerType(enum.StrEnum):
    """Answer widget used for a comment."""

    BOOLEAN = "boolean"
    CHECKBOX = "checkbox"
    DATE = "date"
    NUMBER = "number"
    RANGE = "range"
    TEXT = "text"


class OptionType(enum.StrEnum):
    """Discriminator for :class:`CommentOption` rows."""

    MULTIPLE_CHOICE = "multiple_choice"
    UNIT_TYPE = "unit_type"


class IssueType(enum.StrEnum):
    """Category of an import issue.

    - ``SOURCE_DATA_MISSING``: the information was not present in the source export.
    - ``UNSUPPORTED_CONTENT``: the information existed but could not be fully represented.
    - ``INVALID_SOURCE_DATA``: the source data was malformed.
    """

    SOURCE_DATA_MISSING = "SOURCE_DATA_MISSING"
    UNSUPPORTED_CONTENT = "UNSUPPORTED_CONTENT"
    INVALID_SOURCE_DATA = "INVALID_SOURCE_DATA"


class IssueSeverity(enum.StrEnum):
    """Severity of an import issue, for UI filtering/sorting."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class CommentOption:
    """A single option value for a comment (multiple choice or unit type)."""

    option_type: OptionType
    value: str
    display_order: int = 0
    id: uuid.UUID | None = None


@dataclass(frozen=True)
class Comment:
    """A comment/checklist row; ``content`` may carry markup."""

    name: str
    content: str = ""
    comment_type: CommentType = CommentType.INFO
    answer_type: AnswerType = AnswerType.BOOLEAN
    display_order: int = 0
    category: int | None = None
    recommendation: str | None = None
    default_value: str | None = None
    default_value_2: str | None = None
    default_unit_type: str | None = None
    estimate_min: Decimal | None = None
    estimate_max: Decimal | None = None
    source_row: int | None = None
    options: list[CommentOption] = field(default_factory=list)
    id: uuid.UUID | None = None


@dataclass(frozen=True)
class Item:
    """A checklist item inside a section, with ordered comments."""

    name: str
    display_order: int = 0
    comments: list[Comment] = field(default_factory=list)
    id: uuid.UUID | None = None


@dataclass(frozen=True)
class Section:
    """A named section of a template, with ordered items."""

    name: str
    display_order: int = 0
    items: list[Item] = field(default_factory=list)
    id: uuid.UUID | None = None


@dataclass(frozen=True)
class ImportIssue:
    """A user-visible issue recorded during template import."""

    message: str
    issue_type: IssueType
    severity: IssueSeverity = IssueSeverity.WARNING
    source_row: int | None = None
    source_field: str | None = None
    raw_value: str | None = None
    id: uuid.UUID | None = None


@dataclass(frozen=True)
class Template:
    """Complete structured inspection template (the domain aggregate).

    ``id``/``owner_id`` are optional because importers produce unsaved templates;
    repositories fill them in when persisting. The same applies to the nested
    ``Section``/``Item``/``Comment``/``CommentOption`` ``id``s and to ``created_at`` /
    ``updated_at``: they mirror the Postgres schema, which the API contract (§13 of
    ``docs/API-CONTRACTS.md``) needs on every resource, but unsaved aggregates leave them
    unset.
    """

    name: str
    source: str = "spectora"
    source_filename: str | None = None
    sections: list[Section] = field(default_factory=list)
    issues: list[ImportIssue] = field(default_factory=list)
    id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    copied_from_id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class TemplateSummary:
    """Lightweight template record for list views (no full hierarchy)."""

    id: uuid.UUID
    name: str
    source: str
    source_filename: str | None
    created_at: datetime
    updated_at: datetime
