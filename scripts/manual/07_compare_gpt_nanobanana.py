import argparse
import asyncio
import base64
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
from google import genai
from google.genai import types


def _to_png_bytes(image_bytes: bytes) -> bytes:
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def _render_openai(
    api_key: str,
    model: str,
    image_bytes: bytes,
    aux_image_bytes: bytes | None,
    mask_bytes: bytes | None,
    prompt: str,
    size: str,
    timeout_seconds: int,
) -> bytes:
    url = "https://api.openai.com/v1/images/edits"
    headers = {"Authorization": f"Bearer {api_key}"}
    form = aiohttp.FormData()
    form.add_field("model", model)
    form.add_field("prompt", prompt)
    if aux_image_bytes:
        form.add_field(
            "image[]",
            image_bytes,
            filename="input.png",
            content_type="image/png",
        )
        form.add_field(
            "image[]",
            aux_image_bytes,
            filename="input_aux.png",
            content_type="image/png",
        )
    else:
        form.add_field(
            "image",
            image_bytes,
            filename="input.png",
            content_type="image/png",
        )
    if mask_bytes:
        form.add_field("mask", mask_bytes, filename="mask.png", content_type="image/png")
    form.add_field("n", "1")
    form.add_field("size", size)
    # GPT image models always return base64-encoded images; response_format is
    # not supported for them in the Images API.
    form.add_field("output_format", "png")
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, headers=headers, data=form) as response:
            if response.status >= 400:
                error_text = await response.text()
                raise RuntimeError(
                    f"OpenAI error {response.status}: {error_text}"
                )
            payload = await response.json()
    data = payload.get("data", [])
    if not data:
        raise ValueError("OpenAI response has no image data.")
    b64_data = data[0].get("b64_json")
    if not b64_data:
        raise ValueError("OpenAI response missing b64_json.")
    return base64.b64decode(b64_data)


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


async def _fail(message: str) -> bytes:
    raise RuntimeError(message)


async def _render_vertex(
    project_id: str,
    location: str,
    credentials_path: str | None,
    model: str,
    image_bytes: bytes,
    aux_image_bytes: bytes | None,
    mask_bytes: bytes | None,
    use_mask_hack: bool,
    prompt: str,
    timeout_seconds: int,
) -> bytes:
    if credentials_path and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
    client = genai.Client(vertexai=True, project=project_id, location=location)
    image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
    contents: list[object] = []
    if aux_image_bytes:
        contents.append(
            "A depth/edges reference image is provided for guidance. "
            "Use it to guide structure and preserve camera/FOV."
        )
    if use_mask_hack and mask_bytes:
        contents.append(
            "A binary protection mask is provided as a separate image: white pixels must remain unchanged; "
            "only modify black pixels. Do not change camera/FOV or room geometry."
        )
    contents.append(prompt)
    contents.append(image_part)
    if aux_image_bytes:
        contents.append(types.Part.from_bytes(data=aux_image_bytes, mime_type="image/png"))
    if use_mask_hack and mask_bytes:
        contents.append(types.Part.from_bytes(data=mask_bytes, mime_type="image/png"))
    response = await asyncio.wait_for(
        asyncio.to_thread(
            client.models.generate_content,
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        ),
        timeout=timeout_seconds,
    )
    return _extract_vertex_image(response)


async def _render_gemini_api(
    api_key: str,
    model: str,
    image_bytes: bytes,
    aux_image_bytes: bytes | None,
    mask_bytes: bytes | None,
    use_mask_hack: bool,
    prompt: str,
    timeout_seconds: int,
) -> bytes:
    client = genai.Client(api_key=api_key)
    image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
    contents: list[object] = []
    if aux_image_bytes:
        contents.append(
            "A depth/edges reference image is provided for guidance. "
            "Use it to guide structure and preserve camera/FOV."
        )
    if use_mask_hack and mask_bytes:
        contents.append(
            "A binary protection mask is provided as a separate image: white pixels must remain unchanged; "
            "only modify black pixels. Do not change camera/FOV or room geometry."
        )
    contents.append(prompt)
    contents.append(image_part)
    if aux_image_bytes:
        contents.append(types.Part.from_bytes(data=aux_image_bytes, mime_type="image/png"))
    if use_mask_hack and mask_bytes:
        contents.append(types.Part.from_bytes(data=mask_bytes, mime_type="image/png"))
    response = await asyncio.wait_for(
        asyncio.to_thread(
            client.models.generate_content,
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        ),
        timeout=timeout_seconds,
    )
    return _extract_vertex_image(response)


