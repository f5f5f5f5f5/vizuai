from services.storage import S3Storage


def test_storage_upload_bytes(monkeypatch, settings):
    called = {}

    class _FakeBlob:
        def __init__(self, key: str):
            self.key = key

        def upload_from_string(self, data, content_type=None):
            called["key"] = self.key
            called["content_type"] = content_type

    class _FakeBucket:
        def blob(self, key: str):
            return _FakeBlob(key)

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def bucket(self, name):
            called["bucket"] = name
            return _FakeBucket()

    class _FakeCredentials:
        pass

    monkeypatch.setattr("services.storage.storage.Client", _FakeClient)
    monkeypatch.setattr(
        "services.storage.service_account.Credentials.from_service_account_file",
        lambda _path: _FakeCredentials(),
    )

    storage = S3Storage(settings, prefix="crops/")
    url = storage.upload_bytes(b"data", ".jpg")

    assert called["bucket"] == settings.GCS_BUCKET
    assert called["key"].startswith("crops/")
    assert called["content_type"] == "image/jpeg"
    assert url.startswith("http://cdn/")


def test_storage_upload_bytes_retries_transient_failure(monkeypatch, settings):
    called = {"attempts": 0}

    class _FakeBlob:
        def __init__(self, key: str):
            self.key = key

        def upload_from_string(self, data, content_type=None, timeout=None):
            called["attempts"] += 1
            if called["attempts"] < 3:
                raise TimeoutError("temporary upload timeout")
            called["key"] = self.key
            called["content_type"] = content_type
            called["timeout"] = timeout

    class _FakeBucket:
        def blob(self, key: str):
            return _FakeBlob(key)

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def bucket(self, name):
            return _FakeBucket()

    class _FakeCredentials:
        pass

    monkeypatch.setattr("services.storage.storage.Client", _FakeClient)
    monkeypatch.setattr(
        "services.storage.service_account.Credentials.from_service_account_file",
        lambda _path: _FakeCredentials(),
    )
    monkeypatch.setattr("services.storage.time.sleep", lambda _seconds: None)

    storage = S3Storage(settings, prefix="crops/")
    url = storage.upload_bytes(b"data", ".jpg")

    assert called["attempts"] == 3
    assert called["key"].startswith("crops/")
    assert called["content_type"] == "image/jpeg"
    assert called["timeout"] == 240
    assert url.startswith("http://cdn/")


def test_storage_extracts_key_from_private_cloud_url(monkeypatch, settings):
    class _FakeBucket:
        def blob(self, _key: str):
            raise AssertionError("blob() should not be called")

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def bucket(self, _name):
            return _FakeBucket()

    class _FakeCredentials:
        pass

    monkeypatch.setattr("services.storage.storage.Client", _FakeClient)
    monkeypatch.setattr(
        "services.storage.service_account.Credentials.from_service_account_file",
        lambda _path: _FakeCredentials(),
    )

    storage = S3Storage(settings, prefix="crops/")
    key = storage.extract_storage_key(
        "https://storage.cloud.google.com/bucket/style_refs/20260404/example.jpg"
        "?X-Goog-Algorithm=ignored"
    )

    assert key == "style_refs/20260404/example.jpg"
