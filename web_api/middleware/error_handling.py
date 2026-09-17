"""Global error handling helpers."""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from utils.observability import emit_observability_event
from web_api.contracts import error_payload

logger = logging.getLogger("web_api.errors")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        error_code = "HTTP_ERROR"
        error_message = str(exc.detail)
        error_details = None
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            error = exc.detail["error"]
            error_code = str(error.get("code") or "HTTP_ERROR")
            error_message = str(error.get("message") or "HTTP error.")
            error_details = error.get("details")
        emit_observability_event(
            logger,
            "web_api_http_error",
            level="warning" if exc.status_code < 500 else "error",
            request=request,
            status_code=exc.status_code,
            error_code=error_code,
            error_message=error_message,
            details=error_details,
        )
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content=error_payload(
                    error_code,
                    error_message,
                    request=request,
                    details=error_details,
                ),
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                "HTTP_ERROR",
                str(exc.detail),
                request=request,
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        emit_observability_event(
            logger,
            "web_api_unhandled_exception",
            level="error",
            request=request,
            error_type=type(exc).__name__,
            error_message=str(exc) or "Unhandled server error.",
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content=error_payload(
                "INTERNAL_ERROR",
                str(exc) or "Unhandled server error.",
                request=request,
            ),
        )
