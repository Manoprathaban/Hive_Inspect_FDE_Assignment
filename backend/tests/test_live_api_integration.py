"""Phase 5 integration: the running stack (API + PostgreSQL) driven the way the frontend
drives it.

The unit/API suites use the in-memory repository and the TestClient, so they cannot catch
what only shows up against real SQL and a real server: the serialized response shapes,
the actual multipart import of the committed Spectora export, persistence of the three
PATCHes, duplicate independence, CORS for the browser origin, and the error contract the
frontend maps to messages.

The suite is opt-in and talks to an already-running server over HTTP:

    cd backend
    uv run uvicorn app.main:app --host 127.0.0.1 --port 8020
    LIVE_API_BASE_URL=http://127.0.0.1:8020 uv run pytest tests/test_live_api_integration.py

It follows FRONTEND_DESIGN §28 (the five acceptance flows) and §20 (the error envelope), so
a failure here means the frontend's screens would misbehave. It skips itself when
``LIVE_API_BASE_URL`` is unset, keeping the offline run and CI green. ``LIVE_API_TOKEN``
overrides the development bearer token; the backend ignores its value while ``APP_ENV`` is
not ``production``.

The canonical export is imported once for the whole module (a cold import of the deployed
database takes a while) and deleted again through PostgreSQL afterwards — the API contract
has no delete route. Copies created by the duplicate test are removed the same way. When
no ``DATABASE_URL`` is available the suite still runs and reports the ids it created.
"""

from __future__ import annotations

import asyncio
import os
import urllib.parse
import uuid
from collections.abc import Iterator
from pathlib import Path

import asyncpg
import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_EXPORT = REPO_ROOT / "sample-data" / "sheet1.xml"

BASE_URL = os.environ.get("LIVE_API_BASE_URL", "").rstrip("/")
AUTH_HEADERS = {"Authorization": f"Bearer {os.environ.get('LIVE_API_TOKEN', 'dev:demo@hive.test')}"}

# The importer's own integration expectations for the committed export.
EXPECTED_COUNTS = {"sections": 13, "items": 69, "comments": 392, "comment_options": 520}
BROWSER_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "LIVE_API_CORS_ORIGINS", "http://localhost:5173,http://localhost:4173,http://localhost:3000"
    ).split(",")
    if origin.strip()
]

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="no running API; set LIVE_API_BASE_URL to run the live stack integration suite",
)

_created_ids: list[str] = []


def _database_url() -> str | None:
    env_path = REPO_ROOT / "backend" / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("DATABASE_URL="):
            return line.partition("=")[2].strip() or None
    return None


def _delete_templates(template_ids: list[str]) -> bool:
    """Delete templates through PostgreSQL (the contract has no delete route).

    Returns whether the deletion ran. The count is verified afterwards, so a silent
    cleanup failure (wrong database, missing cascade) fails the suite instead of leaving
    data behind.
    """

    ids = [value for value in template_ids if value]
    dsn = _database_url()
    if not dsn or not ids:
        return False
    parsed = urllib.parse.urlsplit(dsn)
    config = {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": parsed.username,
        "password": parsed.password,
        "database": parsed.path.lstrip("/") or "postgres",
        "ssl": "require" if parsed.query else None,
    }

    async def run() -> None:
        connection = await asyncpg.connect(**{k: v for k, v in config.items() if v is not None})
        try:
            await connection.execute("DELETE FROM public.templates WHERE id = ANY($1::uuid[])", ids)
            remaining = await connection.fetchval(
                "SELECT count(*) FROM public.templates WHERE id = ANY($1::uuid[])", ids
            )
            assert remaining == 0, f"{remaining} of {ids} still present after delete"
        finally:
            await connection.close()

    asyncio.run(run())
    return True


def _count_hierarchy(template: dict) -> dict[str, int]:
    counts = {"sections": 0, "items": 0, "comments": 0, "comment_options": 0}
    for section in template["sections"]:
        counts["sections"] += 1
        for item in section["items"]:
            counts["items"] += 1
            for comment in item["comments"]:
                counts["comments"] += 1
                counts["comment_options"] += len(comment["options"])
    return counts


@pytest.fixture(scope="module")
def client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=600.0) as http:
        yield http


