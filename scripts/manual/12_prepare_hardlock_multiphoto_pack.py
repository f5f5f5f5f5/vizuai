import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from config import Settings
from pipeline.simple_pipeline import (
    _assemble_render_prompt,
    _load_text,
    _planner_with_json_retry,
    _prepare_input_image,
)


DEFAULT_INPUTS_DIR = ROOT_DIR / "inputs" / "пробники"
DEFAULT_OUTPUT_DIR = Path("local-data/hardlock_tests/prod_vs_C_multiphoto_20260315")

CASES = [
    {
        "id": "case_01_open_plan_refresh",
        "filename": "2.jpg",
        "request_ru": "Хочу обновить эту кухню-гостиную в теплом современном стиле. Сделай интерьер чище и визуально дороже, но без радикальной ломки логики пространства. Нужны светлая кухня, овальный обеденный стол на 4, компактный диван, ТВ-зона и мягкий многослойный свет.",
    },
    {
        "id": "case_02_living_contemporary_classic",
        "filename": "1221.jpg",
        "request_ru": "Это гостиная. Хочу спокойный contemporary classic без перегруза: обнови стены, потолок и свет, сделай интерьер более благородным и цельным. Сохрани диванную зону и ТВ, ничего лишнего не добавляй.",
    },
    {
        "id": "case_03_whitebox_open_plan",
        "filename": "1291.jpg",
        "request_ru": "Сделай из этого whitebox светлую кухню-гостиную в мягком минимализме. Нужны прямая кухня по дальней стене, круглый стол на 4, компактный диван, ТВ-зона и теплый встроенный свет.",
    },
    {
        "id": "case_04_shallow_wall_stress",
        "filename": "444444.jpg",
        "request_ru": "Хочу soft luxe для кухни-гостиной: светлая кухня с рифлеными верхними фасадами и каменным фартуком, встроенный холодильник, духовка и микроволновка, большой овальный стол на 4, небольшой шоколадный диван, ТВ и ковер перед диваном.",
    },
    {
        "id": "case_05_long_room_lounge",
        "filename": "ццц.jpg",
        "request_ru": "Хочу превратить эту длинную комнату в элегантную современную гостиную. Сохрани архитектурный характер стен, добавь большую зону отдыха с диваном, креслом, журнальным столиком и крупным ковром, сделай свет мягким и дорогим на вид.",
    },
]


def _build_variant_c_template(prod_template: str) -> str:
    text = prod_template
    text = text.replace(
        "Role: You are a professional interior designer. You edit the provided image to satisfy the user request while preserving geometry and camera.",
        "Role: You are a professional interior designer performing a constrained interior image edit. You satisfy the user request while preserving the original room geometry, depth structure, and camera viewpoint.",
    )
    text = text.replace(
        "- Keep large elements freestanding/surface-mounted; do not embed/merge furniture/cabinetry into walls or anchors.",
        "- Keep large elements freestanding/surface-mounted; do not embed/merge furniture/cabinetry into walls or anchors; no in-wall recesses/cavities.",
    )
    needle = "- If anything risks violating this hard-lock or the space is tight: simplify/downscale and omit secondary features; if still risky, omit it."
    replacement = (
        "- If the requested program feels tight, reduce furniture scale and simplify the layout before altering composition or room shape.\n"
        + needle
    )
    text = text.replace(needle, replacement)
    return text


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _json_dump(path: Path, payload: object) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


