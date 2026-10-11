"""Minimal WSGI endpoint for `TelegramChannel` (served by app/telegram).

Only `POST {path}` is accepted; bodies are bounded before reading; the reply
never echoes request content or internal errors.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from typing import Any

from serene.adapters.telegram.channel import MAX_BODY_BYTES, SECRET_HEADER, TelegramChannel

StartResponse = Callable[[str, list[tuple[str, str]]], Any]

_REASONS = {
    200: "OK",
    400: "Bad Request",
    401: "Unauthorized",
    404: "Not Found",
    405: "Method Not Allowed",
    413: "Payload Too Large",
    500: "Internal Server Error",
}


def make_wsgi_app(
    channel: TelegramChannel, *, path: str = "/telegram"
) -> Callable[..., Iterable[bytes]]:
    def app(wsgi_env: dict[str, Any], start_response: StartResponse) -> Iterable[bytes]:
        if wsgi_env.get("PATH_INFO") != path:
            return _reply(start_response, 404, "NOT_FOUND")
        if wsgi_env.get("REQUEST_METHOD") != "POST":
            return _reply(start_response, 405, "METHOD_NOT_ALLOWED")
        try:
            length = int(wsgi_env.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY_BYTES:
            return _reply(start_response, 413, "TOO_LARGE")
        body = wsgi_env["wsgi.input"].read(length)
        header_key = "HTTP_" + SECRET_HEADER.upper().replace("-", "_")
        headers = {SECRET_HEADER: str(wsgi_env.get(header_key, ""))}
        try:
            result = channel.handle(headers, body)
        except Exception:  # never leak internals to the caller
            return _reply(start_response, 500, "INTERNAL_ERROR")
        return _reply(start_response, result.http_status, result.outcome)

    return app


def _reply(start_response: StartResponse, status: int, outcome: str) -> list[bytes]:
    payload = json.dumps({"ok": status == 200, "outcome": outcome}).encode("utf-8")
    start_response(
        f"{status} {_REASONS.get(status, 'Error')}",
        [("Content-Type", "application/json"), ("Content-Length", str(len(payload)))],
    )
    return [payload]
