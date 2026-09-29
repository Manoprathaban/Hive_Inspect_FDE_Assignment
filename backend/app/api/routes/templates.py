"""Template API routes (FastAPI, thin).

Read paths (``docs/API-CONTRACTS.md`` §9.1/§9.2/§11):

* ``GET /api/templates`` — the caller's templates as summaries, newest first (no
  pagination, §19).
* ``GET /api/templates/{id}`` — one template's full hierarchy; missing **or** foreign is
  the generic ``404 TEMPLATE_NOT_FOUND`` (§20, never distinguishable).
* ``GET /api/templates/{id}/import-issues`` — persisted diagnostics, newest first;
  ``404 TEMPLATE_NOT_FOUND`` when the template is missing/foreign.

Edit paths (§9.4/§10/§17):

* ``POST /api/templates/{id}/duplicate`` — independent deep copy (§17); optional
  ``{"name"}`` body (§12.3); ``201`` + the new template (§13.2) and a ``Location`` header.
* ``PATCH /api/templates/{id}/sections/{section_id}`` / ``.../items/{item_id}`` —
  ``{"name"}`` (trimmed 1–200, §10.1/§10.2); ``204``.
* ``PATCH /api/templates/{id}/comments/{comment_id}`` — ``{"content"}`` (verbatim, empty
  clears, §10.3); ``204``.
* Ownership mapping: a missing/foreign template is ``404 TEMPLATE_NOT_FOUND``; a child id
  that does not resolve under the verified-owned template is the child-specific
  ``404 SECTION_NOT_FOUND`` / ``ITEM_NOT_FOUND`` / ``COMMENT_NOT_FOUND`` (§20).

Import path (``docs/API-CONTRACTS.md`` §9.3/§18):

* ``422 VALIDATION_ERROR`` — the ``file`` part is missing (FastAPI ``File(...)``).
* ``413 FILE_TOO_LARGE`` — upload exceeds the configured 10 MiB cap.
* ``415 INVALID_FILE`` — extension/content not a recognized export container
  (extension AND content checked; the MIME header is never trusted).
* ``422 INVALID_XLSX`` — recognized container but unreadable/invalid structure; the
  importer's reason travels in ``details.reason``.
* ``201`` on success: :class:`ImportResultResponse` (persisted template + issues, newest
  first) plus ``Location: /api/templates/{id}``.

``401``/``500`` come from the shared auth dependency and the error envelope handlers.

Routes contain no business logic; all parsing lives behind the ``TemplateImporter``
protocol and persistence behind the ``TemplateRepository`` protocol.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Response, UploadFile, status
from fastapi.responses import JSONResponse

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.providers import (
    get_import_template_use_case,
    get_template_repository,
)
from app.api.errors import ApiError
from app.api.schemas.templates import (
    DuplicateRequest,
    EditCommentRequest,
    ImportIssueResponse,
    ImportResultResponse,
    RenameRequest,
    TemplateResponse,
    TemplateSummaryResponse,
)
from app.application.use_cases.import_template import ImportTemplateUseCase
from app.domain.exceptions import (
    CommentNotFoundError,
    ItemNotFoundError,
    SectionNotFoundError,
    TemplateImportError,
    TemplateNotFoundError,
)
from app.domain.models.user import UserContext
from app.infrastructure.config.settings import get_settings
from app.protocols.repositories.template_repository import TemplateRepository

__all__ = ["import_guard_router", "router"]

router = APIRouter(
    prefix="/templates",
    tags=["templates"],
    dependencies=[Depends(get_current_user)],
)

# Route guard for the fixed "/import" resource, registered ahead of the main router and
# deliberately WITHOUT the auth dependency: unsupported methods on it must answer 405 no
# matter what (or who) attempts them (matching Starlette's own method-level 405), rather
# than being shadowed by GET /{template_id} or short-circuited by 401/422.
import_guard_router = APIRouter(prefix="/templates", tags=["templates"])

_MAX_UPLOAD_BYTES = get_settings().max_upload_bytes
_ZIP_MAGIC = b"PK\x03\x04"
_RECOGNIZED_SUFFIXES = ("xlsx", "xml")


def _read_limited(file: UploadFile, *, limit: int) -> bytes:
    """Read the upload fully but cap it at ``limit`` bytes.

    Contract §18: uploaded bytes are read fully into memory with a 10 MiB cap.
    Reading ``limit + 1`` proves oversize without first buffering arbitrarily large data.
    """

    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise ApiError(
            413,
            "FILE_TOO_LARGE",
            "Upload exceeds the 10 MiB limit.",
            details={"max_bytes": limit},
        )
    return data


def _validate_container(*, filename: str, data: bytes) -> None:
    """Reject anything that is not a recognized export container (§18, row "INVALID_FILE").

    The MIME header is never trusted. A recognized extension is required, and the bytes
    must plausibly be that container:

    * ``.xlsx`` — must be a ZIP archive (PK magic); a ZIP that turns out corrupt or
      missing the worksheet is the importer's ``422 INVALID_XLSX``, not a files-type error.
    * ``.xml``  — must read as XML-ish (starts with ``<`` after an optional BOM/whitespace);
      a wrong- or broken-root ``.xml`` is the importer's ``422 INVALID_XLSX``.
    """

    suffix = filename.rsplit(".", 1)[-1].lower() if filename else ""
    if suffix == "xlsx":
        if not data.startswith(_ZIP_MAGIC):
            raise ApiError(
                415,
                "INVALID_FILE",
                "That doesn't look like a Spectora export.",
                details={"reason": "an .xlsx upload must be a ZIP-based worksheet container"},
            )
        return
    if suffix == "xml":
        stripped = data.lstrip(b"\xef\xbb\xbf \t\r\n")
        if not stripped.startswith(b"<"):
            raise ApiError(
                415,
                "INVALID_FILE",
                "That doesn't look like a Spectora export.",
                details={"reason": "an .xml upload must contain worksheet XML"},
            )
        return
    raise ApiError(
        415,
        "INVALID_FILE",
        "That doesn't look like a Spectora export.",
        details={"reason": f"unrecognized file type '.{suffix or 'none'}'"},
    )


@router.post(
    "/import",
    status_code=status.HTTP_201_CREATED,
    response_model=ImportResultResponse,
    responses={
        401: {"description": "Authentication required"},
        413: {"description": "Upload exceeds the 10 MiB limit"},
        415: {"description": "Not a recognized export container"},
        422: {"description": "Missing file part, or recognized format that cannot be read"},
        500: {"description": "Internal error"},
    },
)
async def import_template(
    file: Annotated[UploadFile, File()],
    use_case: Annotated[ImportTemplateUseCase, Depends(get_import_template_use_case)],
    repository: Annotated[TemplateRepository, Depends(get_template_repository)],
    response: Response = None,
    user: Annotated[UserContext, Depends(get_current_user)] = None,
) -> ImportResultResponse:
    """Import a Spectora export and persist it atomically with its issues."""

    data = _read_limited(file, limit=_MAX_UPLOAD_BYTES)
    _validate_container(filename=file.filename or "", data=data)

    try:
        template = use_case.execute(data, filename=file.filename or "")
    except TemplateImportError as exc:
        raise ApiError(
            422,
            "INVALID_XLSX",
            "The file could not be read as a valid Spectora template export.",
            details={"reason": str(exc)},
        ) from exc

    saved = await repository.save(template, owner_id=user.user_id)
    response.headers["Location"] = f"/api/templates/{saved.id}"
    return ImportResultResponse.from_domain(saved)


@import_guard_router.api_route(
    "/import",
    methods=["GET", "HEAD", "OPTIONS", "PUT", "PATCH", "DELETE", "TRACE"],
    include_in_schema=False,
)
async def import_only_supports_post() -> JSONResponse:
    """Return ``405`` for methods the import resource does not support.

    Without this route, ``GET /api/templates/import`` would be shadowed by the
    ``GET /api/templates/{template_id}`` route (``import`` is not a UUID, so the endpoint
    would answer ``422`` as if it were a malformed template id). The import endpoint is a
    ``POST``-only resource (§9.3); an unsupported method must be ``405`` with an honest
    ``Allow`` header, not a path-parameter validation error.
    """

    return JSONResponse(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        content={"detail": "Method Not Allowed"},
        headers={"Allow": "POST"},
    )


@router.get(
    "",
    response_model=list[TemplateSummaryResponse],
    responses={
        401: {"description": "Authentication required"},
        500: {"description": "Internal error"},
    },
)
async def list_templates(
    repository: Annotated[TemplateRepository, Depends(get_template_repository)] = None,
    user: Annotated[UserContext, Depends(get_current_user)] = None,
) -> list[TemplateSummaryResponse]:
    """List the caller's templates, most recently updated first (§9.1)."""

    summaries = await repository.list_for_user(user.user_id)
    return [TemplateSummaryResponse.from_domain(summary) for summary in summaries]


