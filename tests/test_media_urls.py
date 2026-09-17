from app_services.media_urls import MediaUrlResolver


def test_media_url_resolver_extracts_key_from_signed_cdn_url(monkeypatch, settings):
    captured = {}

    class _FakeStorage:
        def __init__(self, _settings, prefix="uploads/"):
            captured["prefix"] = prefix

        def get_signed_object_url(self, key: str, expires_in: int = 3600) -> str:
            captured["key"] = key
            captured["expires_in"] = expires_in
            return f"https://signed.example/{key}?exp={expires_in}"

    monkeypatch.setattr("app_services.media_urls.S3Storage", _FakeStorage)

    resolver = MediaUrlResolver(settings)
    signed_source = (
        "http://cdn/uploads/account/design/input.jpg"
        "?X-Goog-Algorithm=GOOG4-RSA-SHA256"
        "&X-Goog-Credential=test"
    )

    resolved = resolver.resolve(signed_source)

    assert captured["prefix"] == "uploads/"
    assert captured["key"] == "uploads/account/design/input.jpg"
    assert captured["expires_in"] == 3600
    assert resolved == "https://signed.example/uploads/account/design/input.jpg?exp=3600"


def test_media_url_resolver_extracts_key_from_gs_url(monkeypatch, settings):
    captured = {}

    class _FakeStorage:
        def __init__(self, _settings, prefix="uploads/"):
            pass

        def get_signed_object_url(self, key: str, expires_in: int = 3600) -> str:
            captured["key"] = key
            return f"https://signed.example/{key}"

    monkeypatch.setattr("app_services.media_urls.S3Storage", _FakeStorage)

    resolver = MediaUrlResolver(settings)
    resolved = resolver.resolve(f"gs://{settings.GCS_BUCKET}/uploads/account/original.png")

    assert captured["key"] == "uploads/account/original.png"
    assert resolved == "https://signed.example/uploads/account/original.png"
