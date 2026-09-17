import pytest

from services.searchapi import SearchApiService


@pytest.mark.asyncio
async def test_searchapi_builds_params(monkeypatch, settings):
    service = SearchApiService(settings=settings, session=object())
    captured = {}

    async def fake_get(session, params, timeout):
        captured.update(params)
        return {"ok": True}

    monkeypatch.setattr(service, "_get", fake_get)
    result = await service.search("http://image/url.jpg", "ozon.ru")
    assert result["ok"] is True
    assert captured["url"] == "http://image/url.jpg"
    assert captured["q"] == "ozon.ru"
    assert captured["api_key"] == settings.SEARCHAPI_KEY
    assert captured["engine"] == settings.SEARCHAPI_ENGINE
    assert captured["search_type"] == settings.SEARCHAPI_SEARCH_TYPE
    assert captured["hl"] == settings.SEARCHAPI_HL
    assert captured["country"] == settings.SEARCHAPI_COUNTRY
    assert captured["device"] == settings.SEARCHAPI_DEVICE
