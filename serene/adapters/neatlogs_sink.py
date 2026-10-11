"""neatlogs ObservabilitySink adapter: span trees POSTed to /v1/trace (issue #52).

Privacy. Attributes reach the sink through `SafeTelemetry` (the central redaction).
The sink re-applies the same `redact` (idempotent on redacted input), so a caller
that hands it raw attributes still cannot leak free text or a raw child id. Root
attributes (session id, end user, verification marker) must be opaque tokens.

Bounded. neatlogs' ingest edge refuses request bodies over ~8 KiB with an HTML 403
(measured 2026-10-10: 8,150 bytes accepted, 8,364 refused). `flush` packs pending
spans into traces whose serialized body stays under `max_body_bytes`; each trace
carries the same session id, so one run is one neatlogs session. Pending spans are
capped; overflow is dropped and counted, never buffered without bound.

Explicit. `flush` returns a `FlushReport` (batches sent/failed, spans dropped, error
codes). It never raises, never follows a redirect (the API key must not be
forwarded), sends only over https (plain http only to loopback, for offline tests),
and reports codes such as HTTP_403, never a response body or the key.

Telemetry cannot change a product outcome: `emit` only buffers, and SafeTelemetry
swallows any sink failure. Uses only the standard library; no neatlogs SDK.
"""

from __future__ import annotations

import atexit
import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlsplit

from serene.observability.telemetry import NoopSink, SafeTelemetry, redact
from serene.ports.observability import AttributeValue, ObservabilitySink

DEFAULT_ENDPOINT: Final = "https://ingest.neatlogs.com/v1/trace"
MAX_BODY_BYTES: Final = 7_000  # under the ~8 KiB edge limit, with headroom
MAX_PENDING_SPANS: Final = 5_000
_LOOPBACK: Final = frozenset({"127.0.0.1", "localhost", "::1"})
_ROOT_TOKEN: Final = re.compile(r"^[A-Za-z0-9_:\-.]{1,128}$")

# Span kinds used by Serene. GUARDRAIL covers deterministic policy decisions.
_KIND_BY_PREFIX: Final = {
    "ledger.": "CHAIN",
    "policy.": "GUARDRAIL",
    "evidence.": "TOOL",
    "browser.": "TOOL",
    "agent.": "AGENT",
    "runtime.call": "LLM",
    "runtime.run": "CHAIN",
    "runtime.plan": "CHAIN",
    "context.": "RETRIEVER",
    "telegram.": "HTTP",
}
_ERROR_STATUSES: Final = frozenset({"FAILED", "REJECTED", "ERROR"})
_BIG: Final = 10**9  # widest batch index/count the envelope size allows for

Opener = Callable[[urllib.request.Request, float], int]


@dataclass(frozen=True, slots=True)
class FlushReport:
    session_id: str | None
    spans: int
    batches: int
    batches_sent: int
    dropped_spans: int
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """Every pending span reached ingest (nothing dropped, every batch accepted)."""
        return self.batches_sent == self.batches and not self.dropped_spans and not self.errors


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None  # urllib then raises HTTPError for the 3xx; the key goes nowhere else


def _urllib_opener(request: urllib.request.Request, timeout: float) -> int:
    opener = urllib.request.build_opener(_NoRedirect)
    with opener.open(request, timeout=timeout) as response:
        return int(response.status)


def _token(value: str | None) -> str | None:
    return value if value is not None and _ROOT_TOKEN.match(value) else None


def endpoint_allowed(endpoint: str) -> bool:
    """https anywhere; plain http only to a loopback host (offline fake servers)."""
    try:
        parts = urlsplit(endpoint)
        host = (parts.hostname or "").lower()
        _ = parts.port
    except ValueError:
        return False
    if parts.username is not None or parts.password is not None or not host:
        return False
    return parts.scheme == "https" or (parts.scheme == "http" and host in _LOOPBACK)


def _verification_marker() -> str | None:
    for item in os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "").split(","):
        key, _, value = item.partition("=")
        if key.strip() == "neatlogs.verification.marker":
            return _token(value.strip())
    return None


def _span(name: str, attributes: Mapping[str, AttributeValue]) -> dict[str, Any]:
    kind = next((k for p, k in _KIND_BY_PREFIX.items() if name.startswith(p)), "CHAIN")
    span: dict[str, Any] = {"name": name, "kind": kind}
    prompt, completion = attributes.get("input_tokens"), attributes.get("output_tokens")
    if isinstance(prompt, int) or isinstance(completion, int):
        span["tokens"] = {
            "prompt": prompt if isinstance(prompt, int) else 0,
            "completion": completion if isinstance(completion, int) else 0,
        }
    if isinstance(attributes.get("tool"), str) and attributes["tool"]:
        span["tool_name"] = attributes["tool"]
    if isinstance(attributes.get("duration_ms"), int):
        span["duration_ms"] = attributes["duration_ms"]
    if "status" in attributes:
        span["status"] = "ERROR" if attributes["status"] in _ERROR_STATUSES else "OK"
    rest = {
        f"serene.{k}": v
        for k, v in attributes.items()
        if k not in {"input_tokens", "output_tokens", "duration_ms"}
    }
    if rest:
        span["attributes"] = rest
    return span


def _size(obj: Any) -> int:
    return len(json.dumps(obj, separators=(",", ":")).encode("utf-8"))


