"""`POST /web/approvals`: the authenticated HTTP boundary for web decisions (issue #84).

    browser -> Next.js /api/approvals (same-origin) -> this endpoint
      -> verify the Supabase session (401)
      -> resolve the PARENT actor for the chosen child (403)
      -> WebApprovalChannel.decide -> EventLedger admission
      -> the projection publish moves the lifecycle the web app shows

The body is `{"child_id": ..., "command": WebApprovalCommand}`. The caller's
identity comes only from the verified session: nothing in the body names an
actor. Bodies are bounded before reading, requests are rate limited per
user, a cross-site Origin is refused, and a replayed `request_id` returns the
first answer instead of attempting a second decision (the ledger's receipt
check holds as well, across restarts). Replies never echo request content or
internal errors, and nothing here logs a user or child id.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Final

from pydantic import ValidationError

from serene.adapters.web.approvals import WebApprovalChannel, WebApprovalCommand
from serene.adapters.web.guardians import WebPrincipals
from serene.adapters.web.session import SessionVerifier
from serene.domain.base import ChildId, KernelModel

StartResponse = Callable[[str, list[tuple[str, str]]], Any]

PATH: Final = "/web/approvals"
MAX_BODY_BYTES: Final = 4096

_REASONS = {
    200: "OK",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    413: "Payload Too Large",
    415: "Unsupported Media Type",
    429: "Too Many Requests",
    500: "Internal Server Error",
}


class ApprovalRequest(KernelModel):
    child_id: ChildId
    command: WebApprovalCommand


@dataclass
class RateLimiter:
    """At most `limit` requests per user per `window` seconds (sliding window)."""

    limit: int = 10
    window: float = 60.0
    now: Callable[[], float] = time.monotonic
    _hits: dict[str, deque[float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def allow(self, key: str) -> bool:
        with self._lock:
            now = self.now()
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True


@dataclass
class ReplayCache:
    """The first answer to each (user, request_id), bounded. The ledger is the backstop."""

    capacity: int = 4096
    _entries: OrderedDict[tuple[str, str], tuple[str, dict[str, Any]]] = field(
        default_factory=OrderedDict
    )
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def get(self, key: tuple[str, str]) -> tuple[str, dict[str, Any]] | None:
        with self._lock:
            return self._entries.get(key)

    def put(self, key: tuple[str, str], digest: str, answer: dict[str, Any]) -> None:
        with self._lock:
            self._entries[key] = (digest, answer)
            while len(self._entries) > self.capacity:
                self._entries.popitem(last=False)


def make_approvals_app(
    channel: WebApprovalChannel,
    verifier: SessionVerifier,
    principals: WebPrincipals,
    *,
    allowed_origins: frozenset[str],
    limiter: RateLimiter | None = None,
    replays: ReplayCache | None = None,
) -> Callable[..., Iterable[bytes]]:
    limiter = limiter or RateLimiter()
    replays = replays or ReplayCache()
    # One decision at a time per process: a replayed request_id racing its
    # original must see the first answer, not attempt a second decision.
    decide_lock = threading.Lock()

    def app(env: dict[str, Any], start_response: StartResponse) -> Iterable[bytes]:
        if env.get("PATH_INFO") != PATH:
            return _error(start_response, 404, "NOT_FOUND")
        if env.get("REQUEST_METHOD") != "POST":
            return _error(start_response, 405, "METHOD_NOT_ALLOWED")
        origin = env.get("HTTP_ORIGIN")
        if origin is not None and origin not in allowed_origins:
            return _error(start_response, 403, "ORIGIN_NOT_ALLOWED")
        try:
            length = int(env.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY_BYTES:
            return _error(start_response, 413, "TOO_LARGE")
        content_type = str(env.get("CONTENT_TYPE", "")).split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return _error(start_response, 415, "JSON_REQUIRED")

        auth = str(env.get("HTTP_AUTHORIZATION", ""))
        scheme, _, token = auth.partition(" ")
        user_id = verifier.verify(token.strip()) if scheme.lower() == "bearer" else None
        if user_id is None:
            return _error(start_response, 401, "NOT_AUTHENTICATED")
        if not limiter.allow(user_id):
            return _error(start_response, 429, "RATE_LIMITED")

        body = env["wsgi.input"].read(length)
        try:
            request = ApprovalRequest.model_validate_json(body)
        except ValidationError:
            return _error(start_response, 400, "MALFORMED_REQUEST")
        actor = principals.parent(user_id, request.child_id)
        if actor is None:
            return _error(start_response, 403, "NOT_THIS_CHILDS_PARENT")

        key = (user_id, request.command.request_id)
        digest = hashlib.sha256(body).hexdigest()
        try:
            with decide_lock:
                seen = replays.get(key)
                if seen is not None:
                    if seen[0] != digest:
                        return _error(start_response, 409, "REQUEST_ID_REUSED")
                    return _reply(start_response, 200, seen[1])
                result = channel.decide(actor, request.child_id, request.command)
                answer = {
                    "outcome": result.outcome,
                    "event_ids": list(result.event_ids),
                    "reason_codes": list(result.reason_codes),
                }
                replays.put(key, digest, answer)
        except Exception:  # never leak internals to the caller
            return _error(start_response, 500, "INTERNAL_ERROR")
        return _reply(start_response, 200, answer)

    return app


def _error(start_response: StartResponse, status: int, code: str) -> list[bytes]:
    return _reply(start_response, status, {"error": code})


def _reply(start_response: StartResponse, status: int, payload: dict[str, Any]) -> list[bytes]:
    data = json.dumps(payload).encode("utf-8")
    start_response(
        f"{status} {_REASONS.get(status, 'Error')}",
        [
            ("Content-Type", "application/json"),
            ("Content-Length", str(len(data))),
            ("Cache-Control", "no-store"),
        ],
    )
    return [data]