@pytest.fixture(scope="module")
def imported(client: httpx.Client) -> Iterator[dict]:
    """Import the committed export once and remove it (and any copy) on teardown."""

    assert SAMPLE_EXPORT.exists(), f"missing canonical export: {SAMPLE_EXPORT}"
    with SAMPLE_EXPORT.open("rb") as handle:
        response = client.post(
            "/api/templates/import",
            headers=AUTH_HEADERS,
            files={"file": (SAMPLE_EXPORT.name, handle, "application/xml")},
        )
    assert response.status_code == 201, response.text
    payload = response.json()
    template_id: str = payload["template"]["id"]
    _created_ids.append(template_id)
    try:
        yield {"id": template_id, "template": payload["template"], "issues": payload["issues"]}
    finally:
        if not _delete_templates(list(_created_ids)):
            pytest.fail(f"could not clean up templates {_created_ids}; delete them manually")


def test_health_reports_ok(client: httpx.Client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_returns_contract_shapes(client: httpx.Client, imported: dict) -> None:
    response = client.get("/api/templates", headers=AUTH_HEADERS)
    assert response.status_code == 200
    summaries = response.json()
    assert isinstance(summaries, list)
    required = {"id", "name", "source", "source_filename", "created_at", "updated_at"}
    assert all(required <= set(summary) for summary in summaries)
    assert imported["id"] in {summary["id"] for summary in summaries}


def test_flow_1_import_matches_the_canonical_export(imported: dict) -> None:
    """FLOW 1 — import: the response is exactly what the viewer renders."""

    assert _count_hierarchy(imported["template"]) == EXPECTED_COUNTS
    issues = imported["issues"]
    assert len(issues) == 4
    assert {issue["issue_type"] for issue in issues} == {
        "SOURCE_DATA_MISSING",
        "UNSUPPORTED_CONTENT",
    }


def test_flow_2_edits_persist_across_a_refetch(client: httpx.Client, imported: dict) -> None:
    """FLOW 2 — rename section, rename item, edit comment content, then re-read."""

    template_id = imported["id"]
    fetched = client.get(f"/api/templates/{template_id}", headers=AUTH_HEADERS)
    assert fetched.status_code == 200
    template = fetched.json()
    section = template["sections"][0]
    item = section["items"][0]
    comment = item["comments"][0]

    renamed = client.patch(
        f"/api/templates/{template_id}/sections/{section['id']}",
        headers=AUTH_HEADERS,
        json={"name": "Integration section"},
    )
    assert renamed.status_code == 204
    assert renamed.content == b"", "204 must not carry a body"

    assert (
        client.patch(
            f"/api/templates/{template_id}/items/{item['id']}",
            headers=AUTH_HEADERS,
            json={"name": "Integration item"},
        ).status_code
        == 204
    )
    assert (
        client.patch(
            f"/api/templates/{template_id}/comments/{comment['id']}",
            headers=AUTH_HEADERS,
            json={"content": "Integration content"},
        ).status_code
        == 204
    )

    again = client.get(f"/api/templates/{template_id}", headers=AUTH_HEADERS).json()
    assert again["sections"][0]["name"] == "Integration section"
    assert again["sections"][0]["items"][0]["name"] == "Integration item"
    assert again["sections"][0]["items"][0]["comments"][0]["content"] == "Integration content"
    orders = [each["display_order"] for each in again["sections"]]
    assert orders == sorted(orders), "display_order must survive a round trip"
    assert len(again["sections"][0]["items"][0]["comments"][0]["options"]) == len(
        comment["options"]
    ), "comment options must not be lost by an edit"


def test_flow_3_duplicate_is_independent(client: httpx.Client, imported: dict) -> None:
    """FLOW 3 — duplicate: fresh ids, same hierarchy, and edits stay on the copy."""

    template_id = imported["id"]
    response = client.post(
        f"/api/templates/{template_id}/duplicate",
        headers=AUTH_HEADERS,
        json={"name": "Integration copy"},
    )
    assert response.status_code == 201, response.text
    copy = response.json()
    copy_id: str = copy["id"]
    _created_ids.append(copy_id)
    try:
        assert copy_id != template_id
        assert copy["copied_from_id"] == template_id
        assert copy["name"] == "Integration copy"
        assert _count_hierarchy(copy) == EXPECTED_COUNTS

        stored = client.get(f"/api/templates/{copy_id}", headers=AUTH_HEADERS).json()
        original = client.get(f"/api/templates/{template_id}", headers=AUTH_HEADERS).json()
        assert stored["sections"][0]["id"] != original["sections"][0]["id"]
        assert (
            stored["sections"][0]["items"][0]["comments"][0]["id"]
            != (original["sections"][0]["items"][0]["comments"][0]["id"])
        )
        # A duplicate carries no import issues of its own.
        copy_issues = client.get(f"/api/templates/{copy_id}/import-issues", headers=AUTH_HEADERS)
        assert copy_issues.status_code == 200
        assert copy_issues.json() == []

        assert (
            client.patch(
                f"/api/templates/{copy_id}/sections/{stored['sections'][0]['id']}",
                headers=AUTH_HEADERS,
                json={"name": "Copy only"},
            ).status_code
            == 204
        )
        untouched = client.get(f"/api/templates/{template_id}", headers=AUTH_HEADERS).json()
        assert untouched["sections"][0]["name"] == original["sections"][0]["name"]
    finally:
        _delete_templates([copy_id])
        _created_ids.remove(copy_id)


def test_flow_4_invalid_upload_is_rejected_without_persisting(client: httpx.Client) -> None:
    """FLOW 4 — a non-export file produces the mapped error and stores nothing."""

    before = client.get("/api/templates", headers=AUTH_HEADERS).json()
    response = client.post(
        "/api/templates/import",
        headers=AUTH_HEADERS,
        files={"file": ("notes.txt", b"not a spectora export", "text/plain")},
    )
    assert response.status_code == 415
    error = response.json()["error"]
    assert error["code"] == "INVALID_FILE"
    assert error["message"]
    after = client.get("/api/templates", headers=AUTH_HEADERS).json()
    assert len(after) == len(before), "a rejected upload must not persist anything"


def test_flow_5_unsupported_content_is_explainable(client: httpx.Client, imported: dict) -> None:
    """FLOW 5 — the issues endpoint answers "what was skipped, and why"."""

    response = client.get(f"/api/templates/{imported['id']}/import-issues", headers=AUTH_HEADERS)
    assert response.status_code == 200
    issues = response.json()
    assert len(issues) == 4
    for issue in issues:
        assert issue["issue_type"] in {
            "SOURCE_DATA_MISSING",
            "UNSUPPORTED_CONTENT",
            "INVALID_SOURCE_DATA",
        }
        assert issue["severity"] in {"info", "warning", "error"}
        assert issue["message"]
    unsupported = [issue for issue in issues if issue["issue_type"] == "UNSUPPORTED_CONTENT"]
    assert unsupported, "the export's unsupported columns must be reported, never dropped silently"
    assert any(issue["source_field"] or issue["source_row"] is not None for issue in unsupported)


def test_unknown_template_is_an_indistinguishable_404(client: httpx.Client) -> None:
    """The contract never reveals whether someone else's template exists."""

    response = client.get(f"/api/templates/{uuid.uuid4()}", headers=AUTH_HEADERS)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TEMPLATE_NOT_FOUND"
    assert response.json()["error"]["details"] is None


def test_missing_bearer_token_is_401(client: httpx.Client) -> None:
    response = client.get("/api/templates")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_cors_allows_the_origins_the_browser_uses(client: httpx.Client) -> None:
    """The frontend is a browser client: preflight must succeed for its dev/preview origins."""

    requests = [
        ("GET", "/api/templates", "authorization"),
        ("POST", "/api/templates/import", "authorization,content-type"),
        (
            "PATCH",
            "/api/templates/00000000-0000-0000-0000-000000000000"
            "/sections/00000000-0000-0000-0000-000000000000",
            "authorization,content-type",
        ),
    ]
    for origin in BROWSER_ORIGINS:
        for method, path, request_headers in requests:
            preflight = client.request(
                "OPTIONS",
                path,
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": method,
                    "Access-Control-Request-Headers": request_headers,
                },
            )
            assert preflight.status_code == 200, (origin, method, preflight.text)
            assert preflight.headers.get("access-control-allow-origin") == origin
            allowed_headers = preflight.headers.get("access-control-allow-headers", "").lower()
            assert "authorization" in allowed_headers
            if method != "GET":
                assert method in preflight.headers.get("access-control-allow-methods", "")

    actual = client.get("/api/templates", headers={**AUTH_HEADERS, "Origin": BROWSER_ORIGINS[0]})
    assert actual.status_code == 200
    assert actual.headers.get("access-control-allow-origin") == BROWSER_ORIGINS[0]