def _load_mask(
    mask_path: Path,
    target_size: tuple[int, int],
    mask_kind: str,
) -> tuple[bytes, bytes, bytes]:
    original_bytes = mask_path.read_bytes()
    original_image = Image.open(BytesIO(original_bytes)).convert("L")
    mask_image = original_image
    if original_image.size != target_size:
        mask_image = original_image.resize(target_size, resample=Image.NEAREST)

    # Threshold to binary (0 or 255)
    mask_binary = mask_image.point(lambda p: 255 if p > 128 else 0, mode="L")
    if mask_kind == "edit":
        mask_binary = Image.eval(mask_binary, lambda p: 255 - p)

    # OpenAI expects alpha mask: 255=protected, 0=editable
    openai_mask = Image.new("RGBA", target_size, (0, 0, 0, 0))
    openai_mask.putalpha(mask_binary)
    openai_buffer = BytesIO()
    openai_mask.save(openai_buffer, format="PNG")

    protect_buffer = BytesIO()
    mask_binary.save(protect_buffer, format="PNG")

    return original_bytes, protect_buffer.getvalue(), openai_buffer.getvalue()


def _load_aux_image(aux_path: Path, target_size: tuple[int, int]) -> bytes:
    aux_image = Image.open(BytesIO(aux_path.read_bytes())).convert("RGB")
    if aux_image.size != target_size:
        aux_image = aux_image.resize(target_size, resample=Image.NEAREST)
    buffer = BytesIO()
    aux_image.save(buffer, format="PNG")
    return buffer.getvalue()


