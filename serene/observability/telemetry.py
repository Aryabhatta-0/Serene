"""Central, privacy-safe telemetry boundary (issue #52).

All telemetry flows through `SafeTelemetry`, which
1. keeps only allow-listed attribute keys,
2. keeps only token-like values (opaque ids, enums, codes, ints) - anything
   containing whitespace or free text is dropped, so prose (and therefore
   child narratives) cannot leak by accident,
3. replaces child ids with a keyed pseudonym (or drops them if no key), and
4. swallows every sink failure: telemetry can never change a kernel outcome.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Mapping
from typing import Final

from serene.ports.observability import AttributeValue, ObservabilitySink

ALLOWED_KEYS: Final = frozenset(
    {
        "event_type",
        "event_id",
        "sequence",
        "actor_kind",
        "source_kind",
        "decision",
        "reason_codes",
        "policy_version",
        "level",
        "safety_class",
        "verification_status",
        "duration_ms",
        "error_type",
        "projection",
        "count",
        "child_ref",
        "chain_ok",
        "failure_index",
    }
)
_TOKEN = re.compile(r"^[A-Za-z0-9_:\-.,/]{0,256}$")
_NAME = re.compile(r"^[a-z][a-z0-9_.]{0,63}$")


def pseudonymize_child(child_id: str, key: bytes | None) -> str | None:
    if not key:
        return None
    digest = hmac.new(key, child_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"cref_{digest[:24]}"


def redact(
    attributes: Mapping[str, object], *, pseudonym_key: bytes | None
) -> dict[str, AttributeValue]:
    out: dict[str, AttributeValue] = {}
    for key, value in attributes.items():
        if key == "child_id":
            ref = pseudonymize_child(str(value), pseudonym_key)
            if ref is not None:
                out["child_ref"] = ref
            continue
        if key not in ALLOWED_KEYS:
            continue
        if isinstance(value, bool | int) or (isinstance(value, str) and _TOKEN.match(value)):
            out[key] = value
        elif isinstance(value, tuple | list) and all(
            isinstance(v, str) and _TOKEN.match(v) for v in value
        ):
            joined = ",".join(value)
            if _TOKEN.match(joined):
                out[key] = joined
    return out


class NoopSink:
    def emit(self, name: str, attributes: Mapping[str, AttributeValue]) -> None:
        return None


class RecordingSink:
    """In-memory sink for tests and local debugging."""

    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, AttributeValue]]] = []

    def emit(self, name: str, attributes: Mapping[str, AttributeValue]) -> None:
        self.records.append((name, dict(attributes)))


class SafeTelemetry:
    def __init__(
        self, sink: ObservabilitySink | None = None, *, pseudonym_key: bytes | None = None
    ):
        self._sink: ObservabilitySink = sink or NoopSink()
        self._key = pseudonym_key
        self.dropped = 0

    def emit(self, name: str, attributes: Mapping[str, object]) -> None:
        try:
            if not _NAME.match(name):
                self.dropped += 1
                return
            self._sink.emit(name, redact(attributes, pseudonym_key=self._key))
        except Exception:  # telemetry must never affect correctness
            self.dropped += 1
