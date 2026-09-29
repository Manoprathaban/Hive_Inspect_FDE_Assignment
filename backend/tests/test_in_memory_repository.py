"""Unit tests for the in-memory template repository adapter."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import replace

import pytest

from app.adapters.authentication.dev import DEV_USER_ID
from app.adapters.repositories.in_memory import InMemoryTemplateRepository
from app.domain.exceptions import (
    CommentNotFoundError,
    ItemNotFoundError,
    SectionNotFoundError,
    TemplateNotFoundError,
)
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


def _first_ids(saved: Template) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    section = saved.sections[0]
    item = section.items[0]
    return section.id, item.id, item.comments[0].id


def test_update_section_name_renames_and_persists() -> None:
    repository = InMemoryTemplateRepository()
    saved = asyncio.run(repository.save(_template(), owner_id=OWNER))
    section_id, *_ = _first_ids(saved)

    asyncio.run(
        repository.update_section_name(
            template_id=saved.id, section_id=section_id, owner_id=OWNER, name="Roof"
        )
    )
    refetched = asyncio.run(repository.get(saved.id, owner_id=OWNER))
    assert refetched.sections[0].name == "Roof"


def test_update_item_name_renames_and_persists() -> None:
    repository = InMemoryTemplateRepository()
    saved = asyncio.run(repository.save(_template(), owner_id=OWNER))
    _, item_id, _ = _first_ids(saved)

    asyncio.run(
        repository.update_item_name(
            template_id=saved.id, item_id=item_id, owner_id=OWNER, name="Roof covering"
        )
    )
    refetched = asyncio.run(repository.get(saved.id, owner_id=OWNER))
    assert refetched.sections[0].items[0].name == "Roof covering"


def test_update_comment_content_replaces_verbatim_and_empty_clears() -> None:
    repository = InMemoryTemplateRepository()
    saved = asyncio.run(repository.save(_template(), owner_id=OWNER))
    _, _, comment_id = _first_ids(saved)

    asyncio.run(
        repository.update_comment_content(
            template_id=saved.id, comment_id=comment_id, owner_id=OWNER, content="New text"
        )
    )
    refetched = asyncio.run(repository.get(saved.id, owner_id=OWNER))
    assert refetched.sections[0].items[0].comments[0].content == "New text"

    asyncio.run(
        repository.update_comment_content(
            template_id=saved.id, comment_id=comment_id, owner_id=OWNER, content=""
        )
    )
    refetched = asyncio.run(repository.get(saved.id, owner_id=OWNER))
    assert refetched.sections[0].items[0].comments[0].content == ""


def test_updates_leave_template_timestamps_untouched() -> None:
    repository = InMemoryTemplateRepository()
    saved = asyncio.run(repository.save(_template(), owner_id=OWNER))
    section_id, *_ = _first_ids(saved)

    asyncio.run(
        repository.update_section_name(
            template_id=saved.id, section_id=section_id, owner_id=OWNER, name="Updated"
        )
    )
    refetched = asyncio.run(repository.get(saved.id, owner_id=OWNER))
    assert refetched.updated_at == saved.updated_at


@pytest.mark.parametrize(
    ("method", "child_kwarg", "exception"),
    [
        ("update_section_name", "section_id", SectionNotFoundError),
        ("update_item_name", "item_id", ItemNotFoundError),
        ("update_comment_content", "comment_id", CommentNotFoundError),
    ],
)
def test_update_with_unresolvable_child_raises_specific_error(
    method: str, child_kwarg: str, exception: type[Exception]
) -> None:
    repository = InMemoryTemplateRepository()
    saved = asyncio.run(repository.save(_template(), owner_id=OWNER))
    kwargs = {
        "template_id": saved.id,
        "owner_id": OWNER,
        child_kwarg: uuid.uuid4(),
    }
    kwargs["content" if method == "update_comment_content" else "name"] = "x"
    with pytest.raises(exception):
        asyncio.run(getattr(repository, method)(**kwargs))


def test_updates_on_missing_template_raise_template_error() -> None:
    repository = InMemoryTemplateRepository()
    with pytest.raises(TemplateNotFoundError):
        asyncio.run(
            repository.update_section_name(
                template_id=uuid.uuid4(),
                section_id=uuid.uuid4(),
                owner_id=OWNER,
                name="x",
            )
        )


def test_updates_on_foreign_template_raise_template_error() -> None:
    repository = InMemoryTemplateRepository()
    saved = asyncio.run(repository.save(_template(), owner_id=OWNER))
    section_id, *_ = _first_ids(saved)
    with pytest.raises(TemplateNotFoundError):
        asyncio.run(
            repository.update_section_name(
                template_id=saved.id, section_id=section_id, owner_id=OTHER, name="x"
            )
        )


def _child_ids(template: Template) -> set[uuid.UUID]:
    return {
        *[section.id for section in template.sections],
        *[item.id for section in template.sections for item in section.items],
        *[
            comment.id
            for section in template.sections
            for item in section.items
            for comment in item.comments
        ],
    }


def test_duplicate_creates_independent_copy_with_new_ids_and_no_issues() -> None:
    repository = InMemoryTemplateRepository()
    source = asyncio.run(repository.save(_template(), owner_id=OWNER))

    copy = asyncio.run(repository.duplicate(source.id, owner_id=OWNER))

    assert copy.id != source.id
    assert copy.copied_from_id == source.id
    assert copy.owner_id == OWNER
    assert copy.name == "Sample (Copy)"
    assert copy.issues == []
    assert copy.created_at is not None
    assert copy.updated_at == copy.created_at
    assert not (_child_ids(source) & _child_ids(copy))

    assert copy.sections[0].name == source.sections[0].name
    assert copy.sections[0].items[0].comments[0].content == (
        source.sections[0].items[0].comments[0].content
    )


def test_duplicate_supports_custom_name() -> None:
    repository = InMemoryTemplateRepository()
    source = asyncio.run(repository.save(_template(), owner_id=OWNER))
    copy = asyncio.run(repository.duplicate(source.id, owner_id=OWNER, new_name="Renamed"))
    assert copy.name == "Renamed"


def test_duplicate_copy_can_be_edited_without_touching_source() -> None:
    repository = InMemoryTemplateRepository()
    source = asyncio.run(repository.save(_template(), owner_id=OWNER))
    copy = asyncio.run(repository.duplicate(source.id, owner_id=OWNER))
    copy_section_id = copy.sections[0].id

    asyncio.run(
        repository.update_section_name(
            template_id=copy.id,
            section_id=copy_section_id,
            owner_id=OWNER,
            name="Copy's section",
        )
    )

    refetched_copy = asyncio.run(repository.get(copy.id, owner_id=OWNER))
    refetched_source = asyncio.run(repository.get(source.id, owner_id=OWNER))
    assert refetched_copy.sections[0].name == "Copy's section"
    assert refetched_source.sections[0].name == "Exterior"


def test_duplicate_missing_and_foreign_raise_template_error() -> None:
    repository = InMemoryTemplateRepository()
    with pytest.raises(TemplateNotFoundError):
        asyncio.run(repository.duplicate(uuid.uuid4(), owner_id=OWNER))

    saved = asyncio.run(repository.save(_template(), owner_id=OWNER))
    with pytest.raises(TemplateNotFoundError):
        asyncio.run(repository.duplicate(saved.id, owner_id=OTHER))
