from __future__ import annotations

from fastapi import Request

from web_api.routes.auth import (
    _json_success_with_cookie,
    _json_success_with_cookie_delete,
)


def _build_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/verify",
            "headers": [],
        }
    )


def test_json_success_with_cookie_includes_set_cookie_header() -> None:
    response = _json_success_with_cookie(
        {"status": "ok"},
        request=_build_request(),
        cookie_name="session",
        cookie_value="token",
        secure=False,
        max_age=3600,
    )

    header_names = [name.decode("latin-1") for name, _ in response.raw_headers]
    assert "set-cookie" in header_names


def test_json_success_with_cookie_delete_includes_set_cookie_header() -> None:
    response = _json_success_with_cookie_delete(
        {"status": "logged_out"},
        request=_build_request(),
        cookie_name="session",
        secure=False,
    )

    cookies = [
        value.decode("latin-1")
        for name, value in response.raw_headers
        if name.decode("latin-1") == "set-cookie"
    ]
    assert cookies
    assert any("Max-Age=0" in value or "expires=" in value.lower() for value in cookies)
