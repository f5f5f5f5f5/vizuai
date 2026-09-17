"""GCS storage helper."""
from __future__ import annotations

from datetime import timedelta
import logging
import os
from pathlib import Path
import secrets
import ssl
import time
from typing import BinaryIO
from urllib.parse import unquote, urlparse

from google.api_core.exceptions import (
    BadGateway,
    GatewayTimeout,
    InternalServerError,
    NotFound,
    RetryError,
    ServiceUnavailable,
    TooManyRequests,
)
from google.auth import compute_engine
from google.auth import default as google_auth_default
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.cloud import storage
from google.oauth2 import service_account

from config import Settings
from utils.time import utcnow


logger = logging.getLogger("storage")

_UPLOAD_TIMEOUT_SECONDS = 240
_DOWNLOAD_TIMEOUT_SECONDS = 120
_STORAGE_MAX_ATTEMPTS = 3


class S3Storage:
    def __init__(self, settings: Settings, prefix: str = "crops/") -> None:
        self._settings = settings
        self._prefix = prefix.rstrip("/") + "/"
        credentials = None
        if settings.GCS_CREDENTIALS_PATH:
            credentials = service_account.Credentials.from_service_account_file(
                settings.GCS_CREDENTIALS_PATH
            )
        elif os.getenv("K_SERVICE"):
            credentials = compute_engine.Credentials()
        else:
            credentials, _ = google_auth_default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        self._signing_credentials = credentials
        self._client = storage.Client(
            project=settings.VERTEX_PROJECT_ID,
            credentials=credentials,
        )
        self._bucket = self._client.bucket(settings.GCS_BUCKET)

    def upload_bytes(self, data: bytes, suffix: str = ".jpg", prefix: str | None = None) -> str:
        key = self._build_key(suffix, prefix)
        blob = self._bucket.blob(key)
        self._with_retry(
            lambda: _call_blob_method(
                blob.upload_from_string,
                data,
                content_type=_content_type_for_suffix(suffix),
                timeout=_UPLOAD_TIMEOUT_SECONDS,
            ),
            op_name="upload_bytes",
            key=key,
        )
        return self._settings.CDN_URL_TEMPLATE.format(key=key)

    def download_bytes(self, key: str) -> bytes:
        blob = self._bucket.blob(key)
        return self._with_retry(
            lambda: _call_blob_method(
                blob.download_as_bytes,
                timeout=_DOWNLOAD_TIMEOUT_SECONDS,
            ),
            op_name="download_bytes",
            key=key,
        )

    def upload_file(
        self, file_path: str | Path, content_type: str = "image/jpeg", prefix: str | None = None
    ) -> str:
        key = self._build_key(Path(file_path).suffix or ".bin", prefix)
        blob = self._bucket.blob(key)
        self._with_retry(
            lambda: _call_blob_method(
                blob.upload_from_filename,
                str(file_path),
                content_type=content_type,
                timeout=_UPLOAD_TIMEOUT_SECONDS,
            ),
            op_name="upload_file",
            key=key,
        )
        return self._settings.CDN_URL_TEMPLATE.format(key=key)

    def upload_stream(
        self,
        stream: BinaryIO,
        content_type: str = "image/jpeg",
        suffix: str = ".jpg",
        prefix: str | None = None,
    ) -> str:
        key = self._build_key(suffix, prefix)
        blob = self._bucket.blob(key)
        self._with_retry(
            lambda: _call_blob_method(
                blob.upload_from_file,
                stream,
                content_type=content_type,
                timeout=_UPLOAD_TIMEOUT_SECONDS,
            ),
            op_name="upload_stream",
            key=key,
        )
        return self._settings.CDN_URL_TEMPLATE.format(key=key)

    def upload_bytes_presigned(
        self,
        data: bytes,
        suffix: str = ".jpg",
        prefix: str | None = None,
        expires_in: int = 3600,
    ) -> str:
        key = self._build_key(suffix, prefix)
        blob = self._bucket.blob(key)
        self._with_retry(
            lambda: _call_blob_method(
                blob.upload_from_string,
                data,
                content_type=_content_type_for_suffix(suffix),
                timeout=_UPLOAD_TIMEOUT_SECONDS,
            ),
            op_name="upload_bytes_presigned",
            key=key,
        )
        return self._generate_signed_url(blob, expires_in)

    def create_signed_upload_url(
        self,
        *,
        content_type: str,
        suffix: str,
        prefix: str | None = None,
        expires_in: int = 3600,
    ) -> tuple[str, str]:
        key = self._build_key(suffix, prefix)
        blob = self._bucket.blob(key)
        return key, self._generate_signed_upload_url(
            blob,
            content_type=content_type,
            expires_in=expires_in,
        )

    def get_object_url(self, key: str) -> str:
        return self._settings.CDN_URL_TEMPLATE.format(key=key)

    def get_signed_object_url(self, key: str, expires_in: int = 3600) -> str:
        blob = self._bucket.blob(key)
        return self._generate_signed_url(blob, expires_in)

    def extract_storage_key(self, url: str | None) -> str | None:
        if not url:
            return None
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

    def get_object_metadata(self, key: str) -> dict | None:
        blob = self._bucket.blob(key)
        try:
            self._with_retry(
                lambda: _call_blob_method(
                    blob.reload,
                    timeout=_DOWNLOAD_TIMEOUT_SECONDS,
                ),
                op_name="reload_metadata",
                key=key,
            )
        except NotFound:
            return None
        return {
            "size_bytes": int(blob.size or 0),
            "content_type": str(blob.content_type or "").strip().lower() or None,
        }

    def _with_retry(self, func, *, op_name: str, key: str):
        last_exc: Exception | None = None
        for attempt in range(1, _STORAGE_MAX_ATTEMPTS + 1):
            try:
                return func()
            except Exception as exc:
                last_exc = exc
                if attempt >= _STORAGE_MAX_ATTEMPTS or not _is_retryable_storage_error(exc):
                    raise
                logger.warning(
                    "storage_%s_retry key=%s attempt=%s/%s error=%s",
                    op_name,
                    key,
                    attempt,
                    _STORAGE_MAX_ATTEMPTS,
                    _exc_text(exc),
                )
                time.sleep(min(4.0, 0.75 * (2 ** (attempt - 1))))
        if last_exc is not None:
            raise last_exc

    def _generate_signed_url(self, blob: storage.Blob, expires_in: int) -> str:
        if self._signing_credentials is not None and hasattr(
            self._signing_credentials, "sign_bytes"
        ):
            return blob.generate_signed_url(
                expiration=timedelta(seconds=expires_in),
                method="GET",
                version="v4",
                credentials=self._signing_credentials,
            )
        credentials = self._signing_credentials
        if credentials is not None:
            if hasattr(credentials, "sign_bytes"):
                return blob.generate_signed_url(
                    expiration=timedelta(seconds=expires_in),
                    method="GET",
                    version="v4",
                    credentials=credentials,
                )
            credentials.refresh(GoogleAuthRequest())
            service_account_email = getattr(credentials, "service_account_email", None)
            access_token = getattr(credentials, "token", None)
            if service_account_email and access_token:
                return blob.generate_signed_url(
                    expiration=timedelta(seconds=expires_in),
                    method="GET",
                    version="v4",
                    service_account_email=service_account_email,
                    access_token=access_token,
                )
        raise RuntimeError(
            "Cannot generate signed URL without signing credentials. "
            "Set GCS_CREDENTIALS_PATH (service account JSON with private key) "
            "or disable presigned URLs (S3_PRESIGN_INPUTS=false) and use a public bucket."
        )

    def _generate_signed_upload_url(
        self,
        blob: storage.Blob,
        *,
        content_type: str,
        expires_in: int,
    ) -> str:
        if self._signing_credentials is not None and hasattr(
            self._signing_credentials, "sign_bytes"
        ):
            return blob.generate_signed_url(
                expiration=timedelta(seconds=expires_in),
                method="PUT",
                version="v4",
                content_type=content_type,
                credentials=self._signing_credentials,
            )
        credentials = self._signing_credentials
        if credentials is not None:
            if hasattr(credentials, "sign_bytes"):
                return blob.generate_signed_url(
                    expiration=timedelta(seconds=expires_in),
                    method="PUT",
                    version="v4",
                    content_type=content_type,
                    credentials=credentials,
                )
            credentials.refresh(GoogleAuthRequest())
            service_account_email = getattr(credentials, "service_account_email", None)
            access_token = getattr(credentials, "token", None)
            if service_account_email and access_token:
                return blob.generate_signed_url(
                    expiration=timedelta(seconds=expires_in),
                    method="PUT",
                    version="v4",
                    content_type=content_type,
                    service_account_email=service_account_email,
                    access_token=access_token,
                )
        raise RuntimeError(
            "Cannot generate signed upload URL without signing credentials. "
            "Set GCS_CREDENTIALS_PATH (service account JSON with private key)."
        )

    def _build_key(self, suffix: str, prefix: str | None = None) -> str:
        now = utcnow()
        timestamp = now.strftime("%Y%m%d/%H%M%S")
        filename = f"{timestamp}-{int(now.timestamp() * 1000)}-{secrets.token_hex(4)}{suffix}"
        base_prefix = self._prefix if prefix is None else prefix.rstrip("/") + "/"
        return f"{base_prefix}{filename}"


