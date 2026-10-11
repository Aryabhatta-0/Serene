"""live-gate/3: strict, outcome-blind shared-prefix counterfactual primitives.

No runtime imports, network, scoring, or historical gate changes in this module.
JSON is used only to frame byte strings; model inputs are never normalized.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

PROTOCOL_VERSION: Final = "live-gate/3"
SCORER_VERSION: Final = "runtime-scorers/2"
TRUST_VERSION: Final = "trust-scorers/1"
DEV_IDS: Final = (
    "ask_discriminates",
    "browse_verified",
    "browse_unsupported_page",
    "browser_flaky_restart",
    "parent_silent",
    "planner_down",
)
POLICY_FILES: Final = (
    "serene/investigation/minimum_data.py",
    "serene/investigation/service.py",
)
PROTECTED_FILES: Final = (
    "eval/scenarios/runtime_live.py",
    "eval/scenarios/runtime_scenarios.py",
    "eval/scorers/runtime_scorers.py",
    "eval/runners/runtime_live_compare.py",
    "serene/adapters/hermes/runtime.py",
    "serene/adapters/hermes/wire.py",
    "serene/adapters/hermes/transport.py",
    "serene/adapters/browser/hermes_browser.py",
    "serene/adapters/browser/fetch.py",
    "serene/evidence/verifier.py",
    "serene/adapters/neatlogs_sink.py",
    "serene/observability/telemetry.py",
    "tests/evidence_support.py",
    "tests/investigation_support.py",
    "eval/fixtures/pages/daycare-pickup-policy.html",
    "serene/policies/scorers.py",
)


class Refused(ValueError):
    """Integrity/attribution failure; must escape runtime repair/retry handling."""


def encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def require(condition: bool, code: str) -> None:
    if not condition:
        raise Refused(code)


def request_key(request: Mapping[str, Any]) -> dict[str, str]:
    """Fields affecting model execution, including the session header.

    The legacy recorder stores the instructions' SHA rather than their text. A/B
    additionally compare actual instructions bytes before trusting that hash.
    """
    fields = ("purpose", "session_ref", "instructions_sha256", "input")
    require(all(isinstance(request.get(k), str) for k in fields), "INCOMPLETE_REQUEST")
    return {k: request[k] for k in fields}


def envelope(request: Any) -> dict[str, str]:
    return {
        "purpose": request.purpose,
        "session_ref": request.session_ref,
        "instructions": request.instructions,
        "instructions_sha256": hashlib.sha256(request.instructions.encode("utf-8")).hexdigest(),
        "input": request.input,
    }


def check_envelope(request: Mapping[str, Any]) -> None:
    require(isinstance(request.get("instructions"), str), "MISSING_INSTRUCTIONS")
    require(
        hashlib.sha256(request["instructions"].encode("utf-8")).hexdigest()
        == request_key(request)["instructions_sha256"],
        "INSTRUCTIONS_HASH_MISMATCH",
    )


@dataclass(frozen=True)
class Exchange:
    """Immutable reply bound to the exact recorded request and tape position."""

    seq: int
    request_bytes: bytes
    reply_bytes: bytes
    binding: str

    @classmethod
    def seal(cls, record: Mapping[str, Any]) -> Exchange:
        key = request_key(record)
        require(isinstance(record.get("seq"), int), "BAD_SEQUENCE")
        require(("response" in record) != ("error" in record), "INCOMPLETE_REPLY")
        reply = {k: record[k] for k in ("response", "error") if k in record}
        if "response" in reply:
            r = reply["response"]
            require(
                isinstance(r, dict)
                and all(
                    k in r
                    for k in ("output_text", "status", "model", "usage", "latency_ms", "tool_calls")
                ),
                "INCOMPLETE_REPLY",
            )
            require(
                isinstance(r["output_text"], str) and isinstance(r["tool_calls"], list), "BAD_REPLY"
            )
            require(
                isinstance(r["usage"], dict)
                and set(r["usage"]) == {"input_tokens", "output_tokens"},
                "MISSING_USAGE",
            )
            require(all(type(v) is int and v >= 0 for v in r["usage"].values()), "BAD_USAGE")
            require(isinstance(r["model"], str) and isinstance(r["status"], str), "BAD_REPLY")
            require(
                isinstance(r["latency_ms"], (int, float)) and r["latency_ms"] >= 0, "BAD_LATENCY"
            )
            require(
                all(
                    isinstance(c, dict)
                    and isinstance(c.get("name"), str)
                    and isinstance(c.get("arguments"), str)
                    for c in r["tool_calls"]
                ),
                "INCOMPLETE_TOOL_CALL",
            )
        else:
            require(
                isinstance(reply["error"], dict)
                and reply["error"].get("kind") in {"TRANSIENT", "AUTH", "PROTOCOL", "REFUSED"}
                and isinstance(reply["error"].get("code"), str),
                "BAD_ERROR",
            )
        req, body = encoded(key), encoded(reply)
        return cls(record["seq"], req, body, digest([record["seq"], key, reply]))

    def deliver(self, request: Mapping[str, Any]) -> dict[str, Any]:
        key, reply = json.loads(self.request_bytes), json.loads(self.reply_bytes)
        require(digest([self.seq, key, reply]) == self.binding, "REPLY_BINDING_MISMATCH")
        require(encoded(request_key(request)) == self.request_bytes, "TAPE_INPUT_MISMATCH")
        return {"request_sha256": digest(key), "exchange_binding": self.binding, **reply}


def sealed_tape(records: Sequence[Mapping[str, Any]], expected_count: int) -> tuple[Exchange, ...]:
    require(bool(records) and len(records) == expected_count, "INCOMPLETE_TAPE")
    require([r.get("seq") for r in records] == list(range(1, expected_count + 1)), "BAD_SEQUENCE")
    all_entries = tuple(Exchange.seal(r) for r in records)
    # Scenario faults are re-injected by the unchanged runtime harness, never supplied twice.
    return tuple(
        e
        for e in all_entries
        if not json.loads(e.reply_bytes).get("error", {}).get("code", "").startswith("INJ")
    )


def select_tapes(catalog: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Fixed subset by experiment/run identity only; no scores enter selection."""
    require(catalog.get("protocol_version") == PROTOCOL_VERSION, "PROTOCOL_MISMATCH")
    require(catalog.get("experiment") == "pr67-ab-20261011", "CATALOG_EXPERIMENT")
    tapes = sorted(catalog["tapes"], key=lambda t: (t["index"], t["tape_id"]))
    expected = [(rep, sid, arm) for rep in (1, 2, 3) for sid in DEV_IDS for arm in ("A", "B")]
    require(len(tapes) == len(expected), "INCOMPLETE_CATALOG")
    require(len({t["tape_id"] for t in tapes}) == len(tapes), "DUPLICATE_TAPE")
    for index, (tape, (rep, sid, arm)) in enumerate(zip(tapes, expected, strict=True), 1):
        require(
            (tape["index"], tape["repetition"], tape["scenario"], tape["source_arm"])
            == (index, rep, sid, arm),
            "CATALOG_ORDER",
        )
    return tuple(dict(t) for t in tapes)


