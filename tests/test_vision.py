import pytest

from services.vision import GoogleVisionService


class _FakeVertex:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


class _FakeBoundingPoly:
    def __init__(self) -> None:
        self.normalized_vertices = [
            _FakeVertex(0.1, 0.1),
            _FakeVertex(0.6, 0.1),
            _FakeVertex(0.6, 0.6),
            _FakeVertex(0.1, 0.6),
        ]


class _FakeObject:
    def __init__(self) -> None:
        self.name = "Chair"
        self.score = 0.95
        self.bounding_poly = _FakeBoundingPoly()


class _FakeResponse:
    def __init__(self) -> None:
        self.localized_object_annotations = [_FakeObject()]
        self.error = type("Error", (), {"message": ""})


class _FakeClient:
    def object_localization(self, image, max_results):
        return _FakeResponse()


@pytest.mark.asyncio
async def test_vision_detect_objects(monkeypatch, settings):
    monkeypatch.setattr(
        "services.vision.service_account.Credentials.from_service_account_file",
        lambda path: object(),
    )
    monkeypatch.setattr(
        "services.vision.vision.ImageAnnotatorClient",
        lambda credentials: _FakeClient(),
    )

    service = GoogleVisionService(settings, max_results=5)
    result = await service.detect_objects(b"image")
    assert "localizedObjectAnnotations" in result
    assert result["localizedObjectAnnotations"][0]["name"] == "Chair"
