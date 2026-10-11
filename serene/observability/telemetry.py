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
        # branch A: investigation / evidence / runtime trace coverage (#52).
        # Opaque ids, enums, counts and codes only; free text never passes `_TOKEN`.
        "run_id",
        "task_id",
        "investigation_id",
        "hypothesis_id",
        "hypothesis_ids",
        "request_id",
        "evidence_id",
        "phase",
        "from_phase",
        "to_phase",
        "proposal_kind",
        "admitted",
        "refused",
        "status",
        "tool",
        "action_count",
        "max_actions",
        "domain",
        "attempt",
        "retryable",
        "failure",
        "information_value",
        "acquisition_mode",
        "context_digest",
        "experience_count",
        "memory_count",
        "belief_count",
        "disagreement_count",
        "candidate_count",
        "input_tokens",
        "output_tokens",
        "cost_micro_usd",
        "cost_known",
        "update_kind",
        "checks_passed",
        "verifier_version",
        # schema location:type of rejected model replies, e.g. "experiment.category:enum"
        "validation_issues",
    }
)
_TOKEN = re.compile(r"^[A-Za-z0-9_:\-.,/]{0,256}$")
_NAME = re.compile(r"^[a-z][a-z0-9_.]{0,63}$")
# Token syntax alone is insufficient: credentials and person ids can be tokens.
_PRIVATE_TOKEN = re.compile(
    r"(?:chd_|act_|person_|parent_|caregiver_)[A-Za-z0-9_-]+"
    r"|(?:sk-|gh[pousr]_|github_pat_|AKIA|ASIA|xox[baprs]-)[A-Za-z0-9_-]{8,}"
    r"|eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_.-]+"
    r"|\d{8,10}:AA[A-Za-z0-9_-]+"
)


def safe_token(value: str) -> bool:
    """Shared lexical gate; callers must still supply codes, never private text."""
    return _TOKEN.fullmatch(value) is not None and _PRIVATE_TOKEN.search(value) is None


def safe_name(value: str) -> bool:
    return _NAME.fullmatch(value) is not None and safe_token(value)


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
        if key == "child_ref" and (
            not isinstance(value, str) or re.fullmatch(r"cref_[0-9a-f]{24}", value) is None
        ):
            continue
        if isinstance(value, bool | int) or (isinstance(value, str) and safe_token(value)):
            out[key] = value
        elif isinstance(value, tuple | list) and all(
            isinstance(v, str) and safe_token(v) for v in value
        ):
            joined = ",".join(value)
            if safe_token(joined):
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
            if not safe_name(name):
                self.dropped += 1
                return
            self._sink.emit(name, redact(attributes, pseudonym_key=self._key))
        except Exception:  # telemetry must never affect correctness
            self.dropped += 1
