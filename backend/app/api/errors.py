"""Standard API error envelope and FastAPI exception handlers.

Every error across the API uses the single envelope from ``docs/API-CONTRACTS.md`` §14::

    {"error": {"code": "...", "message": "...", "details": null}}

Handlers registered by :func:`register_exception_handlers` map exceptions to that shape:

* :class:`ApiError` — explicit contract error (413/415/422/401/...).
* ``RequestValidationError`` — FastAPI body/part validation → ``422 VALIDATION_ERROR``.
* any other exception — ``500 INTERNAL_ERROR`` (logged, never leaked).

Internals (stack traces, credentials, JWT/session material) are never returned to clients.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

__all__ = ["ApiError", "register_exception_handlers"]

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """A client-actionable error with the contract's stable ``code``."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def _envelope(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": jsonable_encoder(details)}}


def register_exception_handlers(app: FastAPI) -> None:
    """Wire the contract error envelope onto ``app``."""

    @app.exception_handler(ApiError)
    async def _handle_api_error(_: Any, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Any, __: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_envelope("VALIDATION_ERROR", "Request validation failed."),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        _: Any, exc: StarletteHTTPException
    ) -> JSONResponse:
        # A multipart body that cannot be parsed reaches the app as HTTPException(400)
        # (Starlette's Request.form re-raises MultiPartException that way). The contract
        # (§14) normalizes request-body failures to 422 VALIDATION_ERROR. Every other
        # status keeps Starlette's default shape (e.g. the plain "Not Found" body).
        if exc.status_code == 400:
            return JSONResponse(
                status_code=422,
                content=_envelope("VALIDATION_ERROR", "Request validation failed."),
            )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Any, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error in request handler", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_envelope("INTERNAL_ERROR", "An unexpected error occurred."),
        )