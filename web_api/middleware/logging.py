"""Basic request logging middleware."""
from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


logger = logging.getLogger("web_api")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "web_api_request method=%s path=%s status=%s elapsed_ms=%s request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            getattr(request.state, "request_id", None),
        )
        return response
