"""Small structured observability helpers."""
from __future__ import annotations

import logging
from typing import Any


def emit_observability_event(
    logger: logging.Logger,
    event: str,
    *,
    level: str = "info",
    request: Any | None = None,
    exc_info: Any | None = None,
    **fields: object,
) -> None:
    payload: dict[str, object] = {
        key: value for key, value in fields.items() if value is not None
    }
    if request is not None:
        payload.setdefault("request_method", getattr(request, "method", None))
        payload.setdefault("request_path", getattr(getattr(request, "url", None), "path", None))
        payload.setdefault("request_id", getattr(getattr(request, "state", None), "request_id", None))

    log_method = getattr(logger, str(level or "info").lower(), logger.info)
    log_method(event, extra=payload, exc_info=exc_info)
