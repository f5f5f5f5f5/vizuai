"""Helpers for turning internal storage URLs into browser-safe media URLs."""
from __future__ import annotations

from urllib.parse import unquote, urlparse

from config import Settings
from services.storage import S3Storage


class MediaUrlResolver:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._storage = S3Storage(settings, prefix="uploads/")

    def resolve(self, url: str | None) -> str | None:
        if not url:
            return url
        key = self.extract_storage_key(url)
        if not key:
            return url
        return self._storage.get_signed_object_url(
            key,
            expires_in=max(int(self._settings.S3_PRESIGN_EXPIRES or 3600), 300),
        )

    def extract_storage_key(self, url: str | None) -> str | None:
        if not url:
            return None
        return self._extract_storage_key(url)

    def resolve_many(self, payload: dict, *fields: str) -> dict:
        resolved = dict(payload)
        for field in fields:
            if field in resolved:
                resolved[field] = self.resolve(resolved.get(field))
        return resolved

    def _extract_storage_key(self, url: str) -> str | None:
        parsed = urlparse(url)
        normalized_url = parsed._replace(query="", fragment="").geturl()

        template = self._settings.CDN_URL_TEMPLATE or ""
        if "{key}" in template:
            prefix, suffix = template.split("{key}", 1)
            if normalized_url.startswith(prefix) and (not suffix or normalized_url.endswith(suffix)):
                key = normalized_url[len(prefix):]
                if suffix:
                    key = key[: -len(suffix)]
                return unquote(key)

        if parsed.scheme == "gs" and parsed.netloc == self._settings.GCS_BUCKET:
            return unquote(parsed.path.lstrip("/")) or None

        if parsed.scheme in {"http", "https"} and parsed.netloc == "storage.googleapis.com":
            bucket_prefix = f"/{self._settings.GCS_BUCKET}/"
            if parsed.path.startswith(bucket_prefix):
                return unquote(parsed.path[len(bucket_prefix):])

        if parsed.scheme in {"http", "https"} and parsed.netloc == "storage.cloud.google.com":
            bucket_prefix = f"/{self._settings.GCS_BUCKET}/"
            if parsed.path.startswith(bucket_prefix):
                return unquote(parsed.path[len(bucket_prefix):])

        return None
