"""Deterministic, offline `HermesTransport` for tests, evals and demos.

Replays canned Responses-API results per purpose ("propose", "plan_evidence",
"browse") in order, so a scenario is byte-reproducible without a model or
network. Entries may be exceptions to inject transport failures. It runs the
production adapters unchanged; only the wire to Hermes is replaced.
"""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from serene.adapters.hermes.transport import (
    HermesRequest,
    HermesResponse,
    HermesToolCall,
    HermesTransportError,
    HermesUsage,
)
from serene.adapters.hermes.wire import WIRE_VERSION

ScriptEntry = HermesResponse | Exception | Callable[[HermesRequest], HermesResponse]


class ScriptedHermesTransport:
    def __init__(self, script: Mapping[str, Iterable[ScriptEntry]] | None = None) -> None:
        self._queues: dict[str, deque[ScriptEntry]] = {
            purpose: deque(entries) for purpose, entries in (script or {}).items()
        }
        self.requests: list[HermesRequest] = []

    def push(self, purpose: str, *entries: ScriptEntry) -> None:
        self._queues.setdefault(purpose, deque()).extend(entries)

    def remaining(self, purpose: str) -> int:
        return len(self._queues.get(purpose, ()))

    def respond(self, request: HermesRequest) -> HermesResponse:
        self.requests.append(request)
        queue = self._queues.get(request.purpose)
        if not queue:
            raise HermesTransportError("TRANSIENT", "SCRIPT_EXHAUSTED")
        entry = queue.popleft()
        if isinstance(entry, Exception):
            raise entry
        if isinstance(entry, HermesResponse):
            return entry
        return entry(request)


def wire_response(
    payload: Mapping[str, Any],
    *,
    tool_calls: Iterable[HermesToolCall] = (),
    input_tokens: int = 1200,
    output_tokens: int = 300,
    model: str = "scripted/hermes",
) -> HermesResponse:
    body = {"contract": WIRE_VERSION, **payload}
    return HermesResponse(
        output_text=json.dumps(body, sort_keys=True),
        tool_calls=tuple(tool_calls),
        usage=HermesUsage(input_tokens=input_tokens, output_tokens=output_tokens),
        model=model,
    )


def raw_response(text: str, *, model: str = "scripted/hermes") -> HermesResponse:
    return HermesResponse(output_text=text, usage=HermesUsage(10, 10), model=model)
