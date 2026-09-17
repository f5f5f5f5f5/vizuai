import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from config import Settings
from services.vision import GoogleVisionService


async def run(image_path: Path, out_path: Path) -> None:
    settings = Settings()
    service = GoogleVisionService(settings, max_results=settings.VISION_MAX_RESULTS)
    payload = await service.detect_objects(image_path.read_bytes())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Vision output saved to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect objects via Google Vision.")
    parser.add_argument("--image", required=True, type=Path, help="Render image path.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/vision.json"),
        help="Output JSON path.",
    )
    args = parser.parse_args()
    asyncio.run(run(args.image, args.out))


if __name__ == "__main__":
    main()
