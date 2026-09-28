"""Template domain models.

These are placeholder shapes for the future template data model (sections/items/comments).
They will evolve once the real schema is decided; protocols already depend on them, so
changes here ripple to importer/repository contracts consistently.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TemplateItem:
    """A single checklist item within a section."""

    name: str
    category: str | None = None


@dataclass(frozen=True)
class TemplateSection:
    """A named group of checklist items."""

    name: str
    items: list[TemplateItem] = field(default_factory=list)


@dataclass(frozen=True)
class TemplateImport:
    """Result of importing a template source file."""

    source_name: str
    title: str
    sections: list[TemplateSection] = field(default_factory=list)