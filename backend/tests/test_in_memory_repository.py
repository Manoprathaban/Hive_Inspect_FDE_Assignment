"""Unit tests for the in-memory template repository adapter."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import replace

from app.adapters.authentication.dev import DEV_USER_ID
from app.adapters.repositories.in_memory import InMemoryTemplateRepository
from app.domain.models.template import (
    Comment,
    ImportIssue,
    IssueSeverity,
    IssueType,
    Item,
    Section,
    Template,
)

OWNER = DEV_USER_ID
OTHER = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _template() -> Template:
    return Template(
        name="Sample",
        source="spectora",
        source_filename="sample.xml",
        sections=[
            Section(
                name="Exterior",
                items=[
                    Item(
                        name="Roof covering",
                        comments=[
                            Comment(name="General roof covering", content="Inspect it."),
                            Comment(name="Second", content=""),
                        ],
                    )
                ],
            )
        ],
        issues=[ImportIssue(message="meh", issue_type=IssueType.UNSUPPORTED_CONTENT)],
    )


def test_save_assigns_ids_everywhere_and_marks_ownership() -> None:
    repository = InMemoryTemplateRepository()
    saved = asyncio.run(repository.save(_template(), owner_id=OWNER))

    assert saved.id is not None
    assert saved.owner_id == OWNER
    assert saved.created_at is not None
    assert saved.updated_at is not None

    assert all(s.id is not None for s in saved.sections)
    assert all(i.id is not None for s in saved.sections for i in s.items)
    assert all(c.id is not None for s in saved.sections for i in s.items for c in i.comments)
    assert all(iss.id is not None for iss in saved.issues)


def test_save_persists_atomically_with_issues() -> None:
    repository = InMemoryTemplateRepository()
    template = replace(
        _template(),
        issues=[ImportIssue(message="alpha", issue_type=IssueType.UNSUPPORTED_CONTENT)],
    )
    saved = asyncio.run(repository.save(template, owner_id=OWNER))

    issues = asyncio.run(repository.list_import_issues(saved.id, owner_id=OWNER))
    assert [issue.message for issue in issues] == [issue.message for issue in saved.issues]


def test_get_is_owner_scoped() -> None:
    repository = InMemoryTemplateRepository()
    saved = asyncio.run(repository.save(_template(), owner_id=OWNER))

    assert asyncio.run(repository.get(saved.id, owner_id=OWNER)) is not None
    assert asyncio.run(repository.get(saved.id, owner_id=OTHER)) is None


def test_saved_aggregate_is_independent_of_the_input() -> None:
    repository = InMemoryTemplateRepository()
    source = _template()
    saved = asyncio.run(repository.save(source, owner_id=OWNER))
    source.sections.append(Section(name="Late addition"))

    refetched = asyncio.run(repository.get(saved.id, owner_id=OWNER))
    assert refetched is not None
    assert len(refetched.sections) == 1


def test_list_for_user_orders_by_updated_at() -> None:
    repository = InMemoryTemplateRepository()
    asyncio.run(repository.save(_template(), owner_id=OWNER))
    second = replace(_template(), name="Second")
    asyncio.run(repository.save(second, owner_id=OWNER))

    summaries = asyncio.run(repository.list_for_user(OWNER))
    assert [summary.name for summary in summaries] == ["Second", "Sample"]
    assert asyncio.run(repository.list_for_user(OTHER)) == []


def test_list_import_issues_newest_first() -> None:
    repository = InMemoryTemplateRepository()
    template = replace(
        _template(),
        issues=[
            ImportIssue(message="older", issue_type=IssueType.UNSUPPORTED_CONTENT),
            ImportIssue(
                message="newer",
                issue_type=IssueType.SOURCE_DATA_MISSING,
                severity=IssueSeverity.INFO,
            ),
        ],
    )
    saved = asyncio.run(repository.save(template, owner_id=OWNER))

    issues = asyncio.run(repository.list_import_issues(saved.id, owner_id=OWNER))
    assert [issue.message for issue in issues] == ["newer", "older"]
    assert asyncio.run(repository.list_import_issues(saved.id, owner_id=OTHER)) == []