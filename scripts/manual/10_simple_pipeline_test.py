import argparse
import asyncio
import base64
import json
import os
import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import aiohttp
from PIL import Image

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from config import Settings

SUPPORTED_SIZES = [(1024, 1024), (1024, 1536), (1536, 1024)]


def _timestamp_dir() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _normalize_line(text: str) -> str:
    return " ".join(text.strip().split())


def _to_png_bytes(image_input: bytes | Image.Image) -> bytes:
    if isinstance(image_input, Image.Image):
        image = image_input.convert("RGB")
    else:
        image = Image.open(BytesIO(image_input)).convert("RGB")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _decode_image(bytes_in: bytes) -> Image.Image:
    return Image.open(BytesIO(bytes_in)).convert("RGB")


def _choose_target_size(size: tuple[int, int], mode: str) -> tuple[int, int]:
    width, height = size
    aspect = width / height
    best = None
    best_score = None
    for tw, th in SUPPORTED_SIZES:
        target_aspect = tw / th
        if mode == "pad":
            scale = min(tw / width, th / height)
            new_w = int(width * scale)
            new_h = int(height * scale)
            pad_area = (tw * th) - (new_w * new_h)
            score = pad_area
        elif mode == "crop":
            scale = max(tw / width, th / height)
            new_w = int(width * scale)
            new_h = int(height * scale)
            crop_area = (new_w * new_h) - (tw * th)
            score = crop_area
        else:
            score = abs(aspect - target_aspect)
        if best_score is None or score < best_score:
            best_score = score
            best = (tw, th)
    return best or SUPPORTED_SIZES[0]


