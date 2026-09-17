"""SearchAPI (Google Lens) client."""
from __future__ import annotations

import asyncio
import time
from typing import Optional
from urllib.parse import urlparse

import aiohttp

from config import Settings


class SearchApiService:
    def __init__(
        self, settings: Settings, session: Optional[aiohttp.ClientSession] = None
    ) -> None:
        self._settings = settings
        self._session = session
        self._cb_lock = asyncio.Lock()
        self._cb_failure_counts: dict[str, int] = {}
        self._cb_open_until_ts: dict[str, float] = {}

    async def search(
        self,
        image_url: str,
        query: str = "ozon.ru",
        *,
        marketplace: str | None = None,
        search_type: str | None = None,
        hl: str | None = None,
        country: str | None = None,
        device: str | None = None,
    ) -> dict:
        params = {
            "api_key": self._settings.SEARCHAPI_KEY,
            "engine": self._settings.SEARCHAPI_ENGINE,
            "search_type": search_type or self._settings.SEARCHAPI_SEARCH_TYPE,
            "url": image_url,
            "q": query,
        }
        if hl is None:
            hl = self._settings.SEARCHAPI_HL
        if country is None:
            country = self._settings.SEARCHAPI_COUNTRY
        if device is None:
            device = self._settings.SEARCHAPI_DEVICE
        if hl:
            params["hl"] = hl
        if country:
            params["country"] = country
        if device:
            params["device"] = device
        total = max(float(self._settings.SEARCHAPI_TIMEOUT_SECONDS or 30), 1.0)
        connect = max(float(self._settings.SEARCHAPI_TIMEOUT_CONNECT_SECONDS or 8), 0.5)
        read = max(float(self._settings.SEARCHAPI_TIMEOUT_READ_SECONDS or 25), 0.5)
        timeout = aiohttp.ClientTimeout(
            total=total,
            connect=min(connect, total),
            sock_read=min(read, total),
        )
        market_key = _resolve_market_key(marketplace=marketplace, query=query)
        await self._assert_circuit_available(market_key)

        try:
            if self._session:
                payload = await self._get(self._session, params, timeout)
            else:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    payload = await self._get(session, params, timeout)
        except Exception as exc:
            await self._register_failure(market_key, exc)
            raise
        await self._register_success(market_key)
        return payload

    async def _assert_circuit_available(self, market_key: str) -> None:
        if not self._settings.SEARCHAPI_CIRCUIT_BREAKER_ENABLED:
            return
        now = time.monotonic()
        async with self._cb_lock:
            open_until = self._cb_open_until_ts.get(market_key)
        if open_until and open_until > now:
            remaining = open_until - now
            raise RuntimeError(f"searchapi_circuit_open:{market_key}:{remaining:.1f}s")

    async def _register_success(self, market_key: str) -> None:
        if not self._settings.SEARCHAPI_CIRCUIT_BREAKER_ENABLED:
            return
        async with self._cb_lock:
            self._cb_failure_counts.pop(market_key, None)
            self._cb_open_until_ts.pop(market_key, None)

    async def _register_failure(self, market_key: str, exc: Exception) -> None:
        if not self._settings.SEARCHAPI_CIRCUIT_BREAKER_ENABLED:
            return
        if not isinstance(exc, (asyncio.TimeoutError, aiohttp.ClientError)):
            return
        threshold = max(int(self._settings.SEARCHAPI_CIRCUIT_BREAKER_FAILURE_THRESHOLD or 1), 1)
        open_seconds = max(int(self._settings.SEARCHAPI_CIRCUIT_BREAKER_OPEN_SECONDS or 1), 1)
        now = time.monotonic()
        async with self._cb_lock:
            count = self._cb_failure_counts.get(market_key, 0) + 1
            self._cb_failure_counts[market_key] = count
            if count < threshold:
                return
            self._cb_open_until_ts[market_key] = now + float(open_seconds)
            self._cb_failure_counts[market_key] = 0

    async def _get(
        self,
        session: aiohttp.ClientSession,
        params: dict[str, str],
        timeout: aiohttp.ClientTimeout,
    ) -> dict:
        async with session.get(
            self._settings.SEARCHAPI_BASE_URL, params=params, timeout=timeout
        ) as response:
            response.raise_for_status()
            return await response.json()


def _resolve_market_key(*, marketplace: str | None, query: str) -> str:
    value = str(marketplace or "").strip().lower()
    if value:
        return value
    domain = str(query or "").strip().split(" ", 1)[0].lower()
    if not domain:
        return "unknown"
    if domain.startswith("http://") or domain.startswith("https://"):
        parsed = urlparse(domain)
        host = (parsed.netloc or "").strip().lower()
        return host or "unknown"
    return domain