@router.get(
    "/{template_id}",
    response_model=TemplateResponse,
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Template missing or not owned (indistinguishable)"},
        422: {"description": "template_id is not a valid UUID"},
        500: {"description": "Internal error"},
    },
)
async def get_template(
    template_id: uuid.UUID,
    repository: Annotated[TemplateRepository, Depends(get_template_repository)] = None,
    user: Annotated[UserContext, Depends(get_current_user)] = None,
) -> TemplateResponse:
    """Return one template's full hierarchy (§9.2)."""

    template = await repository.get(template_id, owner_id=user.user_id)
    if template is None:
        raise ApiError(
            404,
            "TEMPLATE_NOT_FOUND",
            "Template was not found.",
        )
    return TemplateResponse.from_domain(template)


@router.get(
    "/{template_id}/import-issues",
    response_model=list[ImportIssueResponse],
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Template missing or not owned (indistinguishable)"},
        422: {"description": "template_id is not a valid UUID"},
        500: {"description": "Internal error"},
    },
)
async def list_import_issues(
    template_id: uuid.UUID,
    repository: Annotated[TemplateRepository, Depends(get_template_repository)] = None,
    user: Annotated[UserContext, Depends(get_current_user)] = None,
) -> list[ImportIssueResponse]:
    """Return a template's import issues, newest first (§11)."""

    # The repository boundary returns [] for a missing/foreign template; the template must
    # first be resolved so both cases surface as the same 404 TEMPLATE_NOT_FOUND (§20).
    template = await repository.get(template_id, owner_id=user.user_id)
    if template is None:
        raise ApiError(
            404,
            "TEMPLATE_NOT_FOUND",
            "Template was not found.",
        )
    issues = await repository.list_import_issues(template_id, owner_id=user.user_id)
    return [ImportIssueResponse.from_domain(issue) for issue in issues]