def validate_versions(metadata: Mapping[str, Any], oracle: str) -> None:
    require(metadata.get("protocol_version") == PROTOCOL_VERSION, "PROTOCOL_MISMATCH")
    require(metadata.get("scorer_version") == SCORER_VERSION, "SCORER_MISMATCH")
    require(metadata.get("trust_scorer_version") == TRUST_VERSION, "TRUST_SCORER_MISMATCH")
    require(bool(oracle) and metadata.get("oracle_sha256") == oracle, "ORACLE_MISMATCH")


def first_event_difference(a: Sequence[Any], b: Sequence[Any]) -> int | None:
    for index, (x, y) in enumerate(zip(a, b, strict=False)):
        if encoded(x) != encoded(y):
            return index
    return min(len(a), len(b)) if len(a) != len(b) else None


def causal_witness(a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, Any]:
    """Narrow attribution: common ledger until a permitted policy output event.

    Protected source identity and the product-diff allowlist are checked at freeze.
    Merely seeing two different model inputs is NOT evidence of policy causality.
    """
    ae, be = a["events"], b["events"]
    index = first_event_difference(ae, be)
    require(index is not None, "INPUT_DIVERGENCE_WITHOUT_POLICY_OUTPUT")
    left = ae[index] if index < len(ae) else None
    right = be[index] if index < len(be) else None
    allowed = {"EVIDENCE_REQUESTED", "INVESTIGATION_PHASE_CHANGED"}
    require(
        all(e is not None and e["event_type"] in allowed for e in (left, right)),
        "UNEXPECTED_PRE_POLICY_DIVERGENCE",
    )
    ap, bp = a.get("policy_selections", []), b.get("policy_selections", [])
    require(bool(ap) and bool(bp) and len(ap) == len(bp), "MISSING_POLICY_WITNESS")
    require(
        ap[-1].get("policy_version") == "minimum-sufficient-data/1"
        and bp[-1].get("policy_version") == "minimum-sufficient-data/2",
        "POLICY_VERSION",
    )
    if left["event_type"] == right["event_type"] == "EVIDENCE_REQUESTED":
        # The candidate has already been evaluated. Its admitted request is the output.
        require(left["payload"] != right["payload"], "NO_POLICY_OUTPUT_CHANGE")
    else:
        reasons = set(left["payload"].get("reason_codes", [])) | set(
            right["payload"].get("reason_codes", [])
        )
        require("NO_ADMISSIBLE_EVIDENCE" in reasons, "UNEXPECTED_PHASE_DIVERGENCE")
    return {
        "ledger_common_events": index,
        "ledger_common_sha256": digest(ae[:index]),
        "first_policy_outputs": {"A": left, "B": right},
        "policy_selections": {"A": ap[-1], "B": bp[-1]},
    }


@dataclass(frozen=True)
class PrefixEntry:
    ordinal: int
    tape_seq: int
    request_sha256: str
    exchange_binding: str
    chain_sha256: str


