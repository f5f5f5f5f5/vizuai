"""FastAPI application scaffold for the web-first API."""
from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import Settings
from web_api.contracts import json_success
from web_api.middleware.api_version import ApiVersionMiddleware
from web_api.middleware.error_handling import register_error_handlers
from web_api.middleware.logging import RequestLoggingMiddleware
from web_api.middleware.origin_guard import OriginGuardMiddleware
from web_api.middleware.rate_limit import RateLimitMiddleware
from web_api.middleware.request_id import RequestIdMiddleware
from web_api.routes.account import router as account_router
from web_api.routes.analytics import public_router as public_analytics_router
from web_api.routes.analytics import router as analytics_router
from web_api.routes.auth import router as auth_router
from web_api.routes.billing import router as billing_router
from web_api.routes.design import router as design_router
from web_api.routes.furniture import router as furniture_router
from web_api.routes.history import router as history_router
from web_api.routes.jobs import router as jobs_router
from web_api.routes.support import router as support_router
from web_api.routes.uploads import router as uploads_router


@lru_cache
def get_settings() -> Settings:
    return Settings(APP_MODE="web", _env_file=".env")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="VizuAI Web API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.web_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ApiVersionMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(OriginGuardMiddleware, settings=settings)
    app.add_middleware(RateLimitMiddleware, settings=settings)
    register_error_handlers(app)

    @app.get("/healthz", tags=["infra"])
    async def healthz():
        return json_success({"status": "ok"})

    def register_api_routes(prefix: str = "/api") -> None:
        app.include_router(public_analytics_router, prefix=f"{prefix}/public/analytics", tags=["public-analytics"])
        app.include_router(auth_router, prefix=f"{prefix}/auth", tags=["auth"])
        app.include_router(analytics_router, prefix=f"{prefix}/analytics", tags=["analytics"])
        app.include_router(account_router, prefix=f"{prefix}/account", tags=["account"])
        app.include_router(uploads_router, prefix=f"{prefix}/uploads", tags=["uploads"])
        app.include_router(design_router, prefix=f"{prefix}/design", tags=["design"])
        app.include_router(furniture_router, prefix=f"{prefix}/furniture", tags=["furniture"])
        app.include_router(jobs_router, prefix=f"{prefix}/jobs", tags=["jobs"])
        app.include_router(history_router, prefix=f"{prefix}/history", tags=["history"])
        app.include_router(billing_router, prefix=f"{prefix}/billing", tags=["billing"])
        app.include_router(support_router, prefix=f"{prefix}/support", tags=["support"])

    register_api_routes("/api")
    register_api_routes("/api/v1")
    return app
