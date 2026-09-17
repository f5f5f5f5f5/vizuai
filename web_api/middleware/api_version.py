"""API version response header middleware."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from web_api.contracts import API_VERSION, API_VERSION_HEADER


class ApiVersionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers[API_VERSION_HEADER] = API_VERSION
        return response
