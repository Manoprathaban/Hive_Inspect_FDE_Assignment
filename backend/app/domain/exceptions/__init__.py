"""Domain exceptions for the template import flow."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain errors."""


class TemplateImportError(DomainError):
    """Raised when a template source cannot be parsed/imported."""