def _content_type_for_suffix(suffix: str) -> str:
    if suffix.lower() == ".png":
        return "image/png"
    return "image/jpeg"


def _call_blob_method(method, *args, timeout: int | float | None = None, **kwargs):
    if timeout is None:
        return method(*args, **kwargs)
    try:
        return method(*args, timeout=timeout, **kwargs)
    except TypeError as exc:
        if "timeout" not in str(exc):
            raise
        return method(*args, **kwargs)


def _exc_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def _is_retryable_storage_error(exc: Exception) -> bool:
    retryable_types = (
        RetryError,
        ServiceUnavailable,
        TooManyRequests,
        GatewayTimeout,
        InternalServerError,
        BadGateway,
        TimeoutError,
        OSError,
        ssl.SSLError,
    )
    for item in _iter_exception_chain(exc):
        if isinstance(item, retryable_types):
            return True
        try:
            import requests

            if isinstance(item, requests.exceptions.RequestException):
                return True
        except Exception:
            pass
        message = str(item).lower()
        if any(
            needle in message
            for needle in (
                "timed out",
                "timeout",
                "unexpected eof while reading",
                "broken pipe",
                "connection reset",
                "temporarily unavailable",
                "connection aborted",
            )
        ):
            return True
    return False


def _iter_exception_chain(exc: Exception):
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__