class NeatlogsSink:
    def __init__(
        self,
        workflow_name: str = "serene-kernel",
        *,
        api_key: str,
        endpoint: str | None = None,
        session_id: str | None = None,
        end_user_id: str | None = None,
        max_body_bytes: int = MAX_BODY_BYTES,
        max_pending_spans: int = MAX_PENDING_SPANS,
        timeout_s: float = 10.0,
        opener: Opener = _urllib_opener,
    ) -> None:
        self.workflow_name = workflow_name
        self._api_key = api_key
        self.endpoint = endpoint or DEFAULT_ENDPOINT
        self.session_id = session_id
        self.end_user_id = _token(end_user_id)
        self._max_body = max_body_bytes
        self._max_pending = max_pending_spans
        self._timeout = timeout_s
        self._open = opener
        self._pending: list[dict[str, Any]] = []
        self._dropped = 0
        self.last_report: FlushReport | None = None

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @session_id.setter
    def session_id(self, value: str | None) -> None:
        self._session_id = _token(value)

    @property
    def pending(self) -> int:
        return len(self._pending)

    def emit(self, name: str, attributes: Mapping[str, AttributeValue]) -> None:
        if len(self._pending) >= self._max_pending:
            self._dropped += 1
            return
        self._pending.append(_span(name, redact(attributes, pseudonym_key=None)))

    # ------------------------------------------------------------------ flush
    def _root(self, status: str, index: int, children: list[dict[str, Any]]) -> dict[str, Any]:
        attributes: dict[str, Any] = {"serene.batch.index": index}
        if self._session_id:
            attributes["neatlogs.session.id"] = self._session_id
        if self.end_user_id:
            attributes["neatlogs.end_user.id"] = self.end_user_id
        marker = _verification_marker()
        if marker:
            attributes["neatlogs.verification.marker"] = marker
        return {
            "name": self.workflow_name,
            "status": status,
            "attributes": attributes,
            "children": children,
        }

    def _batches(self, status: str) -> tuple[list[dict[str, Any]], int]:
        """Greedy, order-preserving packing under the body limit; oversized spans dropped."""
        # Envelope measured with the largest index/count values it can carry.
        probe = self._root(status, _BIG, [])
        probe["attributes"]["serene.batch.count"] = _BIG
        envelope = _size(probe)
        groups: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        used = envelope
        too_large = 0
        for span in self._pending:
            size = _size(span)
            if envelope + size > self._max_body:
                too_large += 1
                continue
            if current and used + 1 + size > self._max_body:  # +1: the separating comma
                groups.append(current)
                current, used = [], envelope
            used += size + (1 if current else 0)
            current.append(span)
        if current:
            groups.append(current)
        return [self._root(status, i, g) for i, g in enumerate(groups)], too_large

    def _post(self, body: bytes) -> str | None:
        """None when ingest accepted the batch, else a code. Never raises."""
        request = urllib.request.Request(  # noqa: S310 - endpoint vetted by endpoint_allowed
            self.endpoint,
            data=body,
            headers={"x-api-key": self._api_key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            status = self._open(request, self._timeout)
        except urllib.error.HTTPError as exc:
            return "REDIRECT_REFUSED" if 300 <= exc.code < 400 else f"HTTP_{exc.code}"
        except TimeoutError:
            return "TIMEOUT"
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, TimeoutError):
                return "TIMEOUT"
            return f"NETWORK_{type(reason).__name__}"
        except Exception as exc:  # telemetry never raises into the caller
            return f"NETWORK_{type(exc).__name__}"
        return None if 200 <= status < 300 else f"HTTP_{status}"

    def flush(self, status: str = "OK") -> FlushReport:
        spans, dropped = len(self._pending), self._dropped
        errors: list[str] = []
        batches: list[dict[str, Any]] = []
        sent = 0
        if not self._api_key:
            errors.append("NO_API_KEY")
        elif not endpoint_allowed(self.endpoint):
            errors.append("ENDPOINT_REJECTED")
        elif self._pending:
            batches, too_large = self._batches("ERROR" if status == "ERROR" else "OK")
            dropped += too_large
            for batch in batches:
                batch["attributes"]["serene.batch.count"] = len(batches)
                code = self._post(json.dumps(batch, separators=(",", ":")).encode("utf-8"))
                if code is None:
                    sent += 1
                else:
                    errors.append(code)
        if errors and not batches:
            dropped += spans  # nothing could be sent: the pending spans are lost, and said so
        self._pending, self._dropped = [], 0  # bounded: no retry queue, failures are reported
        report = FlushReport(
            self._session_id, spans, len(batches), sent, dropped, tuple(dict.fromkeys(errors))
        )
        self.last_report = report
        return report


def build_sink(
    workflow_name: str = "serene-kernel",
    *,
    session_id: str | None = None,
    flush_at_exit: bool = False,
) -> ObservabilitySink:
    """The HTTP sink when NEATLOGS_API_KEY is set; otherwise telemetry is a no-op."""
    api_key = os.environ.get("NEATLOGS_API_KEY", "")
    if not api_key:
        return NoopSink()
    sink = NeatlogsSink(
        workflow_name,
        api_key=api_key,
        endpoint=os.environ.get("NEATLOGS_ENDPOINT") or None,
        session_id=session_id or os.environ.get("NEATLOGS_SESSION_ID") or None,
        end_user_id=os.environ.get("NEATLOGS_END_USER_ID") or None,
    )
    if flush_at_exit:
        atexit.register(sink.flush)
    return sink


def build_telemetry(workflow_name: str = "serene-kernel") -> SafeTelemetry:
    key = os.environ.get("SERENE_TELEMETRY_PSEUDONYM_KEY", "").encode("utf-8") or None
    try:
        sink = build_sink(workflow_name, flush_at_exit=True)
    except Exception:  # observability failure must not block the kernel
        sink = NoopSink()
    return SafeTelemetry(sink, pseudonym_key=key)
