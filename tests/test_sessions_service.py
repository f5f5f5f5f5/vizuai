from __future__ import annotations

from types import SimpleNamespace

import pytest

from app_services.sessions.service import SessionsService


class _FakeResponse:
    def __init__(self, status: int = 200, body: str = "") -> None:
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self) -> str:
        return self._body


class _FakeClientSession:
    def __init__(self, *, timeout=None, calls: list[dict] | None = None) -> None:
        self.timeout = timeout
        self.calls = calls if calls is not None else []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def post(self, url: str, *, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResponse(status=200, body='{"id":"email_123"}')


def _build_settings(**overrides):
    base = {
        "WEB_APP_URL": "https://app.vizuai.example",
        "AUTH_MAGIC_LINK_TTL_MINUTES": 20,
        "RESEND_API_KEY": None,
        "RESEND_FROM_EMAIL": None,
        "POSTMARK_SERVER_TOKEN": None,
        "POSTMARK_FROM_EMAIL": None,
        "POSTMARK_MESSAGE_STREAM": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_magic_link_uses_resend_when_configured(monkeypatch):
    calls: list[dict] = []

    def _session_factory(*, timeout=None):
        return _FakeClientSession(timeout=timeout, calls=calls)

    monkeypatch.setattr("app_services.sessions.service.aiohttp.ClientSession", _session_factory)
    service = SessionsService(
        _build_settings(
            RESEND_API_KEY="re_test_123",
            RESEND_FROM_EMAIL="hello@vizuai.example",
        )
    )

    await service._send_magic_link_email("user@example.com", "https://app.vizuai.example/login?token=abc&lang=ru", "ru")

    assert len(calls) == 1
    assert calls[0]["url"] == "https://api.resend.com/emails"
    assert calls[0]["headers"]["Authorization"] == "Bearer re_test_123"
    assert calls[0]["json"]["from"] == "VizuAI <hello@vizuai.example>"
    assert calls[0]["json"]["reply_to"] == "owner@vizuai.example"
    assert calls[0]["json"]["to"] == ["user@example.com"]


def test_magic_link_url_preserves_locale():
    service = SessionsService(_build_settings())

    assert service._build_magic_link_url("abc", "ru") == "https://app.vizuai.example/login?token=abc&lang=ru"
    assert service._build_magic_link_url("abc", "en") == "https://app.vizuai.example/login?token=abc&lang=en"


@pytest.mark.asyncio
async def test_magic_link_delivery_raises_when_provider_is_partially_configured():
    service = SessionsService(
        _build_settings(
            RESEND_API_KEY="re_test_123",
            RESEND_FROM_EMAIL=None,
        )
    )

    with pytest.raises(RuntimeError, match="magic_link_delivery_misconfigured"):
        await service._send_magic_link_email("user@example.com", "https://app.vizuai.example/login?token=abc&lang=ru", "ru")