@router.post(
    "/{template_id}/duplicate",
    status_code=status.HTTP_201_CREATED,
    response_model=TemplateResponse,
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Source template missing or not owned (indistinguishable)"},
        422: {"description": "Invalid body, or template_id is not a valid UUID"},
        500: {"description": "Internal error"},
    },
)
async def duplicate_template(
    template_id: uuid.UUID,
    body: Annotated[DuplicateRequest | None, Body()] = None,
    repository: Annotated[TemplateRepository, Depends(get_template_repository)] = None,
    response: Response = None,
    user: Annotated[UserContext, Depends(get_current_user)] = None,
) -> TemplateResponse:
    """Create an independent deep copy of a template (§9.4/§17)."""

    try:
        copy = await repository.duplicate(
            template_id,
            owner_id=user.user_id,
            new_name=body.name if body is not None else None,
        )
    except TemplateNotFoundError as exc:
        raise ApiError(404, "TEMPLATE_NOT_FOUND", "Template was not found.") from exc
    response.headers["Location"] = f"/api/templates/{copy.id}"
    return TemplateResponse.from_domain(copy)


@router.patch(
    "/{template_id}/sections/{section_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Template or section not found (distinct codes, §20)"},
        422: {"description": "Invalid body, or a path id is not a valid UUID"},
        500: {"description": "Internal error"},
    },
)
async def rename_section(
    template_id: uuid.UUID,
    section_id: uuid.UUID,
    body: RenameRequest,
    repository: Annotated[TemplateRepository, Depends(get_template_repository)] = None,
    user: Annotated[UserContext, Depends(get_current_user)] = None,
) -> Response:
    """Rename a section (single-row edit, §10.1)."""

    try:
        await repository.update_section_name(
            template_id=template_id,
            section_id=section_id,
            owner_id=user.user_id,
            name=body.name,
        )
    except TemplateNotFoundError as exc:
        raise ApiError(404, "TEMPLATE_NOT_FOUND", "Template was not found.") from exc
    except SectionNotFoundError as exc:
        raise ApiError(404, "SECTION_NOT_FOUND", "Section was not found.") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/{template_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Template or item not found (distinct codes, §20)"},
        422: {"description": "Invalid body, or a path id is not a valid UUID"},
        500: {"description": "Internal error"},
    },
)
async def rename_item(
    template_id: uuid.UUID,
    item_id: uuid.UUID,
    body: RenameRequest,
    repository: Annotated[TemplateRepository, Depends(get_template_repository)] = None,
    user: Annotated[UserContext, Depends(get_current_user)] = None,
) -> Response:
    """Rename an item (single-row edit, §10.2)."""

    try:
        await repository.update_item_name(
            template_id=template_id,
            item_id=item_id,
            owner_id=user.user_id,
            name=body.name,
        )
    except TemplateNotFoundError as exc:
        raise ApiError(404, "TEMPLATE_NOT_FOUND", "Template was not found.") from exc
    except ItemNotFoundError as exc:
        raise ApiError(404, "ITEM_NOT_FOUND", "Item was not found.") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/{template_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Template or comment not found (distinct codes, §20)"},
        422: {"description": "Invalid body, or a path id is not a valid UUID"},
        500: {"description": "Internal error"},
    },
)
async def edit_comment(
    template_id: uuid.UUID,
    comment_id: uuid.UUID,
    body: EditCommentRequest,
    repository: Annotated[TemplateRepository, Depends(get_template_repository)] = None,
    user: Annotated[UserContext, Depends(get_current_user)] = None,
) -> Response:
    """Replace a comment's content verbatim; empty string clears it (§10.3)."""

    try:
        await repository.update_comment_content(
            template_id=template_id,
            comment_id=comment_id,
            owner_id=user.user_id,
            content=body.content,
        )
    except TemplateNotFoundError as exc:
        raise ApiError(404, "TEMPLATE_NOT_FOUND", "Template was not found.") from exc
    except CommentNotFoundError as exc:
        raise ApiError(404, "COMMENT_NOT_FOUND", "Comment was not found.") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