async def run(
    image_path: Path,
    text_path: Path,
    out_root: Path,
    openai_model: str,
    openai_size: str,
    openai_timeout: int,
    vertex_model: str,
    vertex_timeout: int,
    nanobanana_api: str,
    gpt_only: bool,
    mask_path: Path | None,
    mask_kind: str,
    nanobanana_mask_mode: str,
    aux_image_path: Path | None,
) -> Path:
    settings = Settings(_env_file=ROOT_DIR / ".env")
    prompt = text_path.read_text(encoding="utf-8").strip()
    input_bytes = image_path.read_bytes()
    png_bytes = _to_png_bytes(input_bytes)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = out_root / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    input_image_path = out_dir / f"input_image{image_path.suffix or '.jpg'}"
    input_text_path = out_dir / "input_text.txt"
    openai_out_path = out_dir / "output_gpt.png"
    vertex_out_path = out_dir / "output_nanobanana.png"

    input_image_path.write_bytes(input_bytes)
    input_text_path.write_text(prompt, encoding="utf-8")

    aux_image_bytes: bytes | None = None
    if aux_image_path:
        aux_image_bytes = _load_aux_image(
            aux_path=aux_image_path,
            target_size=Image.open(BytesIO(png_bytes)).size,
        )
        (out_dir / "input_aux_image.png").write_bytes(aux_image_bytes)

    mask_bytes: bytes | None = None
    if mask_path:
        original_mask, protect_mask, openai_mask = _load_mask(
            mask_path=mask_path,
            target_size=Image.open(BytesIO(png_bytes)).size,
            mask_kind=mask_kind,
        )
        (out_dir / "input_mask_original.png").write_bytes(original_mask)
        (out_dir / "mask_protect_normalized.png").write_bytes(protect_mask)
        (out_dir / "openai_mask.png").write_bytes(openai_mask)
        mask_bytes = protect_mask

    openai_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    tasks = [
        _render_openai(
            api_key=openai_key,
            model=openai_model,
            image_bytes=png_bytes,
            aux_image_bytes=aux_image_bytes,
            mask_bytes=(openai_mask if mask_path else None),
            prompt=prompt,
            size=openai_size,
            timeout_seconds=openai_timeout,
        ),
    ]
    if not gpt_only:
        use_mask_hack = nanobanana_mask_mode == "hack" and mask_bytes is not None
        if use_mask_hack:
            (out_dir / "nanobanana_mask.png").write_bytes(mask_bytes)
        if nanobanana_api == "gemini":
            api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
            if not api_key:
                tasks.append(_fail("GEMINI_API_KEY is not set."))
            else:
                tasks.append(
                    _render_gemini_api(
                        api_key=api_key,
                        model=vertex_model,
                        image_bytes=png_bytes,
                        aux_image_bytes=aux_image_bytes,
                        mask_bytes=mask_bytes,
                        use_mask_hack=use_mask_hack,
                        prompt=prompt,
                        timeout_seconds=vertex_timeout,
                    )
                )
        else:
            tasks.append(
                _render_vertex(
                    project_id=settings.VERTEX_PROJECT_ID,
                    location=settings.NANOBANANA_LOCATION,
                    credentials_path=(
                        settings.NANO_BANANA_CREDENTIALS_PATH
                        or settings.GOOGLE_CLOUD_CREDENTIALS_PATH
                    ),
                    model=vertex_model,
                    image_bytes=png_bytes,
                    aux_image_bytes=aux_image_bytes,
                    mask_bytes=mask_bytes,
                    use_mask_hack=use_mask_hack,
                    prompt=prompt,
                    timeout_seconds=vertex_timeout,
                )
            )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    if isinstance(results[0], Exception):
        (out_dir / "output_gpt_error.txt").write_text(str(results[0]), encoding="utf-8")
    else:
        openai_out_path.write_bytes(results[0])

    if gpt_only:
        (out_dir / "output_nanobanana_skipped.txt").write_text(
            "Nano Banana skipped (GPT-only mode).",
            encoding="utf-8",
        )
    else:
        if isinstance(results[1], Exception):
            (out_dir / "output_nanobanana_error.txt").write_text(
                str(results[1]), encoding="utf-8"
            )
        else:
            vertex_out_path.write_bytes(results[1])

    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare OpenAI GPT Image and Vertex Nano Banana outputs."
    )
    parser.add_argument("--image", required=True, type=Path, help="Path to input image.")
    parser.add_argument("--text", required=True, type=Path, help="Path to input text.")
    parser.add_argument(
        "--out-root",
        type=Path,
        default=Path("outputs/compare"),
        help="Root output directory.",
    )
    parser.add_argument(
        "--openai-model",
        default=None,
        help="OpenAI image model name.",
    )
    parser.add_argument(
        "--openai-size",
        default=None,
        help="OpenAI output image size.",
    )
    parser.add_argument(
        "--openai-timeout",
        type=int,
        default=None,
        help="OpenAI request timeout in seconds.",
    )
    parser.add_argument(
        "--nanobanana-model",
        default=None,
        help="Vertex Nano Banana model name.",
    )
    parser.add_argument(
        "--nanobanana-timeout",
        type=int,
        default=None,
        help="Vertex request timeout in seconds.",
    )
    parser.add_argument(
        "--nanobanana-api",
        choices=["vertex", "gemini"],
        default=None,
        help="Which API to use for Nano Banana (vertex or gemini).",
    )
    parser.add_argument(
        "--gpt-only",
        action="store_true",
        help="Skip Nano Banana and render only GPT output.",
    )
    parser.add_argument(
        "--mask",
        type=Path,
        default=None,
        help="Optional mask image path.",
    )
    parser.add_argument(
        "--mask-kind",
        choices=["protect", "edit"],
        default="protect",
        help="Mask interpretation: protect (white=protected) or edit (white=editable).",
    )
    parser.add_argument(
        "--nanobanana-mask-mode",
        choices=["none", "hack"],
        default="none",
        help="Mask handling for Nano Banana (none or hack).",
    )
    parser.add_argument(
        "--aux-image",
        type=Path,
        default=None,
        help="Optional auxiliary image (e.g., depth/edges).",
    )
    args = parser.parse_args()
    settings = Settings(_env_file=ROOT_DIR / ".env")
    openai_model = args.openai_model or settings.OPENAI_IMAGE_MODEL
    openai_size = args.openai_size or settings.OPENAI_IMAGE_SIZE
    openai_timeout = args.openai_timeout or settings.OPENAI_IMAGE_TIMEOUT
    nanobanana_model = args.nanobanana_model or settings.NANOBANANA_MODEL
    nanobanana_timeout = args.nanobanana_timeout or settings.NANOBANANA_TIMEOUT
    nanobanana_api = args.nanobanana_api or settings.NANOBANANA_API
    gpt_only = args.gpt_only or nanobanana_api in {"off", "none", "disabled", "skip"}

    out_dir = asyncio.run(
        run(
            image_path=args.image,
            text_path=args.text,
            out_root=args.out_root,
            openai_model=openai_model,
            openai_size=openai_size,
            openai_timeout=openai_timeout,
            vertex_model=nanobanana_model,
            vertex_timeout=nanobanana_timeout,
            nanobanana_api=nanobanana_api,
            gpt_only=gpt_only,
            mask_path=args.mask,
            mask_kind=args.mask_kind,
            nanobanana_mask_mode=args.nanobanana_mask_mode,
            aux_image_path=args.aux_image,
        )
    )
    print(f"Saved comparison outputs to {out_dir}")


if __name__ == "__main__":
    main()
