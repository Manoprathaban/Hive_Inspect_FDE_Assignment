"""Domain exceptions for the template import/edit flow."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain errors."""


class TemplateImportError(DomainError):
    """Raised when a template source cannot be parsed/imported."""


class TemplateNotFoundError(DomainError):
    """Raised when an id does not resolve to a template the actor owns.

    Missing and foreign are indistinguishable by design (contract §20): the caller maps
    both to ``404 TEMPLATE_NOT_FOUND``.
    """


class SectionNotFoundError(DomainError):
    """Raised when a section id does not resolve under an owned template."""


class ItemNotFoundError(DomainError):
    """Raised when an item id does not resolve under an owned template."""


class CommentNotFoundError(DomainError):
    """Raised when a comment id does not resolve under an owned template."""
