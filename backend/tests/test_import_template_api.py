"""API tests for ``POST /api/templates/import`` (contract §9.3/§13/§18).

Coverage: happy path (ids/timestamps/Location/issues), ``VALIDATION_ERROR``,
``FILE_TOO_LARGE``, ``INVALID_FILE`` (extension and content), ``INVALID_XLSX``,
``AUTHENTICATION_REQUIRED``, and the canonical Spectora worksheet end-to-end.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

from app.adapters.authentication.dev import DEV_USER_ID
from app.adapters.repositories.in_memory import InMemoryTemplateRepository
from app.api.dependencies.providers import (
    get_import_template_use_case,
    get_template_repository,
)
from app.application.use_cases.import_template import ImportTemplateUseCase
from app.domain.exceptions import TemplateImportError
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
_XML = b"<?xml version='1.0'?><worksheet></worksheet>"


class _StubImporter:
    def __init__(
        self,
        template: Template | None = None,
        error: Exception | None = None,
    ) -> None:
        self.template = template
        self.error = error

    def import_template(self, source: bytes, *, filename: str = "") -> Template:
        if self.error is not None:
            raise self.error
        return self.template


@pytest.fixture(autouse=True)
def _clear_dependency_overrides() -> None:
    """Guarantee one test's stubbing never leaks into another."""

    yield
    client.app.dependency_overrides.clear()


def _stub(
    fake: _StubImporter | None = None,
) -> InMemoryTemplateRepository:
    """Point the app at a fresh repository and (optionally) a stub importer."""

    repository = InMemoryTemplateRepository()
    client.app.dependency_overrides[get_template_repository] = lambda: repository
    if fake is not None:
        client.app.dependency_overrides[get_import_template_use_case] = (
            lambda: ImportTemplateUseCase(importer=fake)
        )
    return repository


def _make_template(**overrides) -> Template:
    defaults = dict(
        name="InterNACHI Residential",
        source="spectora",
        source_filename="interNACHI-template.xml",
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


def test_import_creates_persisted_template_with_ids_and_location() -> None:
    repository = _stub(_StubImporter(template=_make_template()))
    response = client.post(
        "/api/templates/import",
        files={"file": ("interNACHI-template.xml", _XML, "application/xml")},
        headers=AUTH,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    template = body["template"]
    assert template["name"] == "InterNACHI Residential"
    assert template["source"] == "spectora"
    assert template["source_filename"] == "interNACHI-template.xml"
    assert template["copied_from_id"] is None
    assert uuid.UUID(template["id"])
    assert template["created_at"] is not None
    assert template["updated_at"] == template["created_at"]

    section = template["sections"][0]
    assert section["name"] == "Exterior"
    assert uuid.UUID(section["id"])
    item = section["items"][0]
    assert uuid.UUID(item["id"])
    comment = item["comments"][0]
    assert uuid.UUID(comment["id"])
    assert comment["content"] == "Inspect the roof covering."

    issue = body["issues"][0]
    assert uuid.UUID(issue["id"])
    assert issue["issue_type"] == "UNSUPPORTED_CONTENT"
    assert issue["severity"] == "warning"
    assert issue["source_field"] == "Locked"
    assert issue["raw_value"] == "true"

    assert response.headers["Location"] == f"/api/templates/{template['id']}"
    saved = asyncio.run(
        repository.get(uuid.UUID(template["id"]), owner_id=DEV_USER_ID)
    )
    assert saved is not None
    assert saved.name == "InterNACHI Residential"


def test_import_issues_are_newest_first() -> None:
    first = ImportIssue(
        message="first",
        issue_type=IssueType.UNSUPPORTED_CONTENT,
        severity=IssueSeverity.WARNING,
    )
    second = ImportIssue(
        message="second",
        issue_type=IssueType.SOURCE_DATA_MISSING,
        severity=IssueSeverity.INFO,
    )
    _stub(_StubImporter(template=_make_template(issues=[first, second])))

    response = client.post(
        "/api/templates/import",
        files={"file": ("t.xml", _XML, "application/octet-stream")},
        headers=AUTH,
    )

    assert response.status_code == 201, response.text
    messages = [issue["message"] for issue in response.json()["issues"]]
    assert messages == ["second", "first"]


def test_missing_file_part_is_validation_error() -> None:
    response = client.post("/api/templates/import", headers=AUTH)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unparseable_multipart_body_is_validation_error() -> None:
    # A malformed multipart body (broken part framing) never parses into a `file` field;
    # the contract's §14 normalizes request-body failures to 422 VALIDATION_ERROR.
    response = client.post(
        "/api/templates/import",
        content=b"--b\r\nNone--b--\r\n",
        headers={
            "Authorization": "Bearer dev",
            "Content-Type": "multipart/form-data; boundary=b",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_no_authorization_header_is_401() -> None:
    response = client.post(
        "/api/templates/import",
        files={"file": ("t.xml", _XML, "application/octet-stream")},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_oversized_upload_is_413() -> None:
    _stub(_StubImporter(template=_make_template()))
    data = b"<worksheet>" + b"x" * (10 * 1024 * 1024)
    response = client.post(
        "/api/templates/import",
        files={"file": ("big.xlsx", data, "application/octet-stream")},
        headers=AUTH,
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_unrecognized_extension_is_415() -> None:
    response = client.post(
        "/api/templates/import",
        files={"file": ("template.txt", b"hello", "text/plain")},
        headers=AUTH,
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "INVALID_FILE"


def test_xlsx_with_non_zip_content_is_415() -> None:
    response = client.post(
        "/api/templates/import",
        files={"file": ("template.xlsx", b"not a zip at all", "application/octet-stream")},
        headers=AUTH,
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "INVALID_FILE"


def test_xml_with_non_xml_content_is_415() -> None:
    response = client.post(
        "/api/templates/import",
        files={"file": ("template.xml", b"\x00\x01\x02", "application/octet-stream")},
        headers=AUTH,
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "INVALID_FILE"


def test_corrupt_xlsx_is_422_invalid_xlsx() -> None:
    # PK magic makes it a recognized container; the importer then reports it unreadable.
    corrupt = b"PK\x03\x04" + b"garbage"
    _stub(_StubImporter(error=TemplateImportError("not a readable ZIP")))
    response = client.post(
        "/api/templates/import",
        files={"file": ("template.xlsx", corrupt, "application/octet-stream")},
        headers=AUTH,
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "INVALID_XLSX"
    assert "not a readable ZIP" in body["error"]["details"]["reason"]


def test_importer_failure_is_422_invalid_xlsx() -> None:
    _stub(_StubImporter(error=TemplateImportError("worksheet contains no sheetData")))
    response = client.post(
        "/api/templates/import",
        files={"file": ("template.xml", _XML, "application/octet-stream")},
        headers=AUTH,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_XLSX"


def test_real_spectora_worksheet_imports_end_to_end() -> None:
    from pathlib import Path

    # Real importer through the app; a fresh in-memory repository keeps the API test
    # hermetic (the Postgres adapter has its own dedicated live-DB suite).
    _stub()
    repo_root = Path(__file__).resolve().parents[2]
    worksheet = (repo_root / "sample-data" / "sheet1.xml").read_bytes()
    response = client.post(
        "/api/templates/import",
        files={"file": ("sheet1.xml", worksheet, "application/xml")},
        headers=AUTH,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["template"]["name"] == "sheet1"
    assert body["template"]["source_filename"] == "sheet1.xml"
    assert len(body["template"]["sections"]) > 0
    assert uuid.UUID(body["template"]["id"])
    assert uuid.UUID(response.headers["Location"].rsplit("/", 1)[-1])