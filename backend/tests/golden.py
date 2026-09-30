"""Expected-output ("golden") projection of an imported :class:`Template`.

A committed expected-output file per fixture turns "the importer produced *something*" into
a reviewable artifact a human can read and diff against a real API response. Two shapes are
produced:

* **full** — every section, item, comment, option and issue, for the small synthetic
  fixtures. Complete enough to review the whole mapping by eye.
* **summary** — counts, per-value tallies and the issue list only. Used for
  ``sample-data/sheet1.xml``, whose 392 comments would make a full golden ~40k lines of
  noise nobody reads; the tallies and ordering assertions carry the signal instead.

Everything here is deliberately a plain JSON-compatible ``dict`` so a golden file is
readable, diffable, and comparable field-by-field in a test failure.
"""

from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.domain.models.template import Template

__all__ = [
    "EXPECTED_DIR",
    "REPO_ROOT",
    "fixture_path",
    "full_projection",
    "summary_projection",
    "render",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DATA = REPO_ROOT / "sample-data"
EXPECTED_DIR = SAMPLE_DATA / "expected"


def fixture_path(filename: str) -> Path:
    """Return the on-disk path of a committed fixture."""

    return SAMPLE_DATA / filename


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _option(option: Any) -> dict[str, Any]:
    return {
        "option_type": option.option_type.value,
        "value": option.value,
        "display_order": option.display_order,
    }


def _comment(comment: Any) -> dict[str, Any]:
    return {
        "name": comment.name,
        "content": comment.content,
        "comment_type": comment.comment_type.value,
        "answer_type": comment.answer_type.value,
        "display_order": comment.display_order,
        "category": comment.category,
        "recommendation": comment.recommendation,
        "default_value": comment.default_value,
        "default_value_2": comment.default_value_2,
        "default_unit_type": comment.default_unit_type,
        "estimate_min": _decimal(comment.estimate_min),
        "estimate_max": _decimal(comment.estimate_max),
        "source_row": comment.source_row,
        "options": [_option(option) for option in comment.options],
    }


def _counts(template: Template) -> dict[str, int]:
    comments = [
        comment
        for section in template.sections
        for item in section.items
        for comment in item.comments
    ]
    return {
        "sections": len(template.sections),
        "items": sum(len(section.items) for section in template.sections),
        "comments": len(comments),
        "options": sum(len(comment.options) for comment in comments),
        "issues": len(template.issues),
    }


def _tallies(template: Template) -> dict[str, dict[str, int]]:
    """Value distributions that a mapping bug would perturb."""

    comments = [
        comment
        for section in template.sections
        for item in section.items
        for comment in item.comments
    ]
    return {
        "comment_type": dict(sorted(Counter(c.comment_type.value for c in comments).items())),
        "answer_type": dict(sorted(Counter(c.answer_type.value for c in comments).items())),
        "category": dict(sorted(Counter(str(c.category) for c in comments).items())),
    }


def _issue(issue: Any) -> dict[str, Any]:
    return {
        "issue_type": issue.issue_type.value,
        "severity": issue.severity.value,
        "source_field": issue.source_field,
        "source_row": issue.source_row,
        "raw_value": issue.raw_value,
        "message": issue.message,
    }


def _skeleton(template: Template) -> dict[str, Any]:
    """Fields shared by both projections."""

    return {
        "name": template.name,
        "source": template.source,
        "source_filename": template.source_filename,
    }


def full_projection(template: Template) -> dict[str, Any]:
    """The complete tree, for fixtures small enough to review in full."""

    return {
        **_skeleton(template),
        "counts": _counts(template),
        "sections": [
            {
                "name": section.name,
                "display_order": section.display_order,
                "items": [
                    {
                        "name": item.name,
                        "display_order": item.display_order,
                        "comments": [_comment(comment) for comment in item.comments],
                    }
                    for item in section.items
                ],
            }
            for section in template.sections
        ],
        "issues": [_issue(issue) for issue in template.issues],
    }


def summary_projection(template: Template) -> dict[str, Any]:
    """Counts, tallies, names and issues — the signal without the bulk."""

    return {
        **_skeleton(template),
        "counts": _counts(template),
        "tallies": _tallies(template),
        "section_names": [section.name for section in template.sections],
        "item_names_by_section": {
            section.name: [item.name for item in section.items] for section in template.sections
        },
        "first_and_last_source_row": [
            min(
                comment.source_row
                for section in template.sections
                for item in section.items
                for comment in item.comments
            ),
            max(
                comment.source_row
                for section in template.sections
                for item in section.items
                for comment in item.comments
            ),
        ],
        "issues": [_issue(issue) for issue in template.issues],
    }


def render(projection: dict[str, Any]) -> str:
    """Serialise a projection deterministically for a committed file."""

    return json.dumps(projection, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