async def _run(output_dir: Path, inputs_dir: Path) -> None:
    settings = Settings()
    planner_instruction = _load_text(ROOT_DIR / settings.SIMPLE_PLANNER_PROMPT_PATH)
    prod_render_template = _load_text(ROOT_DIR / settings.SIMPLE_RENDER_PROMPT_PATH)
    variant_c_template = _build_variant_c_template(prod_render_template)

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_text(
        output_dir / "README.txt",
        "\n".join(
            [
                "Planner step already executed on the original photo with current prod planner prompt.",
                "Use input_prepared.png for GPT-image manual tests.",
                "Compare prompts from prod/prompt.txt vs variant_C/prompt.txt for each case.",
                f"Planner prompt: {settings.SIMPLE_PLANNER_PROMPT_PATH}",
                f"Render hardlock (prod): {settings.SIMPLE_RENDER_PROMPT_PATH}",
                "Render hardlock (variant_C): prod hardlock + constrained role line + priority ladder + no in-wall recesses/cavities.",
            ]
        ),
    )
    _write_text(output_dir / "planner_instruction.txt", planner_instruction)
    _write_text(output_dir / "render_template_prod.txt", prod_render_template)
    _write_text(output_dir / "render_template_variant_C.txt", variant_c_template)
    _json_dump(output_dir / "cases_manifest.json", CASES)

    planner_temperature = settings.OPENAI_PLANNER_TEMPERATURE if settings.OPENAI_TEXT_SEND_TEMPERATURE else None

    for case in CASES:
        case_dir = output_dir / case["id"]
        case_dir.mkdir(parents=True, exist_ok=True)

        image_path = inputs_dir / case["filename"]
        original_bytes = image_path.read_bytes()
        prepared_png, target_size_label, prep_meta = _prepare_input_image(original_bytes)

        (
            planner_raw,
            planner_result,
            planner_provider,
            planner_usage,
            planner_cost,
            planner_attempts,
            planner_error,
            planner_parse_mode,
            planner_text_fallback_used,
            planner_schema,
        ) = await _planner_with_json_retry(
            settings=settings,
            instruction=planner_instruction,
            user_text=case["request_ru"],
            images=[original_bytes],
            max_output_tokens=settings.OPENAI_PLANNER_MAX_OUTPUT_TOKENS,
            temperature=planner_temperature,
            reasoning_effort=settings.OPENAI_PLANNER_REASONING_EFFORT,
            text_verbosity=settings.OPENAI_TEXT_VERBOSITY,
            store=settings.OPENAI_TEXT_STORE,
            gemini_temperature=0.2,
            logger=None,
            job_id=case["id"],
        )

        if planner_result is None:
            raise RuntimeError(f"Planner failed for {case['id']}: {planner_error or 'unknown error'}")

        prod_prompt = _assemble_render_prompt(prod_render_template, planner_result)
        variant_c_prompt = _assemble_render_prompt(variant_c_template, planner_result)

        ext = image_path.suffix.lower() or ".jpg"
        (case_dir / f"input_original{ext}").write_bytes(original_bytes)
        (case_dir / "input_prepared.png").write_bytes(prepared_png)
        _write_text(case_dir / "user_request_ru.txt", case["request_ru"])
        _write_text(case_dir / "planner_raw.txt", planner_raw)
        _json_dump(case_dir / "planner.json", asdict(planner_result))
        _json_dump(case_dir / "planner_usage.json", planner_usage or {})
        _json_dump(case_dir / "planner_attempts.json", planner_attempts)
        _json_dump(
            case_dir / "planner_meta.json",
            {
                "provider": planner_provider,
                "cost_usd": planner_cost,
                "error": planner_error,
                "parse_mode": planner_parse_mode,
                "text_fallback_used": planner_text_fallback_used,
                "schema": planner_schema,
                "target_size_label": target_size_label,
            },
        )
        _json_dump(case_dir / "input_prepared_meta.json", prep_meta)
        _write_text(case_dir / "render_prompt_prod.txt", prod_prompt)
        _write_text(case_dir / "render_prompt_variant_C.txt", variant_c_prompt)
        _write_text(case_dir / "prod" / "prompt.txt", prod_prompt)
        _write_text(case_dir / "variant_C" / "prompt.txt", variant_c_prompt)
        _write_text(
            case_dir / "README.txt",
            "\n".join(
                [
                    f"Source image: {image_path}",
                    "Planner executed on input_original.*",
                    "Render manually with input_prepared.png",
                    "prod/prompt.txt = current prod hardlock",
                    "variant_C/prompt.txt = constrained role + priority ladder variant",
                ]
            ),
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs-dir", type=Path, default=DEFAULT_INPUTS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    asyncio.run(_run(args.output_dir, args.inputs_dir))


if __name__ == "__main__":
    main()
