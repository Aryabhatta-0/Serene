"""neatlogs ObservabilitySink adapter (optional).

Receives attributes that `SafeTelemetry` has already redacted. neatlogs is
imported lazily so the kernel runs without it; if it is missing or not
configured, `build_sink` returns a no-op sink. The SDK reads NEATLOGS_API_KEY
(and optional NEATLOGS_ENDPOINT) itself; Serene never handles the key.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from serene.observability.telemetry import NoopSink, SafeTelemetry
from serene.ports.observability import AttributeValue, ObservabilitySink

# Span kinds used by Serene. GUARDRAIL covers deterministic policy decisions.
_KIND_BY_PREFIX = {
    "ledger.": "CHAIN",
    "policy.": "GUARDRAIL",
    "evidence.": "TOOL",
    "agent.": "AGENT",
}


class NeatlogsSink:
    def __init__(self, client: Any) -> None:
        self._client = client

    def emit(self, name: str, attributes: Mapping[str, AttributeValue]) -> None:
        kind = next((k for p, k in _KIND_BY_PREFIX.items() if name.startswith(p)), "CHAIN")
        with self._client.trace(name, kind=kind) as span:
            for key, value in attributes.items():
                span.set_attribute(f"serene.{key}", value)


def build_sink(workflow_name: str = "serene-kernel") -> ObservabilitySink:
    """Initialise neatlogs if installed and keyed; otherwise telemetry is a no-op."""
    if not os.environ.get("NEATLOGS_API_KEY"):
        return NoopSink()
    try:
        import neatlogs
    except ImportError:
        return NoopSink()
    neatlogs.init(workflow_name=workflow_name, tags=["serene"], capture_logs=False)
    return NeatlogsSink(neatlogs)


def build_telemetry(workflow_name: str = "serene-kernel") -> SafeTelemetry:
    key = os.environ.get("SERENE_TELEMETRY_PSEUDONYM_KEY", "").encode("utf-8") or None
    try:
        sink = build_sink(workflow_name)
    except Exception:  # observability failure must not block the kernel
        sink = NoopSink()
    return SafeTelemetry(sink, pseudonym_key=key)
