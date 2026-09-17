"""Auth route scaffold."""
from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app_services.analytics.events import EVENT_AUTH_LOGOUT, EVENT_AUTH_VERIFIED
from config import Settings
from web_api.contracts import json_success, success_payload
from web_api.deps import (
    get_analytics_service,
    get_current_session_context,
    get_sessions_service,
    get_settings,
)
from web_api.schemas.auth import (
    AuthMeResponse,
    AuthStartRequest,
    AuthStartResponse,
    AuthVerifyRequest,
    AuthVerifyResponse,
)

router = APIRouter()


def _should_use_secure_cookie(request: Request, settings: Settings) -> bool:
    request_host = (request.url.hostname or "").strip().lower()
    if request_host in {"localhost", "127.0.0.1"}:
        return False

    origin = (request.headers.get("origin") or "").strip()
    if origin:
        origin_host = (urlparse(origin).hostname or "").strip().lower()
        if origin_host in {"localhost", "127.0.0.1"}:
            return False

    app_host = (urlparse(settings.WEB_APP_URL).hostname or "").strip().lower()
    api_host = (urlparse(settings.WEB_API_URL).hostname or "").strip().lower()
    if app_host in {"localhost", "127.0.0.1"} or api_host in {"localhost", "127.0.0.1"}:
        return False

    return True


def _json_success_with_cookie(
    data: dict,
    *,
    request: Request,
    cookie_name: str,
    cookie_value: str,
    secure: bool,
    max_age: int,
) -> JSONResponse:
    response = JSONResponse(
        status_code=200,
        content=success_payload(data, request=request),
    )
    response.set_cookie(
        key=cookie_name,
        value=cookie_value,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=max_age,
        path="/",
    )
    return response


def _json_success_with_cookie_delete(
    data: dict,
    *,
    request: Request,
    cookie_name: str,
    secure: bool,
) -> JSONResponse:
    response = JSONResponse(
        status_code=200,
        content=success_payload(data, request=request),
    )
    response.delete_cookie(
        key=cookie_name,
        path="/",
        secure=secure,
        httponly=True,
        samesite="lax",
    )
    return response


@router.post("/start")
async def start_magic_link(
    payload: AuthStartRequest,
    request: Request,
    service=Depends(get_sessions_service),
):
    result = await service.start_magic_link(payload.email, locale=payload.locale)
    if result.get("status") != "magic_link_sent":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "VALIDATION_ERROR", "message": "Invalid email."}},
        )
    payload_model = AuthStartResponse(status="magic_link_sent")
    return json_success(payload_model.model_dump(mode="json"), request=request)


@router.post("/verify")
async def verify_magic_link(
    payload: AuthVerifyRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    service=Depends(get_sessions_service),
    analytics=Depends(get_analytics_service),
):
    result = await service.verify_magic_link(
        payload.token,
        anon_id=payload.anon_id,
        acquisition=payload.acquisition.model_dump(exclude_none=True) if payload.acquisition else None,
        locale=payload.locale,
    )
    if result.get("status") != "ok":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Magic link is invalid or expired."}},
        )

    secure_cookie = _should_use_secure_cookie(request, settings)
    await analytics.record_event(
        result["account"]["id"],
        event_type=EVENT_AUTH_VERIFIED,
        screen_key="auth",
        action_key="magic_link_verify",
        source="web_api",
    )
    payload_model = AuthVerifyResponse(
        account=result["account"],
        session={"expires_at": result["session_expires_at"]},
    )
    return _json_success_with_cookie(
        payload_model.model_dump(mode="json"),
        request=request,
        cookie_name=settings.AUTH_SESSION_COOKIE_NAME,
        cookie_value=result["raw_session_token"],
        secure=secure_cookie,
        max_age=max(int(settings.AUTH_SESSION_TTL_DAYS), 1) * 24 * 60 * 60,
    )


@router.post("/logout")
async def logout(
    request: Request,
    settings: Settings = Depends(get_settings),
    service=Depends(get_sessions_service),
    analytics=Depends(get_analytics_service),
):
    session_token = request.cookies.get(settings.AUTH_SESSION_COOKIE_NAME, "")
    current = await service.get_current_session(session_token)
    await service.logout(session_token)
    secure_cookie = _should_use_secure_cookie(request, settings)
    if current is not None:
        await analytics.record_event(
            current["account"]["id"],
            event_type=EVENT_AUTH_LOGOUT,
            screen_key="auth",
            action_key="logout",
            source="web_api",
        )
    return _json_success_with_cookie_delete(
        {"status": "logged_out"},
        request=request,
        cookie_name=settings.AUTH_SESSION_COOKIE_NAME,
        secure=secure_cookie,
    )


@router.get("/me")
async def me(
    request: Request,
    current=Depends(get_current_session_context),
):
    payload = AuthMeResponse(account=current["account"], balance=current["balance"])
    return json_success(payload.model_dump(mode="json"), request=request)
