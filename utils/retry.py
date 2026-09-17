"""Async retry helper with exponential backoff."""
from __future__ import annotations

import asyncio
import random
import re
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit

try:
    from aiohttp import ClientResponseError, ClientError
except Exception:  # pragma: no cover - optional import
    ClientResponseError = None  # type: ignore
    ClientError = Exception  # type: ignore

try:
    from google.api_core.exceptions import GoogleAPICallError
except Exception:  # pragma: no cover - optional import
    GoogleAPICallError = Exception  # type: ignore


DEFAULT_RETRY_STATUSES = (408, 429, 500, 502, 503, 504)


async def async_retry(
    func,
    *args,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 8.0,
    retry_statuses: Iterable[int] = DEFAULT_RETRY_STATUSES,
    logger=None,
    label: str = "call",
    **kwargs,
):
    for attempt in range(1, attempts + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            status = _extract_status(exc)
            should_retry = _should_retry(exc, status, retry_statuses)
            if not should_retry or attempt == attempts:
                raise
            delay = _compute_delay(exc, attempt, base_delay, max_delay)
            if logger:
                logger.warning(
                    (
                        "%s failed (attempt %s/%s, status=%s, error_type=%s, error=%s). "
                        "Retrying in %.1fs."
                    ),
                    label,
                    attempt,
                    attempts,
                    status,
                    type(exc).__name__,
                    _format_exception_short(exc),
                    delay,
                )
            await asyncio.sleep(delay)


def _should_retry(exc: Exception, status: int | None, retry_statuses: Iterable[int]) -> bool:
    if status is not None and status in retry_statuses:
        return True
    if isinstance(exc, (asyncio.TimeoutError, GoogleAPICallError, ClientError)):
        return True
    return False


def _extract_status(exc: Exception) -> int | None:
    status = getattr(exc, "status", None)
    if status is not None:
        return status
    status = getattr(exc, "status_code", None)
    if status is not None:
        return status
    return None


def _compute_delay(exc: Exception, attempt: int, base_delay: float, max_delay: float) -> float:
    retry_after = _get_retry_after(exc)
    if retry_after:
        return retry_after
    delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
    return delay + random.uniform(0, 0.2)


def _get_retry_after(exc: Exception) -> float | None:
    headers = getattr(exc, "headers", None)
    if not headers:
        return None
    value = headers.get("Retry-After") if hasattr(headers, "get") else None
    if not value:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_exception_short(exc: Exception, max_len: int = 240) -> str:
    text = _sanitize_log_text(str(exc).strip() or repr(exc))
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


_SENSITIVE_QUERY_KEYS = (
    "api_key",
    "x-goog-signature",
    "x-goog-credential",
    "x-goog-date",
    "x-goog-signedheaders",
    "x-goog-expires",
    "token",
    "signature",
)
_URL_PATTERN = re.compile(r"https?://[^\s)>\"]+")


def _sanitize_url(raw_url: str) -> str:
    try:
        parts = urlsplit(raw_url)
    except Exception:
        return raw_url
    if not parts.query:
        return raw_url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "<redacted>", parts.fragment))


def _sanitize_log_text(text: str) -> str:
    if not text:
        return text
    result = text
    for key in _SENSITIVE_QUERY_KEYS:
        result = re.sub(
            rf"(?i)({re.escape(key)}=)([^&\s]+)",
            rf"\1<redacted>",
            result,
        )
    for match in _URL_PATTERN.findall(result):
        sanitized = _sanitize_url(match)
        if sanitized != match:
            result = result.replace(match, sanitized)
    return result
