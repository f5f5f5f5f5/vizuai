"""Redis-backed rate limiting middleware for web API."""
from __future__ import annotations
import hashlib
import logging
import time
from dataclasses import dataclass

from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from config import Settings
from utils.observability import emit_observability_event
from web_api.contracts import error_payload

logger = logging.getLogger("web_api.rate_limit")


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    limit: int
    window_seconds: int


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings
        self._enabled = bool(settings.WEB_RATE_LIMIT_ENABLED)
        self._redis: Redis | None = None
        self._redis_failed_open = False

    async def dispatch(self, request: Request, call_next):
        if not self._enabled:
            return await call_next(request)

        rule = self._match_rule(request)
        if rule is None or rule.limit <= 0 or rule.window_seconds <= 0:
            return await call_next(request)

        subject = self._subject_key(request)
        bucket = self._current_bucket(rule.window_seconds)
        redis_key = f"web_rl:{rule.name}:{bucket}:{subject}"

        try:
            current = await self._increment(redis_key, rule.window_seconds)
        except Exception as exc:
            if not self._redis_failed_open:
                self._redis_failed_open = True
                emit_observability_event(
                    logger,
                    "web_rate_limit_backend_failed_open",
                    level="warning",
                    request=request,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    exc_info=exc,
                )
            return await call_next(request)

        remaining = max(rule.limit - current, 0)
        reset_seconds = self._seconds_until_next_bucket(rule.window_seconds)

        if current > rule.limit:
            emit_observability_event(
                logger,
                "web_rate_limit_exceeded",
                level="warning",
                request=request,
                rule=rule.name,
                limit=rule.limit,
                window_seconds=rule.window_seconds,
                subject=subject,
            )
            response = JSONResponse(
                status_code=429,
                content=error_payload(
                    "RATE_LIMITED",
                    "Too many requests. Please wait and try again.",
                    request=request,
                    details={
                        "rule": rule.name,
                        "limit": rule.limit,
                        "window_seconds": rule.window_seconds,
                        "retry_after_seconds": reset_seconds,
                    },
                ),
            )
            self._apply_headers(response, rule, remaining=0, reset_seconds=reset_seconds)
            response.headers["Retry-After"] = str(reset_seconds)
            return response

        response = await call_next(request)
        self._apply_headers(response, rule, remaining=remaining, reset_seconds=reset_seconds)
        return response

    def _match_rule(self, request: Request) -> RateLimitRule | None:
        path = request.url.path
        method = request.method.upper()

        if path == "/healthz":
            return None
        if path.startswith("/api/public/analytics") or path.startswith("/api/v1/public/analytics"):
            return RateLimitRule(
                "public_analytics",
                self._settings.WEB_RATE_LIMIT_PUBLIC_ANALYTICS_LIMIT,
                self._settings.WEB_RATE_LIMIT_PUBLIC_ANALYTICS_WINDOW_SECONDS,
            )
        if path.endswith("/auth/start") and method == "POST":
            return RateLimitRule(
                "auth_start",
                self._settings.WEB_RATE_LIMIT_AUTH_START_LIMIT,
                self._settings.WEB_RATE_LIMIT_AUTH_START_WINDOW_SECONDS,
            )
        if path.endswith("/auth/verify") and method == "POST":
            return RateLimitRule(
                "auth_verify",
                self._settings.WEB_RATE_LIMIT_AUTH_VERIFY_LIMIT,
                self._settings.WEB_RATE_LIMIT_AUTH_VERIFY_WINDOW_SECONDS,
            )
        if "/uploads" in path and method == "POST":
            return RateLimitRule(
                "uploads",
                self._settings.WEB_RATE_LIMIT_UPLOAD_LIMIT,
                self._settings.WEB_RATE_LIMIT_UPLOAD_WINDOW_SECONDS,
            )
        if path.endswith("/design/jobs") and method == "POST":
            return RateLimitRule(
                "design_job_create",
                self._settings.WEB_RATE_LIMIT_JOB_CREATE_LIMIT,
                self._settings.WEB_RATE_LIMIT_JOB_CREATE_WINDOW_SECONDS,
            )
        if path.endswith("/furniture/jobs") and method == "POST":
            return RateLimitRule(
                "furniture_job_create",
                self._settings.WEB_RATE_LIMIT_JOB_CREATE_LIMIT,
                self._settings.WEB_RATE_LIMIT_JOB_CREATE_WINDOW_SECONDS,
            )
        if path.endswith("/billing/checkout") and method == "POST":
            return RateLimitRule(
                "billing_checkout_create",
                self._settings.WEB_RATE_LIMIT_BILLING_CHECKOUT_LIMIT,
                self._settings.WEB_RATE_LIMIT_BILLING_CHECKOUT_WINDOW_SECONDS,
            )
        if path.startswith("/api/public") or path.startswith("/api/v1/public"):
            return RateLimitRule(
                "public_api",
                self._settings.WEB_RATE_LIMIT_PUBLIC_LIMIT,
                self._settings.WEB_RATE_LIMIT_PUBLIC_WINDOW_SECONDS,
            )
        if path.startswith("/api/") or path.startswith("/api/v1/"):
            return RateLimitRule(
                "app_api",
                self._settings.WEB_RATE_LIMIT_APP_LIMIT,
                self._settings.WEB_RATE_LIMIT_APP_WINDOW_SECONDS,
            )
        return None

    def _subject_key(self, request: Request) -> str:
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        client_ip = forwarded_for.split(",")[0].strip() or (request.client.host if request.client else "unknown")
        cookie = request.cookies.get(self._settings.AUTH_SESSION_COOKIE_NAME, "")
        if cookie:
            digest = hashlib.sha256(cookie.encode("utf-8")).hexdigest()[:16]
            return f"ip:{client_ip}:session:{digest}"
        return f"ip:{client_ip}"

    async def _increment(self, redis_key: str, ttl_seconds: int) -> int:
        redis = await self._get_redis()
        current = await redis.incr(redis_key)
        if current == 1:
            await redis.expire(redis_key, ttl_seconds)
        return int(current)

    async def _get_redis(self) -> Redis:
        if not self._settings.REDIS_URL:
            raise RuntimeError("REDIS_URL is not configured")
        if self._redis is None:
            self._redis = Redis.from_url(self._settings.REDIS_URL, decode_responses=True)
        return self._redis

    @staticmethod
    def _current_bucket(window_seconds: int) -> int:
        return int(time.time()) // max(window_seconds, 1)

    @staticmethod
    def _seconds_until_next_bucket(window_seconds: int) -> int:
        now = int(time.time())
        return max(window_seconds - (now % max(window_seconds, 1)), 1)

    @staticmethod
    def _apply_headers(response, rule: RateLimitRule, *, remaining: int, reset_seconds: int) -> None:
        response.headers["X-RateLimit-Limit"] = str(rule.limit)
        response.headers["X-RateLimit-Remaining"] = str(max(remaining, 0))
        response.headers["X-RateLimit-Reset"] = str(reset_seconds)

    async def shutdown(self) -> None:
        if self._redis is not None:
            await self._redis.close()
            await self._redis.connection_pool.disconnect()
            self._redis = None
