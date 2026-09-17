"""Quick test script for Google Cloud Vision object localization."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from google.cloud import vision
from google.oauth2 import service_account

from config import Settings


def build_client(creds_path: Path) -> vision.ImageAnnotatorClient:
    """Create a Vision client from a local service account JSON."""
    credentials = service_account.Credentials.from_service_account_file(str(creds_path))
    return vision.ImageAnnotatorClient(credentials=credentials)


def detect_objects(
    client: vision.ImageAnnotatorClient, image_path: Path, max_results: int = 5
) -> Sequence[vision.LocalizedObjectAnnotation]:
    """Run object localization on a local image."""
    content = image_path.read_bytes()
    image = vision.Image(content=content)
    response = client.object_localization(image=image, max_results=max_results)
    if response.error.message:
        raise RuntimeError(response.error.message)
    return response.localized_object_annotations


def format_vertices(vertices) -> str:
    return ", ".join(f"({v.x:.3f}, {v.y:.3f})" for v in vertices)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test Google Cloud Vision object localization on a local image."
    )
    settings = Settings()
    parser.add_argument(
        "--image",
        type=Path,
        default=Path("test-room.jpg"),
        help="Path to the test image (default: test-room.jpg).",
    )
    parser.add_argument(
        "--creds",
        type=Path,
        default=Path(settings.GOOGLE_CLOUD_CREDENTIALS_PATH),
        help=(
            "Path to the service account JSON "
            "(default: GOOGLE_CLOUD_CREDENTIALS_PATH / GOOGLE_APPLICATION_CREDENTIALS)."
        ),
    )
    parser.add_argument(
        "--max",
        type=int,
        default=5,
        dest="max_results",
        help="Max objects to return (default: 5).",
    )
    args = parser.parse_args()

    if not args.creds.exists():
        raise SystemExit(f"Credentials file not found: {args.creds}")
    if not args.image.exists():
        raise SystemExit(f"Image file not found: {args.image}")

    client = build_client(args.creds)
    results = detect_objects(client, args.image, args.max_results)

    if not results:
        print("No objects detected.")
        return

    print(f"Detected {len(results)} object(s):")
    for idx, obj in enumerate(results, start=1):
        box = format_vertices(obj.bounding_poly.normalized_vertices)
        print(f"{idx}. {obj.name} (score={obj.score:.2%}) box={box}")


if __name__ == "__main__":
    main()
