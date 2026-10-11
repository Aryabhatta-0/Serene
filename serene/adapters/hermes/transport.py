"""Transport to a running Hermes Agent (pinned tag v2026.9.24).

Serene talks to Hermes over its OpenAI-compatible API server
(`POST {HERMES_API_BASE_URL}/responses`, bearer `HERMES_API_SERVER_KEY`), so no
Hermes code is imported into this process. The Responses API returns the tool
calls Hermes actually executed as `function_call` / `function_call_output`
items; adapters audit those against their bounds instead of trusting the
model's own account of what it did.

Every failure is classified (TRANSIENT / AUTH / PROTOCOL / REFUSED) so callers
can apply a finite retry budget without guessing.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Final, Literal, Protocol, runtime_checkable

MAX_RESPONSE_BYTES: Final = 1_000_000
DEFAULT_BASE_URL: Final = "http://127.0.0.1:8642/v1"

FailureKind = Literal["TRANSIENT", "AUTH", "PROTOCOL", "REFUSED"]

# Hermes reports a provider failure (no credentials, rate limit, provider down) as a
# *completed* response whose only output is a "⚠️ <label>: <error>" line and whose
# usage is zero: no model ran. Without this check that line would be read as model
# output, blamed on the model (WIRE_NOT_JSON), repaired and retried. Labels per
# hermes-agent v0.21.6 `gateway/platforms/api_server.py` and `gateway/run.py`.
_ENVELOPE_PREFIX: Final = "\u26a0"  # WARNING SIGN
_PROVIDER_FAILURES: Final[tuple[tuple[re.Pattern[str], FailureKind, str], ...]] = (
    (
        re.compile(r"provider\s+authentication\s+failed|(in(valid|correct))\s+api\s+key", re.I),
        "AUTH",
        "PROVIDER_AUTH",
    ),
    (
        re.compile(r"rate[\s-]+limit|quota|usage\s+limit|\b429\b", re.I),
        "TRANSIENT",
        "PROVIDER_RATE_LIMITED",
    ),
    (
        re.compile(r"connection\s+(refused|reset|error|timeout)|unreachable|timed?\s*out", re.I),
        "TRANSIENT",
        "PROVIDER_UNREACHABLE",
    ),
)


class HermesTransportError(RuntimeError):
    def __init__(self, kind: FailureKind, code: str) -> None:
        super().__init__(f"{kind}:{code}")
        self.kind: FailureKind = kind
        self.code = code


@dataclass(frozen=True, slots=True)
class HermesToolCall:
    """A tool call Hermes executed (from the Responses `output` items)."""

    call_id: str
    name: str
    arguments: str
    output: str | None = None

    def parsed_arguments(self) -> dict[str, Any]:
        try:
            value = json.loads(self.arguments)
        except (ValueError, TypeError):
            return {}
        return value if isinstance(value, dict) else {}


@dataclass(frozen=True, slots=True)
class HermesUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class HermesRequest:
    purpose: Literal["propose", "plan_evidence", "browse"]
    instructions: str
    input: str
    session_ref: str


@dataclass(frozen=True, slots=True)
class HermesResponse:
    output_text: str
    tool_calls: tuple[HermesToolCall, ...] = ()
    usage: HermesUsage = field(default_factory=HermesUsage)
    model: str | None = None
    status: str = "completed"
    latency_ms: int = 0


@runtime_checkable
class HermesTransport(Protocol):
    def respond(self, request: HermesRequest) -> HermesResponse: ...


def parse_responses_payload(data: Any, *, latency_ms: int = 0) -> HermesResponse:
    """Map an OpenAI-Responses-shaped payload to `HermesResponse` (pure; fails closed)."""
    if not isinstance(data, dict) or not isinstance(data.get("output"), list):
        raise HermesTransportError("PROTOCOL", "NO_OUTPUT")
    status = str(data.get("status", "completed"))
    if status in {"failed", "cancelled", "incomplete"}:
        raise HermesTransportError(
            "TRANSIENT" if status == "failed" else "PROTOCOL", status.upper()
        )
    texts: list[str] = []
    calls: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in data["output"]:
        if not isinstance(item, dict):
            raise HermesTransportError("PROTOCOL", "BAD_ITEM")
        kind = item.get("type")
        if kind == "message" and item.get("phase") != "commentary":
            for part in item.get("content") or []:
                if isinstance(part, dict) and part.get("type") == "refusal":
                    raise HermesTransportError("REFUSED", "MODEL_REFUSAL")
                if isinstance(part, dict) and part.get("type") == "output_text":
                    texts.append(str(part.get("text", "")))
        elif kind == "function_call":
            call_id = str(item.get("call_id", ""))
            calls[call_id] = {"name": str(item.get("name", "")), "arguments": item.get("arguments")}
            order.append(call_id)
        elif kind == "function_call_output":
            call_id = str(item.get("call_id", ""))
            calls.setdefault(call_id, {"name": "", "arguments": "{}"})
            calls[call_id]["output"] = item.get("output")
            if call_id not in order:
                order.append(call_id)
    tool_calls = tuple(
        HermesToolCall(
            call_id=cid,
            name=calls[cid]["name"],
            arguments=(
                calls[cid]["arguments"]
                if isinstance(calls[cid]["arguments"], str)
                else json.dumps(calls[cid]["arguments"] or {})
            ),
            output=None if calls[cid].get("output") is None else str(calls[cid]["output"]),
        )
        for cid in order
    )
    raw_usage = data.get("usage")
    usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
    if not tool_calls:
        _raise_on_provider_failure("".join(texts), usage)
    raw_runtime = data.get("runtime")
    runtime: dict[str, Any] = raw_runtime if isinstance(raw_runtime, dict) else {}
    return HermesResponse(
        output_text="".join(texts),
        tool_calls=tool_calls,
        usage=HermesUsage(
            input_tokens=_int_or_none(usage.get("input_tokens")),
            output_tokens=_int_or_none(usage.get("output_tokens")),
        ),
        model=str(runtime.get("model") or data.get("model") or "") or None,
        status=status,
        latency_ms=latency_ms,
    )


def _raise_on_provider_failure(text: str, usage: dict[str, Any]) -> None:
    """A zero-usage "⚠️ ..." reply is Hermes reporting that no model ran."""
    if not text.lstrip().startswith(_ENVELOPE_PREFIX):
        return
    if any(_int_or_none(usage.get(k)) for k in ("input_tokens", "output_tokens")):
        return  # a model produced this text; it is model output, not an envelope
    for pattern, kind, code in _PROVIDER_FAILURES:
        if pattern.search(text):
            raise HermesTransportError(kind, code)
    raise HermesTransportError("PROTOCOL", "PROVIDER_FAILURE")


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class HttpHermesTransport:
    """stdlib HTTP client for the Hermes API server. Never logs prompts or keys."""

    def __init__(self, base_url: str, api_key: str, *, timeout_s: float = 120.0) -> None:
        if not base_url.startswith(("http://127.0.0.1", "http://localhost", "https://")):
            raise ValueError("Hermes API must be loopback http or https")
        if not api_key:
            raise ValueError("HERMES_API_SERVER_KEY is required")
        self._url = base_url.rstrip("/") + "/responses"
        self._key = api_key
        self._timeout = timeout_s

    def respond(self, request: HermesRequest) -> HermesResponse:
        body = json.dumps(
            {
                "model": "hermes-agent",
                "instructions": request.instructions,
                "input": request.input,
                "store": False,
            }
        ).encode("utf-8")
        http_request = urllib.request.Request(  # noqa: S310 - scheme checked in __init__
            self._url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
                "X-Hermes-Session-Id": request.session_ref,
            },
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(http_request, timeout=self._timeout) as resp:  # noqa: S310
                raw = resp.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise HermesTransportError("AUTH", f"HTTP_{exc.code}") from None
            kind: FailureKind = (
                "TRANSIENT" if exc.code in (408, 429) or exc.code >= 500 else "PROTOCOL"
            )
            raise HermesTransportError(kind, f"HTTP_{exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise HermesTransportError("TRANSIENT", "UNREACHABLE") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise HermesTransportError("PROTOCOL", "RESPONSE_TOO_LARGE")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise HermesTransportError("PROTOCOL", "NOT_JSON") from None
        return parse_responses_payload(data, latency_ms=int((time.monotonic() - started) * 1000))


def transport_from_env() -> HttpHermesTransport | None:
    """The configured Hermes transport, or None (callers then fail closed)."""
    key = os.environ.get("HERMES_API_SERVER_KEY", "")
    if not key:
        return None
    return HttpHermesTransport(os.environ.get("HERMES_API_BASE_URL") or DEFAULT_BASE_URL, key)
