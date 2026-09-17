import argparse
import asyncio
import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CASES_ROOT = Path("local-data/gpt5.4")


def _timestamp_dir() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _normalize_line(text: str) -> str:
    return " ".join(text.strip().split())


def _extract_json_block(text: str) -> dict | None:
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = text[start : end + 1]
    try:
        payload = json.loads(snippet)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        return None


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return float(raw)


@dataclass
class RuntimeSettings:
    openai_api_key: str
    openai_text_timeout: int
    openai_text_verbosity: str
    openai_text_store: bool
    openai_text_send_temperature: bool
    planner_max_output_tokens: int
    planner_temperature: float
    planner_reasoning_effort: str
    ranker_max_output_tokens: int
    ranker_temperature: float
    ranker_reasoning_effort: str
    planner_prompt_path: Path
    ranker_prompt_path: Path


def _load_runtime_settings() -> RuntimeSettings:
    _load_env_file(ROOT_DIR / ".env")
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set in environment or .env")
    return RuntimeSettings(
        openai_api_key=api_key,
        openai_text_timeout=_env_int("OPENAI_TEXT_TIMEOUT", 120),
        openai_text_verbosity=os.getenv("OPENAI_TEXT_VERBOSITY", "low").strip() or "low",
        openai_text_store=_env_bool("OPENAI_TEXT_STORE", False),
        openai_text_send_temperature=_env_bool("OPENAI_TEXT_SEND_TEMPERATURE", False),
        planner_max_output_tokens=_env_int("OPENAI_PLANNER_MAX_OUTPUT_TOKENS", 5000),
        planner_temperature=_env_float("OPENAI_PLANNER_TEMPERATURE", 0.2),
        planner_reasoning_effort=os.getenv("OPENAI_PLANNER_REASONING_EFFORT", "high").strip() or "high",
        ranker_max_output_tokens=_env_int("OPENAI_RANKER_MAX_OUTPUT_TOKENS", 5000),
        ranker_temperature=_env_float("OPENAI_RANKER_TEMPERATURE", 0.0),
        ranker_reasoning_effort=os.getenv("OPENAI_RANKER_REASONING_EFFORT", "high").strip() or "high",
        planner_prompt_path=ROOT_DIR / (os.getenv("SIMPLE_PLANNER_PROMPT_PATH", "prompts/gpt_methods_planner_instruction_simple_pipeline_v1.md")),
        ranker_prompt_path=ROOT_DIR / (os.getenv("SIMPLE_RANKER_PROMPT_PATH", "prompts/gpt_ranker_ab_prompt_v2.md")),
    )


def _openai_image_part(image_bytes: bytes) -> dict[str, str]:
    mime = "image/png" if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return {"type": "input_image", "image_url": f"data:{mime};base64,{b64}"}


def _extract_openai_text(payload: dict[str, Any]) -> str:
    for item in payload.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                return text
    return str(payload.get("output_text") or "").strip()


def _extract_openai_usage(payload: dict[str, Any]) -> dict[str, Any]:
    usage = payload.get("usage") or {}
    return {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


def _compute_cost(model: str, usage: dict[str, Any]) -> float | None:
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if input_tokens is None or output_tokens is None:
        return None
    pricing = {
        "gpt-5.2": (1.75, 14.0),
        "gpt-5.4": (2.50, 15.0),
    }
    input_price, output_price = pricing.get(model, (None, None))
    if input_price is None or output_price is None:
        return None
    return (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price


async def _openai_text_with_usage(
    api_key: str,
    model: str,
    system_text: str,
    user_text: str,
    images: list[bytes],
    max_output_tokens: int,
    timeout_seconds: int,
    temperature: float | None,
    reasoning_effort: str | None,
    text_verbosity: str | None,
    store: bool | None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    user_content: list[dict[str, Any]] = [{"type": "input_text", "text": user_text}]
    for image in images:
        user_content.append(_openai_image_part(image))
    payload: dict[str, Any] = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_text}]},
            {"role": "user", "content": user_content},
        ],
        "max_output_tokens": max_output_tokens,
    }
    if temperature is not None and not model.startswith("gpt-5"):
        payload["temperature"] = temperature
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}
    if text_verbosity:
        payload["text"] = {"verbosity": text_verbosity}
    if store is not None:
        payload["store"] = store
    body = json.dumps(payload).encode("utf-8")

    def _post() -> dict[str, Any]:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI error {exc.code}: {error_text}") from exc

    data = await asyncio.to_thread(_post)
    return _extract_openai_text(data), _extract_openai_usage(data), payload


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _planner_case_dirs(cases_root: Path) -> list[Path]:
    root = cases_root / "planner_cases"
    return sorted([path for path in root.iterdir() if path.is_dir()])


