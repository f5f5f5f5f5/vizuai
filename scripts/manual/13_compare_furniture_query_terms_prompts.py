"""Compare furniture query-terms prompt variants on local image+vision dumps."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Settings
from pipeline.orchestrator import OrchestratorConfig
from services.furniture_query_terms import (
    FurnitureQueryTermsService,
    QueryTermsBatchResult,
    QueryTermsCropInput,
)
from utils.image_processing import batch_crop
from utils.label_loader import load_label_set
from utils.response_parser import parse_vision


@dataclass
class CaseComparison:
    case_id: str
    image_path: str
    vision_path: str
    detected_objects: list[dict[str, Any]]
    old_results: list[dict[str, Any]]
    new_results: list[dict[str, Any]]
    old_model: str | None
    new_model: str | None
    old_deletes: int
    new_deletes: int


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare furniture query-terms prompts on local examples."
    )
    parser.add_argument(
        "--examples-dir",
        type=Path,
        default=Path("local-data/crops_duplicate/examples"),
        help="Directory with paired *.jpg and *.txt files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("local-data/crops_duplicate"),
        help="Base directory for comparison results.",
    )
    parser.add_argument(
        "--old-prompt",
        type=Path,
        default=Path("prompts/gpt_furniture_query_terms_system_v1.md"),
        help="Old prompt path.",
    )
    parser.add_argument(
        "--new-prompt",
        type=Path,
        default=Path("prompts/gpt_furniture_query_terms_system_v2.md"),
        help="New prompt path.",
    )
    return parser.parse_args()


def _load_settings() -> Settings:
    return Settings(APP_MODE="test")


def _build_orchestrator_config(settings: Settings) -> OrchestratorConfig:
    return OrchestratorConfig(
        exclude_labels_path=Path(settings.EXCLUDE_LABELS_PATH),
        min_score=settings.VISION_MIN_SCORE,
        min_area=settings.VISION_MIN_AREA,
        max_objects=settings.MAX_OBJECTS,
        prefetch_n=settings.VISION_PREFETCH_N,
        iou_threshold=settings.VISION_IOU_THRESHOLD,
        containment_threshold=settings.VISION_CONTAINMENT_THRESHOLD,
        max_per_label=settings.VISION_MAX_PER_LABEL,
    )


def _parse_generic_labels(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _serialize_results(result: QueryTermsBatchResult | None) -> list[dict[str, Any]]:
    if result is None:
        return []
    rows: list[dict[str, Any]] = []
    for crop_id, item in sorted(result.results_by_crop.items(), key=lambda pair: pair[0]):
        rows.append(
            {
                "crop_id": crop_id,
                "display_name_ru": item.display_name_ru,
                "query_terms": list(item.query_terms),
            }
        )
    return rows


def _count_deletes(rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if row.get("display_name_ru") == "__DELETE__")


def _save_crop(path: Path, image_bytes: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image_bytes)


def _save_original_copy(target: Path, source: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())


async def _run_prompt(
    settings: Settings,
    prompt_path: Path,
    crops: list[QueryTermsCropInput],
) -> QueryTermsBatchResult | None:
    prompt_settings = settings.model_copy(
        update={"FURNITURE_QUERY_TERMS_PROMPT_PATH": str(prompt_path)}
    )
    service = FurnitureQueryTermsService(prompt_settings)
    return await service.infer(crops=crops)


def _make_crop_inputs(image_bytes: bytes, objects: list[Any], settings: Settings) -> list[QueryTermsCropInput]:
    cropped = batch_crop(
        image_bytes,
        objects,
        image_format=settings.CROP_IMAGE_FORMAT,
        mask_shrink_ratio=settings.CROP_MASK_SHRINK_RATIO,
        mask_transparent=settings.CROP_MASK_TRANSPARENT,
    )
    inputs: list[QueryTermsCropInput] = []
    for index, item in enumerate(cropped, start=1):
        obj = item["object"]
        inputs.append(
            QueryTermsCropInput(
                crop_id=str(index),
                vision_label=str(obj.label or ""),
                image_bytes=item["bytes"],
            )
        )
    return inputs


def _detected_objects_summary(objects: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, obj in enumerate(objects, start=1):
        rows.append(
            {
                "crop_id": str(index),
                "vision_label": obj.label,
                "score": round(float(obj.score), 4),
                "area": round(float(obj.area), 4),
            }
        )
    return rows


def _render_markdown(cases: list[CaseComparison]) -> str:
    lines: list[str] = ["# Furniture Query Terms Prompt Comparison", ""]
    for case in cases:
        lines.append(f"## {case.case_id}")
        lines.append(f"- Image: `{case.image_path}`")
        lines.append(f"- Vision: `{case.vision_path}`")
        lines.append(f"- Objects after prod parse: `{len(case.detected_objects)}`")
        lines.append(f"- Old prompt deletes: `{case.old_deletes}`")
        lines.append(f"- New prompt deletes: `{case.new_deletes}`")
        lines.append("")
        lines.append("### Detected Objects")
        for obj in case.detected_objects:
            lines.append(
                f"- `{obj['crop_id']}` `{obj['vision_label']}` score={obj['score']} area={obj['area']}"
            )
        lines.append("")
        lines.append("### Old Prompt")
        for row in case.old_results:
            lines.append(
                f"- `{row['crop_id']}` → `{row['display_name_ru']}` | {', '.join(row['query_terms']) or '[]'}"
            )
        lines.append("")
        lines.append("### New Prompt")
        for row in case.new_results:
            lines.append(
                f"- `{row['crop_id']}` → `{row['display_name_ru']}` | {', '.join(row['query_terms']) or '[]'}"
            )
        lines.append("")
    return "\n".join(lines).strip() + "\n"


async def main() -> None:
    args = _parse_args()
    settings = _load_settings()
    config = _build_orchestrator_config(settings)
    exclude_labels = load_label_set(config.exclude_labels_path)
    generic_labels = _parse_generic_labels(settings.VISION_GENERIC_LABELS)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir / f"prompt_compare_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    cases: list[CaseComparison] = []

    image_paths = sorted(args.examples_dir.glob("*.jpg"))
    for image_path in image_paths:
        case_id = image_path.stem
        vision_path = args.examples_dir / f"{case_id}.txt"
        if not vision_path.exists():
            continue

        image_bytes = image_path.read_bytes()
        vision_payload = _load_json(vision_path)
        objects = parse_vision(
            vision_payload,
            exclude_labels=exclude_labels,
            min_score=config.min_score,
            min_area=config.min_area,
            max_objects=config.max_objects,
            prefetch_n=config.prefetch_n,
            iou_threshold=config.iou_threshold,
            containment_threshold=config.containment_threshold,
            max_per_label=config.max_per_label,
            generic_labels=generic_labels,
            generic_iou_threshold=settings.VISION_GENERIC_IOU_THRESHOLD,
            generic_containment_threshold=settings.VISION_GENERIC_CONTAINMENT_THRESHOLD,
            global_iou_threshold=settings.VISION_DUPLICATE_IOU_THRESHOLD,
            global_containment_threshold=settings.VISION_DUPLICATE_CONTAINMENT_THRESHOLD,
        )

        crop_inputs = _make_crop_inputs(image_bytes, objects, settings)
        old_result = await _run_prompt(settings, args.old_prompt, crop_inputs)
        new_result = await _run_prompt(settings, args.new_prompt, crop_inputs)

        case_dir = output_dir / case_id
        _save_original_copy(case_dir / image_path.name, image_path)
        (case_dir / vision_path.name).write_text(
            json.dumps(vision_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        crops_dir = case_dir / "crops"
        for crop in crop_inputs:
            _save_crop(crops_dir / f"{crop.crop_id}_{crop.vision_label}.jpg", crop.image_bytes)

        old_rows = _serialize_results(old_result)
        new_rows = _serialize_results(new_result)
        (case_dir / "detected_objects.json").write_text(
            json.dumps(_detected_objects_summary(objects), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (case_dir / "old_prompt_result.json").write_text(
            json.dumps(
                {
                    "model": old_result.model if old_result else None,
                    "usage": old_result.usage if old_result else None,
                    "raw": old_result.raw if old_result else None,
                    "normalized": old_rows,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (case_dir / "new_prompt_result.json").write_text(
            json.dumps(
                {
                    "model": new_result.model if new_result else None,
                    "usage": new_result.usage if new_result else None,
                    "raw": new_result.raw if new_result else None,
                    "normalized": new_rows,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        cases.append(
            CaseComparison(
                case_id=case_id,
                image_path=str(image_path),
                vision_path=str(vision_path),
                detected_objects=_detected_objects_summary(objects),
                old_results=old_rows,
                new_results=new_rows,
                old_model=old_result.model if old_result else None,
                new_model=new_result.model if new_result else None,
                old_deletes=_count_deletes(old_rows),
                new_deletes=_count_deletes(new_rows),
            )
        )

    summary = {
        "generated_at": timestamp,
        "examples_dir": str(args.examples_dir),
        "old_prompt": str(args.old_prompt),
        "new_prompt": str(args.new_prompt),
        "cases": [asdict(case) for case in cases],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "summary.md").write_text(_render_markdown(cases), encoding="utf-8")
    print(output_dir)


if __name__ == "__main__":
    asyncio.run(main())
