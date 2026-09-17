import asyncio
from types import SimpleNamespace

from app_services.design.result_service import DesignResultService


def test_design_result_service_download_payload_uses_storage_key_from_signed_url(monkeypatch, settings):
    design = SimpleNamespace(
        id="47fd089b-eba0-4f4b-bbe9-19296653b1c8",
        mode="full",
        final_image_url=(
            "http://cdn/final/20260328/223505-1774737305346-559584ca.png"
            "?X-Goog-Algorithm=GOOG4-RSA-SHA256"
        ),
        render_image_url=None,
        fix_image_url=None,
    )

    class _FakeStorage:
        def __init__(self, _settings, prefix="uploads/"):
            self.prefix = prefix

        def get_signed_object_url(self, key: str, expires_in: int = 3600) -> str:
            return f"https://signed.example/{key}?exp={expires_in}"

        def get_object_metadata(self, key: str):
            assert key == "final/20260328/223505-1774737305346-559584ca.png"
            return {"content_type": "image/png"}

        def download_bytes(self, key: str):
            assert key == "final/20260328/223505-1774737305346-559584ca.png"
            return b"png-bytes"

    class _FakeRepo:
        def __init__(self, _session):
            pass

        def get_account_design(self, _account_id, _design_id):
            return design

    class _FakeSessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app_services.design.result_service.S3Storage", _FakeStorage)
    monkeypatch.setattr("app_services.media_urls.S3Storage", _FakeStorage)
    monkeypatch.setattr("app_services.design.result_service.DesignRepository", _FakeRepo)
    monkeypatch.setattr("app_services.design.result_service.get_db_session", lambda: _FakeSessionContext())

    service = DesignResultService(settings)
    payload = asyncio.run(
        service.get_download_payload(
            "2f088530-c7ba-4699-b928-719fa91cee89",
            "47fd089b-eba0-4f4b-bbe9-19296653b1c8",
        )
    )

    assert payload == {
        "content": b"png-bytes",
        "content_type": "image/png",
        "filename": "vizuai-result-47fd089b.png",
    }