def _ranker_case_dirs(cases_root: Path) -> list[Path]:
    root = cases_root / "ranker_cases"
    return sorted([path for path in root.iterdir() if path.is_dir()])


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _planner_case_payload(case_dir: Path) -> tuple[str, list[bytes], dict[str, Any]]:
    user_request = _load_text(case_dir / "user_request_ru.txt")
    images = [_read_bytes(case_dir / "input_prepared.png")]
    meta = {
        "case_type": "planner",
        "case_name": case_dir.name,
        "user_request_ru": user_request,
        "image_path": str(case_dir / "input_prepared.png"),
    }
    return user_request, images, meta


def _ranker_case_payload(case_dir: Path) -> tuple[str, list[bytes], dict[str, Any]]:
    user_text = _load_text(case_dir / "ranker_user_text.txt")
    images = [
        _read_bytes(case_dir / "input_prepared.png"),
        _read_bytes(case_dir / "candidate_A.png"),
        _read_bytes(case_dir / "candidate_B.png"),
    ]
    meta = {
        "case_type": "ranker",
        "case_name": case_dir.name,
        "ranker_user_text": user_text,
        "expected_best": _load_text(case_dir / "expected_best.txt") if (case_dir / "expected_best.txt").exists() else "",
        "candidate_labels": _load_text(case_dir / "candidate_labels.txt") if (case_dir / "candidate_labels.txt").exists() else "",
    }
    return user_text, images, meta


