"""Google Cloud Vision client."""
from __future__ import annotations

import asyncio

from google.cloud import vision
from google.oauth2 import service_account

from config import Settings


class GoogleVisionService:
    def __init__(self, settings: Settings, max_results: int = 10) -> None:
        self._max_results = max_results
        credentials_path = (
            settings.GOOGLE_VISION_CREDENTIALS_PATH
            or settings.GOOGLE_CLOUD_CREDENTIALS_PATH
        )
        if credentials_path:
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path
            )
            self._client = vision.ImageAnnotatorClient(credentials=credentials)
        else:
            self._client = vision.ImageAnnotatorClient()

    async def detect_objects(self, image_bytes: bytes) -> dict:
        return await asyncio.to_thread(self._detect_sync, image_bytes)

    def _detect_sync(self, image_bytes: bytes) -> dict:
        image = vision.Image(content=image_bytes)
        response = self._client.object_localization(
            image=image, max_results=self._max_results
        )
        if response.error.message:
            raise RuntimeError(response.error.message)

        annotations = []
        for obj in response.localized_object_annotations:
            annotations.append(
                {
                    "name": obj.name,
                    "score": obj.score,
                    "boundingPoly": {
                        "normalizedVertices": [
                            {"x": v.x, "y": v.y}
                            for v in obj.bounding_poly.normalized_vertices
                        ]
                    },
                }
            )
        return {"localizedObjectAnnotations": annotations}
