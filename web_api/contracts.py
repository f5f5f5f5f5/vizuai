"""Shared API contract helpers."""
from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


API_VERSION = "v1"
API_VERSION_HEADER = "X-VizuAI-API-Version"


def build_meta(request: Request | None = None, **extra: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {"api_version": API_VERSION}
    if request is not None:
        request_id = getattr(request.state, "request_id", None)
        if request_id:
            meta["request_id"] = request_id
    for key, value in extra.items():
        if value is not None:
            meta[key] = value
    return meta


def success_payload(
    data: Any,
    *,
    request: Request | None = None,
    **meta: Any,
) -> dict[str, Any]:
    return {
        "ok": True,
        "data": data,
        "meta": build_meta(request, **meta),
    }


def error_payload(
    code: str,
    message: str,
    *,
    request: Request | None = None,
    details: Any = None,
    **meta: Any,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {
        "ok": False,
        "error": error,
        "meta": build_meta(request, **meta),
    }


def json_success(
    data: Any,
    *,
    request: Request | None = None,
    status_code: int = 200,
    **meta: Any,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(success_payload(data, request=request, **meta)),
    )