async def _run_one(
    *,
    step: str,
    case_dir: Path,
    model: str,
    output_dir: Path,
    settings: RuntimeSettings,
) -> dict[str, Any]:
    if step == "planner":
        prompt_path = settings.planner_prompt_path
        user_text, images, meta = _planner_case_payload(case_dir)
        max_output_tokens = settings.planner_max_output_tokens
        temperature = settings.planner_temperature if settings.openai_text_send_temperature else None
        reasoning_effort = settings.planner_reasoning_effort
    else:
        prompt_path = settings.ranker_prompt_path
        user_text, images, meta = _ranker_case_payload(case_dir)
        max_output_tokens = settings.ranker_max_output_tokens
        temperature = settings.ranker_temperature if settings.openai_text_send_temperature else None
        reasoning_effort = settings.ranker_reasoning_effort
    instruction = _load_text(prompt_path)
    started = asyncio.get_running_loop().time()
    output_dir.mkdir(parents=True, exist_ok=True)
    error: str | None = None
    try:
        raw_text, usage, request_payload = await _openai_text_with_usage(
            api_key=settings.openai_api_key,
            model=model,
            system_text=instruction,
            user_text=user_text,
            images=images,
            max_output_tokens=max_output_tokens,
            timeout_seconds=settings.openai_text_timeout,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            text_verbosity=settings.openai_text_verbosity,
            store=settings.openai_text_store,
        )
    except Exception as exc:
        raw_text = ""
        usage = {}
        request_payload = {
            "model": model,
            "max_output_tokens": max_output_tokens,
            "temperature": temperature,
            "reasoning_effort": reasoning_effort,
            "text_verbosity": settings.openai_text_verbosity,
            "store": settings.openai_text_store,
        }
        error = f"{type(exc).__name__}: {exc}"
    elapsed = round(asyncio.get_running_loop().time() - started, 3)
    parsed = _extract_json_block(raw_text) if raw_text else None
    usage["estimated_cost_usd"] = _compute_cost(model, usage)
    (output_dir / "raw.txt").write_text(raw_text, encoding="utf-8")
    (output_dir / "parsed.json").write_text(json.dumps(parsed or {}, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "usage.json").write_text(
        json.dumps({"model": model, "elapsed_s": elapsed, "error": error, **usage}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "request_payload.json").write_text(json.dumps(request_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "case_meta.json").write_text(
        json.dumps(
            {
                **meta,
                "step": step,
                "prompt_path": str(prompt_path),
                "instruction_sha1_like": str(abs(hash(instruction)))[:16],
                "error": error,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "step": step,
        "case": case_dir.name,
        "model": model,
        "elapsed_s": elapsed,
        "parsed_ok": parsed is not None,
        "error": error,
        "usage": usage,
        "output_dir": str(output_dir),
    }


def _build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"results": results, "aggregate": {}}
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in results:
        buckets.setdefault((item["step"], item["model"]), []).append(item)
    for (step, model), items in sorted(buckets.items()):
        parsed_ok = sum(1 for item in items if item["parsed_ok"])
        total_cost = sum(item["usage"].get("estimated_cost_usd") or 0.0 for item in items)
        total_elapsed = sum(item["elapsed_s"] for item in items)
        summary["aggregate"][f"{step}:{model}"] = {
            "cases": len(items),
            "parsed_ok": parsed_ok,
            "parsed_fail": len(items) - parsed_ok,
            "errors": sum(1 for item in items if item.get("error")),
            "total_cost_usd": round(total_cost, 6),
            "avg_cost_usd": round(total_cost / len(items), 6) if items else 0.0,
            "avg_elapsed_s": round(total_elapsed / len(items), 3) if items else 0.0,
        }
    return summary


async def _run(args: argparse.Namespace) -> None:
    settings = _load_runtime_settings()
    cases_root = args.cases_root.resolve()
    output_root = (args.output_root or (cases_root / "runs" / _timestamp_dir())).resolve()
    models = [item.strip() for item in args.models.split(",") if item.strip()]
    steps = [item.strip() for item in args.steps.split(",") if item.strip()]
    planner_cases = _planner_case_dirs(cases_root) if "planner" in steps else []
    ranker_cases = _ranker_case_dirs(cases_root) if "ranker" in steps else []
    if args.case_filter:
        planner_cases = [case for case in planner_cases if args.case_filter in case.name]
        ranker_cases = [case for case in ranker_cases if args.case_filter in case.name]
    if args.limit is not None:
        planner_cases = planner_cases[: args.limit]
        ranker_cases = ranker_cases[: args.limit]
    results: list[dict[str, Any]] = []
    for model in models:
        for case_dir in planner_cases:
            result = await _run_one(
                step="planner",
                case_dir=case_dir,
                model=model,
                output_dir=output_root / "planner" / model / case_dir.name,
                settings=settings,
            )
            results.append(result)
        for case_dir in ranker_cases:
            result = await _run_one(
                step="ranker",
                case_dir=case_dir,
                model=model,
                output_dir=output_root / "ranker" / model / case_dir.name,
                settings=settings,
            )
            results.append(result)
    summary = _build_summary(results)
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"output_root": str(output_root), **summary["aggregate"]}, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark GPT-5.2 vs GPT-5.4 on planner/ranker cases.")
    parser.add_argument("--cases-root", type=Path, default=DEFAULT_CASES_ROOT)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--models", default="gpt-5.2,gpt-5.4")
    parser.add_argument("--steps", default="planner,ranker")
    parser.add_argument("--case-filter", default="")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
