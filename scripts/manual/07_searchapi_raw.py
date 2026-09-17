import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from config import Settings
from services.searchapi import SearchApiService
from services.storage import S3Storage


async def run(image_path: Path, query: str, out_path: Path) -> None:
    settings = Settings()
    storage = S3Storage(settings)
    search = SearchApiService(settings)

    image_bytes = image_path.read_bytes()
    suffix = image_path.suffix if image_path.suffix else ".jpg"

    if settings.S3_PRESIGN_INPUTS:
        image_url = storage.upload_bytes_presigned(
            image_bytes, suffix, prefix="inputs", expires_in=settings.S3_PRESIGN_EXPIRES
        )
    else:
        image_url = storage.upload_bytes(image_bytes, suffix, prefix="inputs")

    payload = await search.search(image_url, query)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Image URL: {image_url}")
    print(f"SearchAPI response saved to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run raw SearchAPI (Google Lens) call.")
    parser.add_argument("--image", required=True, type=Path, help="Image path.")
    parser.add_argument(
        "--text",
        type=Path,
        help="Path to text file used as query (optional).",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Query string (overrides --text).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/searchapi_raw.json"),
        help="Output JSON path.",
    )
    args = parser.parse_args()

    if args.query is not None:
        query = args.query.strip()
    elif args.text is not None:
        query = args.text.read_text(encoding="utf-8").strip()
    else:
        query = "ozon.ru"

    asyncio.run(run(args.image, query, args.out))


if __name__ == "__main__":
    main()
