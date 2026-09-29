"""API tests for the template edit endpoints (contract §9.4/§10/§12/§17).

Covers the three PATCHes (204, trimmed-name semantics, empty content clears, exact
§10/§20 ownership mapping: TEMPLATE_NOT_FOUND vs child-specific 404s) and the duplicate
endpoint (independent copy, provenance, default/custom naming, Location, body validation).
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.authentication.dev import DEV_USER_ID
from app.adapters.repositories.in_memory import InMemoryTemplateRepository
from app.api.dependencies.providers import get_template_repository
from app.domain.models.template import (
    Comment,
    ImportIssue,
    IssueSeverity,
    IssueType,
    Item,
    Section,
    Template,
)
from app.main import app

client = TestClient(app)

AUTH = {"Authorization": "Bearer dev-token"}
OTHER = uuid.UUID("00000000-0000-0000-0000-000000000002")
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _clear_dependency_overrides() -> None:
    yield
    client.app.dependency_overrides.clear()


def _stub() -> InMemoryTemplateRepository:
    repository = InMemoryTemplateRepository()
    client.app.dependency_overrides[get_template_repository] = lambda: repository
    return repository


def _make_template(**overrides) -> Template:
    defaults = dict(
        name="Sample",
        source="spectora",
        source_filename="sample.xml",
        sections=[
            Section(
                name="Exterior",
                display_order=0,
                items=[
                    Item(
                        name="Roof covering",
                        display_order=0,
                        comments=[
                            Comment(
                                name="General roof covering",
                                content="Inspect the roof covering.",
                                display_order=0,
                            )
                        ],
                    )
                ],
            )
        ],
        issues=[
            ImportIssue(
                message="Source column 'Locked' contained data that cannot be represented.",
                issue_type=IssueType.UNSUPPORTED_CONTENT,
                severity=IssueSeverity.WARNING,
                source_row=45,
                source_field="Locked",
                raw_value="true",
            )
        ],
    )
    defaults.update(overrides)
    return Template(**defaults)


def _seed(repository: InMemoryTemplateRepository, **kw) -> Template:
    return asyncio.run(
        repository.save(
            _make_template(**kw), owner_id=kw.pop("owner_id", DEV_USER_ID)
        )
    )


def _child_ids(saved: Template) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    section = saved.sections[0]
    item = section.items[0]
    return section.id, item.id, item.comments[0].id


def test_rename_section_returns_204_and_persists() -> None:
    repository = _stub()
    saved = _seed(repository)
    section_id, *_ = _child_ids(saved)

    response = client.patch(
        f"/api/templates/{saved.id}/sections/{section_id}",
        json={"name": "Roof"},
        headers=AUTH,
    )
    assert response.status_code == 204, response.text
    assert response.text == ""

    fetched = client.get(f"/api/templates/{saved.id}", headers=AUTH).json()
    assert fetched["sections"][0]["name"] == "Roof"


def test_rename_item_returns_204_and_persists() -> None:
    repository = _stub()
    saved = _seed(repository)
    _, item_id, _ = _child_ids(saved)

    response = client.patch(
        f"/api/templates/{saved.id}/items/{item_id}",
        json={"name": "Roof covering"},
        headers=AUTH,
    )
    assert response.status_code == 204, response.text

    fetched = client.get(f"/api/templates/{saved.id}", headers=AUTH).json()
    assert fetched["sections"][0]["items"][0]["name"] == "Roof covering"


def test_edit_comment_replaces_content_and_empty_clears() -> None:
    repository = _stub()
    saved = _seed(repository)
    _, _, comment_id = _child_ids(saved)

    response = client.patch(
        f"/api/templates/{saved.id}/comments/{comment_id}",
        json={"content": "New text"},
        headers=AUTH,
    )
    assert response.status_code == 204, response.text
    fetched = client.get(f"/api/templates/{saved.id}", headers=AUTH).json()
    assert fetched["sections"][0]["items"][0]["comments"][0]["content"] == "New text"

    cleared = client.patch(
        f"/api/templates/{saved.id}/comments/{comment_id}",
        json={"content": ""},
        headers=AUTH,
    )
    assert cleared.status_code == 204, cleared.text
    fetched = client.get(f"/api/templates/{saved.id}", headers=AUTH).json()
    assert fetched["sections"][0]["items"][0]["comments"][0]["content"] == ""


def test_rename_trimmed_name_is_stored() -> None:
    repository = _stub()
    saved = _seed(repository)
    section_id, *_ = _child_ids(saved)

    response = client.patch(
        f"/api/templates/{saved.id}/sections/{section_id}",
        json={"name": "  Roof  "},
        headers=AUTH,
    )
    assert response.status_code == 204, response.text
    fetched = client.get(f"/api/templates/{saved.id}", headers=AUTH).json()
    assert fetched["sections"][0]["name"] == "Roof"


def test_edit_does_not_bump_template_updated_at() -> None:
    repository = _stub()
    saved = _seed(repository)
    section_id, *_ = _child_ids(saved)

    before = client.get(f"/api/templates/{saved.id}", headers=AUTH).json()
    client.patch(
        f"/api/templates/{saved.id}/sections/{section_id}",
        json={"name": "Roof"},
        headers=AUTH,
    )
    after = client.get(f"/api/templates/{saved.id}", headers=AUTH).json()
    assert before["updated_at"] == after["updated_at"]


@pytest.mark.parametrize(
    "payload",
    [
        {"name": ""},
        {"name": "   "},
        {"name": None},
        {"name": "x" * 201},
        {"name": "Roof", "extra": "nope"},
        {},
    ],
)
def test_invalid_rename_body_is_422(payload) -> None:
    repository = _stub()
    saved = _seed(repository)
    section_id, *_ = _child_ids(saved)
    response = client.patch(
        f"/api/templates/{saved.id}/sections/{section_id}",
        json=payload,
        headers=AUTH,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("payload", [{"content": None}, {}, {"content": "x", "extra": 1}])
def test_invalid_comment_body_is_422(payload) -> None:
    repository = _stub()
    saved = _seed(repository)
    _, _, comment_id = _child_ids(saved)
    response = client.patch(
        f"/api/templates/{saved.id}/comments/{comment_id}",
        json=payload,
        headers=AUTH,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_patch_on_missing_template_is_404() -> None:
    _stub()
    response = client.patch(
        f"/api/templates/{uuid.uuid4()}/sections/{uuid.uuid4()}",
        json={"name": "Roof"},
        headers=AUTH,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TEMPLATE_NOT_FOUND"


def test_patch_on_foreign_template_is_404() -> None:
    repository = _stub()
    saved = _seed(repository, owner_id=OTHER)
    section_id, *_ = _child_ids(saved)

    response = client.patch(
        f"/api/templates/{saved.id}/sections/{section_id}",
        json={"name": "Roof"},
        headers=AUTH,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TEMPLATE_NOT_FOUND"


@pytest.mark.parametrize(
    ("path", "expected_code"),
    [
        ("sections/{section_id}", "SECTION_NOT_FOUND"),
        ("items/{item_id}", "ITEM_NOT_FOUND"),
        ("comments/{comment_id}", "COMMENT_NOT_FOUND"),
    ],
)
def test_patch_child_not_under_owned_template_is_child_404(
    path: str, expected_code: str
) -> None:
    repository = _stub()
    saved = _seed(repository)
    target = {
        "section_id": uuid.uuid4(),
        "item_id": uuid.uuid4(),
        "comment_id": uuid.uuid4(),
    }
    url = f"/api/templates/{saved.id}/{path.format(**target)}"
    body = {"name": "x"} if not path.startswith("comments") else {"content": "x"}
    response = client.patch(url, json=body, headers=AUTH)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == expected_code


def test_duplicate_creates_independent_copy_with_location_and_no_issues() -> None:
    repository = _stub()
    saved = _seed(repository)

    response = client.post(f"/api/templates/{saved.id}/duplicate", headers=AUTH)
    assert response.status_code == 201, response.text
    copy = response.json()
    assert uuid.UUID(copy["id"])
    assert copy["id"] != str(saved.id)
    assert copy["copied_from_id"] == str(saved.id)
    assert copy["name"] == "Sample (Copy)"
    assert copy["source_filename"] == "sample.xml"
    assert "issues" not in copy
    assert response.headers["Location"] == f"/api/templates/{copy['id']}"

    # Copy's import issues are empty (no import happened); the original's are intact.
    issues = client.get(f"/api/templates/{copy['id']}/import-issues", headers=AUTH)
    assert issues.json() == []
    original_issues = client.get(
        f"/api/templates/{saved.id}/import-issues", headers=AUTH
    ).json()
    assert len(original_issues) == 1


def test_duplicate_with_custom_name() -> None:
    repository = _stub()
    saved = _seed(repository)
    response = client.post(
        f"/api/templates/{saved.id}/duplicate",
        json={"name": "Renamed copy"},
        headers=AUTH,
    )
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "Renamed copy"


def test_duplicate_empty_body_uses_default_name() -> None:
    repository = _stub()
    saved = _seed(repository)
    response = client.post(
        f"/api/templates/{saved.id}/duplicate", json={}, headers=AUTH
    )
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "Sample (Copy)"


def test_duplicate_explicit_null_name_uses_default_name() -> None:
    repository = _stub()
    saved = _seed(repository)
    response = client.post(
        f"/api/templates/{saved.id}/duplicate", json={"name": None}, headers=AUTH
    )
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "Sample (Copy)"


@pytest.mark.parametrize(
    "payload",
    [{"name": ""}, {"name": "   "}, {"name": "x" * 201}],
)
def test_invalid_duplicate_body_is_422(payload) -> None:
    repository = _stub()
    saved = _seed(repository)
    response = client.post(
        f"/api/templates/{saved.id}/duplicate", json=payload, headers=AUTH
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_duplicate_missing_and_foreign_template_is_404() -> None:
    repository = _stub()
    missing = client.post(f"/api/templates/{uuid.uuid4()}/duplicate", headers=AUTH)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "TEMPLATE_NOT_FOUND"

    saved = _seed(repository, owner_id=OTHER)
    foreign = client.post(f"/api/templates/{saved.id}/duplicate", headers=AUTH)
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "TEMPLATE_NOT_FOUND"


@pytest.mark.parametrize(
    "method,path",
    [
        ("patch", f"/{uuid.uuid4()}/sections/{uuid.uuid4()}"),
        ("patch", f"/{uuid.uuid4()}/items/{uuid.uuid4()}"),
        ("patch", f"/{uuid.uuid4()}/comments/{uuid.uuid4()}"),
        ("post", f"/{uuid.uuid4()}/duplicate"),
    ],
)
def test_edit_endpoints_require_auth(method: str, path: str) -> None:
    _stub()
    kw = {"json": {"name": "x"}} if not path.endswith("comments") else {"json": {"content": "x"}}
    if path.endswith("duplicate"):
        kw = {}
    response = getattr(client, method)(f"/api/templates{path}", **kw)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_import_then_duplicate_and_edit_end_to_end() -> None:
    # Real importer through the app with a fresh in-memory repository (hermetic; the
    # PostgreSQL adapter is covered by the dedicated live-DB suite).
    _stub()
    worksheet = (REPO_ROOT / "sample-data" / "sheet1.xml").read_bytes()
    imported = client.post(
        "/api/templates/import",
        files={"file": ("sheet1.xml", worksheet, "application/xml")},
        headers=AUTH,
    )
    assert imported.status_code == 201, imported.text
    original_id = imported.json()["template"]["id"]

    copied = client.post(f"/api/templates/{original_id}/duplicate", headers=AUTH)
    assert copied.status_code == 201, copied.text
    copy = copied.json()
    copy_id = copy["id"]
    section_id = copy["sections"][0]["id"]

    renamed = client.patch(
        f"/api/templates/{copy_id}/sections/{section_id}",
        json={"name": "Exterior (Copy)"},
        headers=AUTH,
    )
    assert renamed.status_code == 204, renamed.text

    copy_fetched = client.get(f"/api/templates/{copy_id}", headers=AUTH).json()
    original_fetched = client.get(f"/api/templates/{original_id}", headers=AUTH).json()
    assert copy_fetched["sections"][0]["name"] == "Exterior (Copy)"
    assert original_fetched["sections"][0]["name"] != "Exterior (Copy)"