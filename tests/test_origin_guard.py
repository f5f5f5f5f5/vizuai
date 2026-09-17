from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import Settings
from web_api.middleware.origin_guard import OriginGuardMiddleware


def _build_client() -> TestClient:
    app = FastAPI()
    app.add_middleware(
        OriginGuardMiddleware,
        settings=Settings(
            _env_file=None,
            APP_MODE="web",
            DATABASE_URL="sqlite://",
            GCS_BUCKET="test-bucket",
            CDN_URL_TEMPLATE="https://cdn.example.com/{key}",
            VERTEX_PROJECT_ID="test-project",
            WEB_APP_URL="https://app.vizuai.example",
            WEB_PUBLIC_URL="https://vizuai.example",
            WEB_ALLOWED_ORIGINS="https://app.vizuai.example,http://localhost:3000",
        ),
    )

    @app.post("/api/v1/secure")
    async def secure_endpoint():
        return {"ok": True}

    return TestClient(app)


def test_origin_guard_allows_known_origin() -> None:
    client = _build_client()
    response = client.post("/api/v1/secure", headers={"Origin": "https://app.vizuai.example"})
    assert response.status_code == 200


def test_origin_guard_blocks_unknown_origin() -> None:
    client = _build_client()
    response = client.post("/api/v1/secure", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"


def test_origin_guard_blocks_cookie_request_without_origin_metadata() -> None:
    client = _build_client()
    response = client.post(
        "/api/v1/secure",
        headers={"Cookie": "vizuai_session=token"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"
