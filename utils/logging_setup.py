"""Shared logging setup with stable runtime context fields."""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone

_CONTEXT_FIELDS = (
    "service_name",
    "revision_name",
    "configuration_name",
    "app_mode",
    "project_id",
)

_STANDARD_LOG_RECORD_FIELDS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
}

_KV_PATTERN = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)=([^\s]+)")


class _StaticContextFilter(logging.Filter):
    def __init__(self, context: dict[str, str]) -> None:
        super().__init__()
        self._context = context

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in self._context.items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "severity": record.levelname,
            "logger": record.name,
            "message": message,
        }
        for key in _CONTEXT_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_FIELDS or key in payload:
                continue
            payload[key] = value
        for match in _KV_PATTERN.finditer(message):
            key = match.group(1)
            if key in payload:
                continue
            value = match.group(2).rstrip(",;")
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=_json_default)


def configure_logging(
    level: str = "INFO",
    app_mode: str | None = None,
    json_logs: bool | None = None,
) -> None:
    context = {
        "service_name": os.getenv("K_SERVICE", "unknown"),
        "revision_name": os.getenv("K_REVISION", "unknown"),
        "configuration_name": os.getenv("K_CONFIGURATION", "unknown"),
        "app_mode": app_mode or os.getenv("APP_MODE", "unknown"),
        "project_id": (
            os.getenv("GOOGLE_CLOUD_PROJECT")
            or os.getenv("GCP_PROJECT")
            or os.getenv("VERTEX_PROJECT_ID")
            or "unknown"
        ),
    }
    use_json_logs = _env_bool("LOG_JSON", True) if json_logs is None else bool(json_logs)

    handler = logging.StreamHandler()
    handler.addFilter(_StaticContextFilter(context))
    handler.setFormatter(
        _JsonFormatter()
        if use_json_logs
        else logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