class SharedPrefix:
    """Lockstep barrier. Validate BOTH requests before releasing EITHER reply."""

    def __init__(self, tape: tuple[Exchange, ...]) -> None:
        self._tape = tape
        self._history: tuple[PrefixEntry, ...] = ()
        self._divergence: bytes | None = None
        self._policy_witness: bytes | None = None

    @property
    def history(self) -> tuple[PrefixEntry, ...]:
        return self._history

    @property
    def history_sha256(self) -> str:
        return self._history[-1].chain_sha256 if self._history else digest([])

    @property
    def divergence(self) -> dict[str, Any] | None:
        return None if self._divergence is None else json.loads(self._divergence)

    def step(self, a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, Any]:
        require(self._divergence is None, "PREFIX_ALREADY_SEALED")
        ar, br = a.get("request"), b.get("request")
        for request in (ar, br):
            if request is not None:
                check_envelope(request)
        state_difference = first_event_difference(a["events"], b["events"])
        if state_difference is not None and self._policy_witness is None:
            self._policy_witness = encoded(
                {
                    **causal_witness(a, b),
                    "policy_output_observed_before_ordinal": len(self._history) + 1,
                }
            )
        if self._policy_witness is not None:
            witness = json.loads(self._policy_witness)
            cut = witness["ledger_common_events"]
            require(state_difference == cut, "POLICY_OUTPUT_HISTORY_CHANGED")
            for arm, state in (("A", a), ("B", b)):
                require(
                    digest(state["events"][:cut]) == witness["ledger_common_sha256"]
                    and encoded(state["events"][cut])
                    == encoded(witness["first_policy_outputs"][arm]),
                    "POLICY_OUTPUT_HISTORY_CHANGED",
                )
        same = ar is not None and br is not None and encoded(ar) == encoded(br)
        if same:
            require(len(self._history) < len(self._tape), "TAPE_EXHAUSTED")
            exchange = self._tape[len(self._history)]
            delivery = exchange.deliver(ar)  # check tape binding BEFORE releasing either arm
            prior = self.history_sha256
            item = PrefixEntry(
                len(self._history) + 1,
                exchange.seq,
                delivery["request_sha256"],
                exchange.binding,
                digest([prior, exchange.binding, delivery["request_sha256"]]),
            )
            self._history += (item,)
            return {"kind": "shared_reply", "delivery": delivery}
        if ar is None and br is None and encoded(a["events"]) == encoded(b["events"]):
            require(len(self._history) == len(self._tape), "UNCONSUMED_TAPE")
            return {"kind": "no_divergence"}
        require(self._policy_witness is not None, "INPUT_DIVERGENCE_WITHOUT_POLICY_OUTPUT")
        witness = json.loads(self._policy_witness)
        # One source arm must still match its original tape. Otherwise this is drift,
        # not permission to recycle a convenient reply onto two unrelated inputs.
        remaining = len(self._history) < len(self._tape)
        next_entry = self._tape[len(self._history)] if remaining else None
        matches = [
            arm
            for arm, req in (("A", ar), ("B", br))
            if req is not None
            and next_entry is not None
            and encoded(request_key(req)) == next_entry.request_bytes
        ]
        require(
            bool(matches) or (not remaining and (ar is None or br is None)),
            "DIVERGENCE_NOT_ON_SOURCE_TAPE",
        )
        self._divergence = encoded(
            {
                "kind": "first_policy_divergence",
                "next_shared_ordinal": len(self._history) + 1,
                "prefix_sha256": self.history_sha256,
                "requests": {"A": ar, "B": br},
                "source_tape_matches": matches,
                "model_input_diverged": ar is not None or br is not None,
                **witness,
            }
        )
        return self.divergence  # no delivery at or after this boundary


class ContinuationJournal:
    """Append-only downstream records; sealed prefix never enters a live provider."""

    def __init__(self, prefix: SharedPrefix) -> None:
        require(prefix.divergence is not None, "LIVE_BEFORE_DIVERGENCE")
        self._prefix = prefix.history
        self._prefix_sha256 = prefix.history_sha256
        self._records: tuple[bytes, ...] = ()

    @property
    def prefix(self) -> tuple[PrefixEntry, ...]:
        return self._prefix

    @property
    def prefix_sha256(self) -> str:
        return self._prefix_sha256

    def append(self, arm: str, request: Mapping[str, Any], delivery: Mapping[str, Any]) -> None:
        check_envelope(request)
        require(arm in {"A", "B"}, "UNKNOWN_ARM")
        require(
            delivery.get("request_sha256") == digest(request_key(request)), "LIVE_INPUT_MISMATCH"
        )
        require(("response" in delivery) != ("error" in delivery), "INCOMPLETE_LIVE_REPLY")
        self._records += (
            encoded(
                {
                    "arm": arm,
                    "request": request,
                    "delivery": delivery,
                    "prefix_sha256": self.prefix_sha256,
                }
            ),
        )

    def records(self) -> list[dict[str, Any]]:
        return [json.loads(r) for r in self._records]
