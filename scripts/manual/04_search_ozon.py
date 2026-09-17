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
from utils.image_processing import batch_crop
from utils.label_loader import load_label_set
from utils.response_parser import parse_searchapi, parse_vision


def _parse_label_list(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


async def run(
    image_path: Path,
    vision_path: Path,
    exclude_labels_path: Path,
    out_path: Path,
    min_score: float,
    min_area: float,
    max_objects: int,
    prefetch_n: int,
    iou_threshold: float,
    containment_threshold: float,
    max_per_label: int,
    generic_labels: set[str],
    generic_iou_threshold: float,
    generic_containment_threshold: float,
) -> None:
    settings = Settings()
    vision_payload = json.loads(vision_path.read_text(encoding="utf-8"))
    exclude_labels = load_label_set(exclude_labels_path)
    objects = parse_vision(
        vision_payload,
        exclude_labels=exclude_labels,
        min_score=min_score,
        min_area=min_area,
        max_objects=max_objects,
        prefetch_n=prefetch_n,
        iou_threshold=iou_threshold,
        containment_threshold=containment_threshold,
        max_per_label=max_per_label,
        generic_labels=generic_labels,
        generic_iou_threshold=generic_iou_threshold,
        generic_containment_threshold=generic_containment_threshold,
    )

    storage = S3Storage(settings, prefix="crops/")
    search = SearchApiService(settings)
    image_bytes = image_path.read_bytes()
    crops = batch_crop(image_bytes, objects)

    marketplaces = [
        ("ozon", "ozon.ru"),
        ("yandex_market", "market.yandex.ru"),
        ("wildberries", "wildberries.ru"),
    ]
    results = []
    for item in crops:
        obj = item["object"]
        if settings.S3_PRESIGN_INPUTS:
            crop_url = storage.upload_bytes_presigned(
                item["bytes"], ".jpg", None, settings.S3_PRESIGN_EXPIRES
            )
        else:
            crop_url = storage.upload_bytes(item["bytes"], ".jpg")
        entry = {"label": obj.label, "crop_url": crop_url, "links": {}}
        for marketplace, query in marketplaces:
            payload = await search.search(crop_url, query)
            matches = parse_searchapi(payload, obj.label, marketplace=marketplace, limit=3)
            entry["links"][marketplace] = [item.url for item in matches]
        results.append(entry)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Search results saved to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Search products on Ozon via SearchAPI.")
    parser.add_argument("--image", required=True, type=Path, help="Render image path.")
    parser.add_argument("--vision", required=True, type=Path, help="Vision JSON path.")
    parser.add_argument(
        "--exclude-labels",
        type=Path,
        default=Path("data/exclude_labels.json"),
        help="Exclude labels file path.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/products.json"),
        help="Output JSON file path.",
    )
    parser.add_argument("--min-score", type=float, default=0.5)
    parser.add_argument("--min-area", type=float, default=0.01)
    parser.add_argument("--max-objects", type=int, default=10)
    parser.add_argument("--prefetch-n", type=int, default=30)
    parser.add_argument("--iou-threshold", type=float, default=0.85)
    parser.add_argument("--containment-threshold", type=float, default=0.9)
    parser.add_argument("--max-per-label", type=int, default=2)
    parser.add_argument(
        "--generic-labels",
        type=str,
        default=None,
        help="Comma-separated generic labels for overlap suppression.",
    )
    parser.add_argument("--generic-iou-threshold", type=float, default=0.85)
    parser.add_argument("--generic-containment-threshold", type=float, default=0.9)
    args = parser.parse_args()
    settings = Settings()
    generic_labels = _parse_label_list(
        args.generic_labels if args.generic_labels is not None else settings.VISION_GENERIC_LABELS
    )
    asyncio.run(
        run(
            args.image,
            args.vision,
            args.exclude_labels,
            args.out,
            args.min_score,
            args.min_area,
            args.max_objects,
            args.prefetch_n,
            args.iou_threshold,
            args.containment_threshold,
            args.max_per_label,
            generic_labels,
            args.generic_iou_threshold,
            args.generic_containment_threshold,
        )
    )


if __name__ == "__main__":
    main()
