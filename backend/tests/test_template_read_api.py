"""API tests for the template read endpoints (contract §9.1/§9.2/§11/§13).

Covers the list (summaries, newest first, empty case), single-template retrieval (full
hierarchy, no issues/owner leak), import-issues retrieval, the indistinguishable
``404 TEMPLATE_NOT_FOUND`` for missing/foreign ids, the 422 path-parameter shape, the
``WWW-Authenticate`` header on 401, and an import-then-read-back end-to-end pass.
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
    """Point the app at a fresh repository so tests seed and read the same state."""

    repository = InMemoryTemplateRepository()
    client.app.dependency_overrides[get_template_repository] = lambda: repository
    return repository


def _make_template(*, name: str = "Sample", issues=None) -> Template:
    return Template(
        name=name,
        source="spectora",
        source_filename=f"{name.lower()}.xml",
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
        issues=issues or [],
    )


def _seed(repository: InMemoryTemplateRepository, *, owner_id=DEV_USER_ID, **kw) -> Template:
    return asyncio.run(repository.save(_make_template(**kw), owner_id=owner_id))


def test_list_templates_empty_is_200_empty_array() -> None:
    _stub()
    response = client.get("/api/templates", headers=AUTH)
    assert response.status_code == 200, response.text
    assert response.json() == []


def test_list_templates_returns_summaries_newest_first() -> None:
    repository = _stub()
    _seed(repository, name="Sample")
    _seed(repository, name="Second")

    response = client.get("/api/templates", headers=AUTH)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["name"] for item in body] == ["Second", "Sample"]

    for item in body:
        assert uuid.UUID(item["id"])
        assert item["source"] == "spectora"
        assert item["source_filename"] is not None
        assert item["created_at"] is not None
        assert item["updated_at"] is not None
        assert "sections" not in item
        assert "issues" not in item
        assert "owner_id" not in item


def test_list_templates_is_owner_scoped() -> None:
    repository = _stub()
    _seed(repository, name="Mine")
    _seed(repository, name="Someone else's", owner_id=OTHER)

    response = client.get("/api/templates", headers=AUTH)
    assert response.status_code == 200, response.text
    assert [item["name"] for item in response.json()] == ["Mine"]


def test_get_template_returns_full_hierarchy_without_issues_or_owner() -> None:
    repository = _stub()
    saved = _seed(
        repository,
        issues=[
            ImportIssue(
                message="meh",
                issue_type=IssueType.UNSUPPORTED_CONTENT,
                severity=IssueSeverity.WARNING,
            )
        ],
    )

    response = client.get(f"/api/templates/{saved.id}", headers=AUTH)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Sample"
    assert uuid.UUID(body["id"])
    assert "issues" not in body
    assert "owner_id" not in body

    section = body["sections"][0]
    assert section["name"] == "Exterior"
    assert uuid.UUID(section["id"])
    item = section["items"][0]
    assert item["name"] == "Roof covering"
    assert uuid.UUID(item["id"])
    comment = item["comments"][0]
    assert comment["content"] == "Inspect the roof covering."
    assert uuid.UUID(comment["id"])


def test_get_template_missing_is_404() -> None:
    _stub()
    response = client.get(f"/api/templates/{uuid.uuid4()}", headers=AUTH)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TEMPLATE_NOT_FOUND"


def test_get_template_foreign_is_indistinguishable_404() -> None:
    repository = _stub()
    saved = _seed(repository, owner_id=OTHER)

    response = client.get(f"/api/templates/{saved.id}", headers=AUTH)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TEMPLATE_NOT_FOUND"


def test_get_template_non_uuid_is_422() -> None:
    _stub()
    response = client.get("/api/templates/not-a-uuid", headers=AUTH)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_import_issues_returns_newest_first() -> None:
    repository = _stub()
    saved = _seed(
        repository,
        issues=[
            ImportIssue(
                message="older",
                issue_type=IssueType.UNSUPPORTED_CONTENT,
                severity=IssueSeverity.WARNING,
            ),
            ImportIssue(
                message="newer",
                issue_type=IssueType.SOURCE_DATA_MISSING,
                severity=IssueSeverity.INFO,
            ),
        ],
    )

    response = client.get(f"/api/templates/{saved.id}/import-issues", headers=AUTH)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [issue["message"] for issue in body] == ["newer", "older"]
    for issue in body:
        assert uuid.UUID(issue["id"])
        assert "owner_id" not in issue


def test_import_issues_for_missing_template_is_404() -> None:
    _stub()
    response = client.get(f"/api/templates/{uuid.uuid4()}/import-issues", headers=AUTH)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TEMPLATE_NOT_FOUND"


def test_import_issues_for_foreign_template_is_404() -> None:
    repository = _stub()
    saved = _seed(repository, owner_id=OTHER)

    response = client.get(f"/api/templates/{saved.id}/import-issues", headers=AUTH)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TEMPLATE_NOT_FOUND"


@pytest.mark.parametrize(
    "path",
    [
        "",
        f"/{uuid.uuid4()}",
        f"/{uuid.uuid4()}/import-issues",
    ],
)
def test_read_endpoints_require_auth(path: str) -> None:
    _stub()
    response = client.get(f"/api/templates{path}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_405_unsupported_method_advertises_allow() -> None:
    _stub()
    response = client.request("TRACE", "/api/templates", headers=AUTH)
    assert response.status_code == 405
    assert "GET" in response.headers["Allow"]

    overlaid = client.request("TRACE", "/api/templates/import", headers=AUTH)
    assert overlaid.status_code == 405
    assert {"GET", "POST"} <= set(overlaid.headers["Allow"].split(", "))


def test_import_then_read_back_end_to_end() -> None:
    # No importer/repository override: the real importer + in-memory repository serve both
    # the import and the reads, proving Location + GET + import-issues agree.
    worksheet = (REPO_ROOT / "sample-data" / "sheet1.xml").read_bytes()
    imported = client.post(
        "/api/templates/import",
        files={"file": ("sheet1.xml", worksheet, "application/xml")},
        headers=AUTH,
    )
    assert imported.status_code == 201, imported.text
    template_id = imported.json()["template"]["id"]

    fetched = client.get(f"/api/templates/{template_id}", headers=AUTH)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["name"] == "sheet1"
    assert fetched.json()["sections"]

    issues = client.get(f"/api/templates/{template_id}/import-issues", headers=AUTH)
    assert issues.status_code == 200, issues.text
    assert [issue["id"] for issue in issues.json()] == [
        issue["id"] for issue in imported.json()["issues"]
    ]