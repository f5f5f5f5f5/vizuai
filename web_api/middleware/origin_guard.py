"""Origin / referer guard for cookie-authenticated and browser-initiated writes."""
from __future__ import annotations

from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from config import Settings


class OriginGuardMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        configured = {item.rstrip("/") for item in settings.web_allowed_origins}
        configured.add(str(settings.WEB_APP_URL).rstrip("/"))
        configured.add(str(settings.WEB_PUBLIC_URL).rstrip("/"))
        self._allowed_origins = {
            self._normalize_origin(origin)
            for origin in configured
            if self._normalize_origin(origin)
        }
        self._protected_methods = {"POST", "PUT", "PATCH", "DELETE"}
        self._exempt_prefixes = {
            "/healthz",
        }

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._should_validate(request):
            return await call_next(request)

        origin = self._normalize_origin(request.headers.get("origin"))
        referer_origin = self._normalize_origin(request.headers.get("referer"))
        if origin:
            if origin not in self._allowed_origins:
                return self._forbidden("Origin is not allowed.")
        elif referer_origin:
            if referer_origin not in self._allowed_origins:
                return self._forbidden("Referer origin is not allowed.")
        elif request.headers.get("cookie"):
            return self._forbidden("Missing origin metadata for cookie-authenticated request.")

        return await call_next(request)

    def _should_validate(self, request: Request) -> bool:
        if request.method.upper() not in self._protected_methods:
            return False
        path = request.url.path or ""
        if path in self._exempt_prefixes:
            return False
        return path.startswith("/api/")

    @staticmethod
    def _normalize_origin(value: str | None) -> str | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        parsed = urlparse(raw)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        return raw.rstrip("/")

    @staticmethod
    def _forbidden(message: str) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={
                "ok": False,
                "error": {
                    "code": "ORIGIN_NOT_ALLOWED",
                    "message": message,
                },
                "meta": {},
            },
        )
