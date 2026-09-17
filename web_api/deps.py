"""Dependency and helper primitives for the web API scaffold."""
from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, HTTPException, Request, status

from app_services.sessions.service import SessionsService
from app_services.analytics.service import AnalyticsService
from app_services.analytics.public_service import PublicAnalyticsService
from app_services.accounts.service import AccountsService
from app_services.billing.balance_service import BalanceService
from app_services.billing.checkout_service import CheckoutService
from app_services.uploads.service import UploadsService
from app_services.idempotency.service import IdempotencyService
from app_services.drafts.design_service import DesignDraftService
from app_services.drafts.furniture_service import FurnitureDraftService
from app_services.jobs.service import JobsService
from app_services.history.service import HistoryService
from app_services.design.result_service import DesignResultService
from app_services.furniture.result_service import FurnitureResultService
from app_services.support.service import SupportService
from config import Settings
def api_not_implemented(feature: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "error": {
                "code": "NOT_IMPLEMENTED",
                "message": f"{feature} is not implemented yet.",
            }
        },
    )


def get_request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@lru_cache
def get_settings() -> Settings:
    return Settings(APP_MODE="web", _env_file=".env")

@lru_cache
def get_sessions_service() -> SessionsService:
    return SessionsService(get_settings())


@lru_cache
def get_accounts_service() -> AccountsService:
    return AccountsService()


@lru_cache
def get_analytics_service() -> AnalyticsService:
    return AnalyticsService()


@lru_cache
def get_public_analytics_service() -> PublicAnalyticsService:
    return PublicAnalyticsService()


@lru_cache
def get_balance_service() -> BalanceService:
    return BalanceService()


@lru_cache
def get_checkout_service() -> CheckoutService:
    return CheckoutService(get_settings())


@lru_cache
def get_uploads_service() -> UploadsService:
    return UploadsService(get_settings())


@lru_cache
def get_idempotency_service() -> IdempotencyService:
    return IdempotencyService()


@lru_cache
def get_design_draft_service() -> DesignDraftService:
    return DesignDraftService(get_settings())


@lru_cache
def get_furniture_draft_service() -> FurnitureDraftService:
    return FurnitureDraftService(get_settings())


@lru_cache
def get_jobs_service() -> JobsService:
    return JobsService(get_settings())


@lru_cache
def get_history_service() -> HistoryService:
    return HistoryService(get_settings())


@lru_cache
def get_design_result_service() -> DesignResultService:
    return DesignResultService(get_settings())


@lru_cache
def get_furniture_result_service() -> FurnitureResultService:
    return FurnitureResultService(get_settings())


def get_support_service(
    settings: Settings = Depends(get_settings),
    analytics: AnalyticsService = Depends(get_analytics_service),
) -> SupportService:
    return SupportService(settings, analytics)


async def get_current_session_context(
    request: Request,
    settings: Settings = Depends(get_settings),
    service: SessionsService = Depends(get_sessions_service),
    balance_service: BalanceService = Depends(get_balance_service),
) -> dict:
    session_token = request.cookies.get(settings.AUTH_SESSION_COOKIE_NAME, "")
    current = await service.get_current_session(session_token)
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Session is missing or expired.",
                }
            },
        )
    path = request.url.path or ""
    include_balance = request.method.upper() == "GET" and (
        path.endswith("/auth/me") or path.endswith("/account") or path.endswith("/account/balance")
    )
    if include_balance:
        current["balance"] = await balance_service.get_balance(current["account"]["id"])
    else:
        current["balance"] = {"credits": 0}
    return current
