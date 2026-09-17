"""Decor8 API client."""
from __future__ import annotations

from typing import Any

import aiohttp

from config import Settings


class Decor8Service:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def generate_designs_for_room(
        self,
        *,
        input_image_url: str,
        room_type: str,
        design_style: str,
        prompt: str,
        num_images: int = 2,
        num_inference_steps: int = 75,
        design_style_image_url: str | None = None,
    ) -> dict[str, Any]:
        api_key = (self._settings.DECOR8_API_KEY or "").strip()
        if not api_key:
            raise RuntimeError("DECOR8_API_KEY is not set.")
        if not input_image_url.strip():
            raise RuntimeError("Decor8 fallback requires input_image_url.")

        base_url = (self._settings.DECOR8_API_BASE or "https://api.decor8.ai").rstrip("/")
        url = f"{base_url}/generate_designs_for_room"
        payload: dict[str, Any] = {
            "input_image_url": input_image_url,
            "room_type": " ".join((room_type or "").strip().split()),
            "design_style": " ".join((design_style or "").strip().split()),
            "num_images": max(1, int(num_images)),
            "num_inference_steps": max(1, int(num_inference_steps)),
        }
        normalized_prompt = " ".join((prompt or "").strip().split())
        if normalized_prompt:
            payload["prompt"] = normalized_prompt
        normalized_style_ref_url = " ".join((design_style_image_url or "").strip().split())
        if normalized_style_ref_url:
            payload["design_style_image_url"] = normalized_style_ref_url

        timeout = aiohttp.ClientTimeout(
            total=max(float(self._settings.DECOR8_TIMEOUT_SECONDS or 120), 1.0),
            connect=max(float(self._settings.DECOR8_TIMEOUT_CONNECT_SECONDS or 15), 0.5),
            sock_read=max(float(self._settings.DECOR8_TIMEOUT_READ_SECONDS or 110), 0.5),
        )
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    raise RuntimeError(f"Decor8 error {response.status}: {error_text}")
                return await response.json()


def extract_decor8_image_urls(payload: dict[str, Any]) -> list[str]:
    urls: list[str] = []

    direct_urls = payload.get("image_urls")
    if isinstance(direct_urls, list):
        for item in direct_urls:
            if isinstance(item, str) and item.strip():
                urls.append(item.strip())

    direct_url = payload.get("image_url")
    if isinstance(direct_url, str) and direct_url.strip():
        urls.append(direct_url.strip())

    info = payload.get("info")
    if isinstance(info, dict):
        images = info.get("images")
        if isinstance(images, list):
            for item in images:
                if isinstance(item, dict):
                    value = item.get("url")
                    if isinstance(value, str) and value.strip():
                        urls.append(value.strip())

    deduped: list[str] = []
    for value in urls:
        if value not in deduped:
            deduped.append(value)
    return deduped