def _fit_image(
    image: Image.Image,
    target: tuple[int, int],
    mode: str,
    pad_style: str,
) -> Image.Image:
    from PIL import ImageFilter

    target_w, target_h = target
    if mode == "stretch":
        return image.resize((target_w, target_h), resample=Image.LANCZOS)

    if mode == "pad":
        scale = min(target_w / image.width, target_h / image.height)
        new_w = max(1, int(image.width * scale))
        new_h = max(1, int(image.height * scale))
        resized = image.resize((new_w, new_h), resample=Image.LANCZOS)
        if pad_style == "blur":
            background = image.resize((target_w, target_h), resample=Image.LANCZOS)
            background = background.filter(ImageFilter.GaussianBlur(radius=12))
        else:
            background = Image.new("RGB", (target_w, target_h), color=(16, 16, 16))
        offset = ((target_w - new_w) // 2, (target_h - new_h) // 2)
        background.paste(resized, offset)
        return background

    # crop
    scale = max(target_w / image.width, target_h / image.height)
    new_w = max(1, int(image.width * scale))
    new_h = max(1, int(image.height * scale))
    resized = image.resize((new_w, new_h), resample=Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def _guess_mime_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return "image/jpeg"


def _extract_json_block(text: str) -> dict | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = text[start : end + 1]
    try:
        return json.loads(snippet)
    except json.JSONDecodeError:
        return None


def _extract_openai_text(payload: dict) -> str:
    for item in payload.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                return text
    return payload.get("output_text", "").strip()


def _extract_openai_usage(payload: dict) -> dict:
    usage = payload.get("usage") or {}
    return {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


def _compute_gpt52_cost(usage: dict) -> float | None:
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if input_tokens is None or output_tokens is None:
        return None
    return (input_tokens / 1_000_000) * 1.75 + (output_tokens / 1_000_000) * 14.0


def _openai_image_part(image_bytes: bytes) -> dict:
    mime = "image/png" if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return {"type": "input_image", "image_url": f"data:{mime};base64,{b64}"}


async def _openai_text(
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
) -> str:
    url = "https://api.openai.com/v1/responses"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    user_content: list[dict] = [{"type": "input_text", "text": user_text}]
    for image in images:
        user_content.append(_openai_image_part(image))
    payload: dict = {
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
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status >= 400:
                error_text = await response.text()
                raise RuntimeError(f"OpenAI error {response.status}: {error_text}")
            data = await response.json()
    return _extract_openai_text(data)


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
) -> tuple[str, dict]:
    async def _post(payload: dict) -> dict:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    raise RuntimeError(f"OpenAI error {response.status}: {error_text}")
                return await response.json()
    url = "https://api.openai.com/v1/responses"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    user_content: list[dict] = [{"type": "input_text", "text": user_text}]
    for image in images:
        user_content.append(_openai_image_part(image))
    payload: dict = {
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
    try:
        data = await _post(payload)
    except RuntimeError as exc:
        message = str(exc)
        if "Unsupported parameter" in message and "temperature" in message:
            payload.pop("temperature", None)
            data = await _post(payload)
        else:
            raise
    return _extract_openai_text(data), _extract_openai_usage(data)


async def _render_openai(
    api_key: str,
    model: str,
    image_bytes: bytes,
    aux_image_bytes: bytes | None,
    prompt: str,
    size: str,
    timeout_seconds: int,
    quality: str | None,
    moderation: str | None,
    background: str | None,
    partial_images: int | None,
) -> bytes:
    url = "https://api.openai.com/v1/images/edits"
    headers = {"Authorization": f"Bearer {api_key}"}
    form = aiohttp.FormData()
    form.add_field("model", model)
    form.add_field("prompt", prompt)
    if aux_image_bytes:
        form.add_field("image[]", image_bytes, filename="input.png", content_type="image/png")
        form.add_field("image[]", aux_image_bytes, filename="input_aux.png", content_type="image/png")
    else:
        form.add_field("image", image_bytes, filename="input.png", content_type="image/png")
    if quality:
        form.add_field("quality", quality)
    if moderation:
        form.add_field("moderation", moderation)
    if background:
        form.add_field("background", background)
    if partial_images is not None:
        form.add_field("partial_images", str(partial_images))
    form.add_field("n", "1")
    form.add_field("size", size)
    form.add_field("output_format", "png")
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, headers=headers, data=form) as response:
            if response.status >= 400:
                error_text = await response.text()
                raise RuntimeError(f"OpenAI error {response.status}: {error_text}")
            payload = await response.json()
    data = payload.get("data", [])
    if not data:
        raise ValueError("OpenAI response has no image data.")
    b64_data = data[0].get("b64_json")
    if not b64_data:
        raise ValueError("OpenAI response missing b64_json.")
    return base64.b64decode(b64_data)


def _extract_vertex_text(response: object) -> str:
    candidates = getattr(response, "candidates", None)
    if not candidates:
        return ""
    content = getattr(candidates[0], "content", None)
    parts = getattr(content, "parts", None) if content else None
    if not parts:
        return ""
    texts = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            texts.append(text)
    return "\n".join(texts).strip()


async def _gemini_text(
    project_id: str,
    location: str,
    credentials_path: str | None,
    model: str,
    instruction: str,
    user_text: str,
    images: list[bytes],
    timeout_seconds: int,
    max_side: int,
    max_output_tokens: int,
) -> str:
    if credentials_path and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
    from google import genai
    from google.genai import types

    def _resize(bytes_in: bytes) -> bytes:
        image = Image.open(BytesIO(bytes_in)).convert("RGB")
        if max(image.size) <= max_side:
            return bytes_in
        ratio = max_side / max(image.size)
        new_size = (int(image.width * ratio), int(image.height * ratio))
        image = image.resize(new_size, resample=Image.LANCZOS)
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=95)
        return buffer.getvalue()

    client = genai.Client(vertexai=True, project=project_id, location=location)
    contents: list[object] = [instruction]
    if user_text.strip():
        contents.append(_normalize_line(user_text))
    for image in images:
        resized = _resize(image)
        contents.append(
            types.Part.from_bytes(data=resized, mime_type=_guess_mime_type(resized))
        )
    response = await asyncio.wait_for(
        asyncio.to_thread(
            client.models.generate_content,
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=max_output_tokens,
                response_mime_type="text/plain",
            ),
        ),
        timeout=timeout_seconds,
    )
    return _normalize_line(_extract_vertex_text(response))


def _extract_vertex_image(response: object) -> bytes:
    parts = getattr(response, "parts", None)
    if not parts:
        candidates = getattr(response, "candidates", None)
        if candidates:
            content = getattr(candidates[0], "content", None)
            parts = getattr(content, "parts", None)
    if not parts:
        raise ValueError("Vertex response has no parts.")
    for part in parts:
        inline = getattr(part, "inline_data", None)
        if inline is not None:
            try:
                image = part.as_image()
                buffer = BytesIO()
                image.save(buffer, format="PNG")
                return buffer.getvalue()
            except Exception:
                data = getattr(inline, "data", None)
                if data:
                    return data
    raise ValueError("Vertex response has no inline image data.")


async def _render_vertex(
    project_id: str,
    location: str,
    credentials_path: str | None,
    model: str,
    image_bytes: bytes,
    aux_image_bytes: bytes | None,
    prompt: str,
    timeout_seconds: int,
) -> bytes:
    if credentials_path and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
    from google import genai
    from google.genai import types

    client = genai.Client(vertexai=True, project=project_id, location=location)
    image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
    contents: list[object] = [prompt, image_part]
    if aux_image_bytes:
        contents.append(types.Part.from_bytes(data=aux_image_bytes, mime_type="image/png"))
    response = await asyncio.wait_for(
        asyncio.to_thread(
            client.models.generate_content,
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        ),
        timeout=timeout_seconds,
    )
    return _extract_vertex_image(response)


async def _llm_text(
    provider: str,
    settings: Settings,
    instruction: str,
    user_text: str,
    images: list[bytes],
    openai_model: str | None,
    openai_max_tokens: int | None,
    openai_timeout: int | None,
    openai_temperature: float | None,
    openai_reasoning_effort: str | None,
    openai_text_verbosity: str | None,
    openai_store: bool | None,
    usage_out: dict | None,
    gemini_timeout: int | None,
    gemini_max_side: int,
) -> str:
    if provider == "gpt":
        openai_key = settings.OPENAI_API_KEY
        if not openai_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        text, usage = await _openai_text_with_usage(
            api_key=openai_key,
            model=openai_model or "gpt-5.2",
            system_text=instruction,
            user_text=user_text,
            images=images,
            max_output_tokens=openai_max_tokens or settings.GEMINI_MAX_OUTPUT_TOKENS,
            timeout_seconds=openai_timeout or settings.OPENAI_IMAGE_TIMEOUT,
            temperature=openai_temperature,
            reasoning_effort=openai_reasoning_effort,
            text_verbosity=openai_text_verbosity,
            store=openai_store,
        )
        if usage_out is not None:
            usage_out.update(usage)
            usage_out["estimated_cost_usd"] = _compute_gpt52_cost(usage)
        return _normalize_line(text)
    if provider == "gemini":
        return await _gemini_text(
            project_id=settings.VERTEX_PROJECT_ID,
            location=settings.VERTEX_LOCATION,
            credentials_path=settings.GOOGLE_CLOUD_CREDENTIALS_PATH,
            model=settings.GEMINI_MODEL,
            instruction=instruction,
            user_text=user_text,
            images=images,
            timeout_seconds=gemini_timeout or settings.GEMINI_TIMEOUT_SECONDS,
            max_side=gemini_max_side,
            max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
        )
    raise RuntimeError(f"Unknown llm provider: {provider}")


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _fill_template(template: str, replacements: dict[str, str]) -> str:
    result = template
    for key, value in replacements.items():
        result = result.replace(key, value)
    return result.strip()


def _parse_planner_payload(raw_text: str) -> dict:
    data = _extract_json_block(raw_text) or {}
    methods = data.get("methods", [])
    if not isinstance(methods, list):
        methods = []
    methods = [item for item in methods if isinstance(item, str)]
    data["methods"] = methods
    return data


def _parse_validator_payload(raw_text: str) -> dict:
    data = _extract_json_block(raw_text) or {}
    def _as_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            if value.strip().lower() == "true":
                return True
            if value.strip().lower() == "false":
                return False
        return False

    scores = data.get("scores") if isinstance(data.get("scores"), dict) else {}
    def _as_score(value: object) -> int:
        if isinstance(value, (int, float)):
            return int(max(0, min(100, value)))
        return 0

    parsed = {
        "request_ok": _as_bool(data.get("request_ok")),
        "geometry_ok": _as_bool(data.get("geometry_ok")),
        "function_ok": _as_bool(data.get("function_ok")),
        "scores": {
            "request": _as_score(scores.get("request")),
            "geometry": _as_score(scores.get("geometry")),
            "function": _as_score(scores.get("function")),
        },
        "notes": data.get("notes", ""),
        "raw": data,
    }
    return parsed


def _overall_score(scores: dict) -> int:
    return scores["geometry"] * 10000 + scores["request"] * 100 + scores["function"]


async def run(
    image_path: Path,
    text_path: Path,
    out_dir: Path,
    planner_instruction_path: Path,
    render_template_path: Path,
    fix_template_path: Path,
    validator_prompt_path: Path,
    planner_llm: str,
    validator_llm: str,
    render_provider: str,
    fix_provider: str,
    openai_text_model: str | None,
    openai_text_max_tokens: int | None,
    openai_text_timeout: int | None,
    openai_image_model: str | None,
    openai_image_size: str | None,
    openai_image_timeout: int | None,
    nanobanana_model: str | None,
    nanobanana_timeout: int | None,
    nanobanana_api: str | None,
    gemini_timeout: int | None,
    gemini_max_side: int,
    fit_mode: str,
    pad_style: str,
) -> Path:
    settings = Settings()
    out_dir.mkdir(parents=True, exist_ok=True)

    user_request = text_path.read_text(encoding="utf-8").strip()
    original_bytes = image_path.read_bytes()
    original_image = _decode_image(original_bytes)

    target = _choose_target_size(original_image.size, fit_mode)
    prepared_image = _fit_image(original_image, target, fit_mode, pad_style)
    prepared_png = _to_png_bytes(prepared_image)

    (out_dir / "input_original.jpg").write_bytes(original_bytes)
    (out_dir / "input_request.txt").write_text(user_request, encoding="utf-8")
    (out_dir / "input_prepared.png").write_bytes(prepared_png)
    (out_dir / "input_prepared_meta.json").write_text(
        json.dumps(
            {
                "original_size": list(original_image.size),
                "target_size": list(target),
                "fit_mode": fit_mode,
                "pad_style": pad_style,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    planner_instruction = _load_text(planner_instruction_path)
    (out_dir / "planner_instruction.txt").write_text(planner_instruction, encoding="utf-8")
    (out_dir / "planner_request.txt").write_text(
        f"User request:\n{user_request}\n\n(One image attached)", encoding="utf-8"
    )
    planner_temperature = 0.2 if planner_llm == "gpt" and settings.OPENAI_TEXT_SEND_TEMPERATURE else None
    planner_raw = await _llm_text(
        provider=planner_llm,
        settings=settings,
        instruction=planner_instruction,
        user_text=user_request,
        images=[original_bytes],
        openai_model=openai_text_model,
        openai_max_tokens=openai_text_max_tokens or 900,
        openai_timeout=openai_text_timeout,
        openai_temperature=planner_temperature,
        openai_reasoning_effort="high" if planner_llm == "gpt" else None,
        openai_text_verbosity="low" if planner_llm == "gpt" else None,
        openai_store=False if planner_llm == "gpt" else None,
        usage_out=(planner_usage := {}) if planner_llm == "gpt" else None,
        gemini_timeout=gemini_timeout,
        gemini_max_side=gemini_max_side,
    )
    (out_dir / "planner_raw.txt").write_text(planner_raw, encoding="utf-8")
    planner_payload = _parse_planner_payload(planner_raw)
    (out_dir / "planner.json").write_text(
        json.dumps(planner_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if planner_llm == "gpt":
        (out_dir / "planner_usage.json").write_text(
            json.dumps(planner_usage, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    must_not_change = planner_payload.get("must_not_change", [])
    if isinstance(must_not_change, list):
        must_not_change_text = "; ".join([item for item in must_not_change if item])
    else:
        must_not_change_text = ""
    if not must_not_change_text:
        must_not_change_text = "all existing windows, doors, openings/doorways, radiators"

    render_template = _load_text(render_template_path)
    render_prompt = _fill_template(
        render_template,
        {
            "<TARGET_STYLE>": planner_payload.get("target_style", "modern"),
            "<must_not_change>": must_not_change_text,
            "<planner_compiled_prompt>": planner_payload.get("planner_compiled_prompt", ""),
        },
    )
    (out_dir / "render_prompt.txt").write_text(render_prompt, encoding="utf-8")

    openai_key = settings.OPENAI_API_KEY
    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    render_image: bytes
    size_str = f"{target[0]}x{target[1]}"
    if render_provider == "gpt":
        render_image = await _render_openai(
            api_key=openai_key,
            model=openai_image_model or settings.OPENAI_IMAGE_MODEL,
            image_bytes=prepared_png,
            aux_image_bytes=None,
            prompt=render_prompt,
            size=size_str,
            timeout_seconds=openai_image_timeout or settings.OPENAI_IMAGE_TIMEOUT,
            quality="high",
            moderation="auto",
            background="auto",
            partial_images=0,
        )
    else:
        api_mode = (nanobanana_api or settings.NANOBANANA_API).lower()
        if api_mode != "vertex":
            raise RuntimeError(f"Unsupported NANOBANANA_API mode: {api_mode}")
        render_image = await _render_vertex(
            project_id=settings.VERTEX_PROJECT_ID,
            location=settings.NANOBANANA_LOCATION,
            credentials_path=settings.NANO_BANANA_CREDENTIALS_PATH,
            model=nanobanana_model or settings.NANOBANANA_MODEL,
            image_bytes=prepared_png,
            aux_image_bytes=None,
            prompt=render_prompt,
            timeout_seconds=nanobanana_timeout or settings.NANOBANANA_TIMEOUT,
        )
    (out_dir / "render.png").write_bytes(render_image)

    validator_prompt = _load_text(validator_prompt_path)
    (out_dir / "validator_prompt.txt").write_text(validator_prompt, encoding="utf-8")
    validator_request = (
        "User request:\n"
        f"{user_request}\n\n"
        "Edited image is first, original image is second."
    )
    (out_dir / "validator_request.txt").write_text(validator_request, encoding="utf-8")
    validator_temperature = 0.0 if validator_llm == "gpt" and settings.OPENAI_TEXT_SEND_TEMPERATURE else None
    validator_raw = await _llm_text(
        provider=validator_llm,
        settings=settings,
        instruction=validator_prompt,
        user_text=validator_request,
        images=[render_image, prepared_png],
        openai_model=openai_text_model,
        openai_max_tokens=openai_text_max_tokens or 700,
        openai_timeout=openai_text_timeout,
        openai_temperature=validator_temperature,
        openai_reasoning_effort="high" if validator_llm == "gpt" else None,
        openai_text_verbosity="low" if validator_llm == "gpt" else None,
        openai_store=False if validator_llm == "gpt" else None,
        usage_out=(validator_usage := {}) if validator_llm == "gpt" else None,
        gemini_timeout=gemini_timeout,
        gemini_max_side=gemini_max_side,
    )
    (out_dir / "validator_raw.txt").write_text(validator_raw, encoding="utf-8")
    validation = _parse_validator_payload(validator_raw)
    (out_dir / "validator.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if validator_llm == "gpt":
        (out_dir / "validator_usage.json").write_text(
            json.dumps(validator_usage, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    render_result = {
        "image_path": "render.png",
        "validation": validation,
        "overall_score": _overall_score(validation["scores"]),
    }

    best = render_result
    fix_result = None

    if not (validation["request_ok"] and validation["geometry_ok"] and validation["function_ok"]):
        fix_template = _load_text(fix_template_path)
        fix_prompt = fix_template.strip() + "\n\nUser request: " + user_request
        (out_dir / "fix_prompt.txt").write_text(fix_prompt, encoding="utf-8")

        if fix_provider == "gpt":
            fix_image = await _render_openai(
                api_key=openai_key,
                model=openai_image_model or settings.OPENAI_IMAGE_MODEL,
                image_bytes=render_image,
                aux_image_bytes=prepared_png,
                prompt=fix_prompt,
                size=size_str,
                timeout_seconds=openai_image_timeout or settings.OPENAI_IMAGE_TIMEOUT,
                quality="high",
                moderation="auto",
                background="auto",
                partial_images=0,
            )
        else:
            api_mode = (nanobanana_api or settings.NANOBANANA_API).lower()
            if api_mode != "vertex":
                raise RuntimeError(f"Unsupported NANOBANANA_API mode: {api_mode}")
            fix_image = await _render_vertex(
                project_id=settings.VERTEX_PROJECT_ID,
                location=settings.NANOBANANA_LOCATION,
                credentials_path=settings.NANO_BANANA_CREDENTIALS_PATH,
                model=nanobanana_model or settings.NANOBANANA_MODEL,
                image_bytes=render_image,
                aux_image_bytes=prepared_png,
                prompt=fix_prompt,
                timeout_seconds=nanobanana_timeout or settings.NANOBANANA_TIMEOUT,
            )
        (out_dir / "fix.png").write_bytes(fix_image)

        fix_validator_raw = await _llm_text(
            provider=validator_llm,
            settings=settings,
            instruction=validator_prompt,
            user_text=validator_request,
            images=[fix_image, prepared_png],
            openai_model=openai_text_model,
            openai_max_tokens=openai_text_max_tokens or 700,
            openai_timeout=openai_text_timeout,
            openai_temperature=validator_temperature,
            openai_reasoning_effort="high" if validator_llm == "gpt" else None,
            openai_text_verbosity="low" if validator_llm == "gpt" else None,
            openai_store=False if validator_llm == "gpt" else None,
            usage_out=(fix_validator_usage := {}) if validator_llm == "gpt" else None,
            gemini_timeout=gemini_timeout,
            gemini_max_side=gemini_max_side,
        )
        (out_dir / "fix_validator_raw.txt").write_text(
            fix_validator_raw, encoding="utf-8"
        )
        fix_validation = _parse_validator_payload(fix_validator_raw)
        (out_dir / "fix_validator.json").write_text(
            json.dumps(fix_validation, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if validator_llm == "gpt":
            (out_dir / "fix_validator_usage.json").write_text(
                json.dumps(fix_validator_usage, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        fix_result = {
            "image_path": "fix.png",
            "validation": fix_validation,
            "overall_score": _overall_score(fix_validation["scores"]),
        }

        render_ok = validation["request_ok"] and validation["geometry_ok"] and validation["function_ok"]
        fix_ok = fix_validation["request_ok"] and fix_validation["geometry_ok"] and fix_validation["function_ok"]
        if fix_ok and not render_ok:
            best = fix_result
        elif render_ok and not fix_ok:
            best = render_result
        elif fix_ok and render_ok:
            best = fix_result if fix_result["overall_score"] >= render_result["overall_score"] else render_result
        else:
            best = fix_result if fix_result["overall_score"] >= render_result["overall_score"] else render_result

    (out_dir / "best.json").write_text(
        json.dumps(
            {
                "best": best,
                "render": render_result,
                "fix": fix_result,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    best_image_path = out_dir / "best.png"
    (best_image_path).write_bytes(
        (out_dir / best["image_path"]).read_bytes()
    )
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple pipeline test runner.")
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--text", required=True, type=Path)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument(
        "--planner-instruction",
        type=Path,
        default=Path("prompts/gpt_methods_planner_instruction_simple_pipeline_v1.md"),
    )
    parser.add_argument(
        "--render-template",
        type=Path,
        default=Path("prompts/gpt_image15_hardlock_and_role_v1.md"),
    )
    parser.add_argument(
        "--fix-template",
        type=Path,
        default=Path("prompts/gpt_image15_fix_pass_wrapper_v1.md"),
    )
    parser.add_argument(
        "--validator-prompt",
        type=Path,
        default=Path("prompts/gpt_render_validation_prompt_v1.md"),
    )
    parser.add_argument("--planner-llm", choices=("gpt", "gemini"), default="gpt")
    parser.add_argument("--validator-llm", choices=("gpt", "gemini"), default="gpt")
    parser.add_argument("--render-provider", choices=("gpt", "nanobanana"), default="gpt")
    parser.add_argument("--fix-provider", choices=("gpt", "nanobanana"), default="gpt")
    parser.add_argument("--openai-text-model", default="gpt-5.2")
    parser.add_argument("--openai-text-max-tokens", type=int, default=None)
    parser.add_argument("--openai-text-timeout", type=int, default=None)
    parser.add_argument("--openai-image-model", default=None)
    parser.add_argument("--openai-image-size", default=None)
    parser.add_argument("--openai-image-timeout", type=int, default=None)
    parser.add_argument("--nanobanana-model", default=None)
    parser.add_argument("--nanobanana-timeout", type=int, default=None)
    parser.add_argument("--nanobanana-api", default=None)
    parser.add_argument("--gemini-timeout", type=int, default=None)
    parser.add_argument("--gemini-max-side", type=int, default=1600)
    parser.add_argument("--fit-mode", choices=("pad", "crop", "stretch"), default="pad")
    parser.add_argument("--pad-style", choices=("blur", "solid"), default="blur")

    args = parser.parse_args()
    out_dir = args.out_dir or Path("outputs/simple_pipeline") / _timestamp_dir()
    asyncio.run(
        run(
            image_path=args.image,
            text_path=args.text,
            out_dir=out_dir,
            planner_instruction_path=args.planner_instruction,
            render_template_path=args.render_template,
            fix_template_path=args.fix_template,
            validator_prompt_path=args.validator_prompt,
            planner_llm=args.planner_llm,
            validator_llm=args.validator_llm,
            render_provider=args.render_provider,
            fix_provider=args.fix_provider,
            openai_text_model=args.openai_text_model,
            openai_text_max_tokens=args.openai_text_max_tokens,
            openai_text_timeout=args.openai_text_timeout,
            openai_image_model=args.openai_image_model,
            openai_image_size=args.openai_image_size,
            openai_image_timeout=args.openai_image_timeout,
            nanobanana_model=args.nanobanana_model,
            nanobanana_timeout=args.nanobanana_timeout,
            nanobanana_api=args.nanobanana_api,
            gemini_timeout=args.gemini_timeout,
            gemini_max_side=args.gemini_max_side,
            fit_mode=args.fit_mode,
            pad_style=args.pad_style,
        )
    )
    print(f"Saved outputs to {out_dir}")


if __name__ == "__main__":
    main()
