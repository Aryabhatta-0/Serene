"""Descriptive downstream metrics; runtime-scorers/2 remains the sole scorer.

Partial prefixes cannot earn PASS or be assigned fictional terminal scores.
"""

from __future__ import annotations

import dataclasses
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any

from eval.runners.shared_prefix_protocol import SharedPrefix, digest, require
from eval.scorers.runtime_scorers import (
    DECISIVE_OUTCOMES,
    Oracle,
    Trajectory,
    report_row,
    score_investigation,
    told_apart,
)


def unnecessary(score: Any) -> int:
    return sum(int(n.split(":")[1]) for n in score.notes if n.startswith("UNNECESSARY_QUESTIONS:"))


def downstream(
    completed: Mapping[str, Any],
    prefix: SharedPrefix,
    oracle: Oracle,
    *,
    offline_identical: bool = False,
) -> dict[str, Any]:
    divergence = prefix.divergence
    require(
        (divergence is not None or offline_identical) and completed.get("kind") == "done",
        "SUFFIX_INCOMPLETE",
    )
    cut = 0 if divergence is None else divergence["ledger_common_events"]
    events = completed["events"]
    if divergence is not None:
        require(
            digest(events[:cut]) == divergence["ledger_common_sha256"], "PREFIX_HISTORY_CHANGED"
        )
    trajectory = Trajectory.from_json(json.dumps(completed["trajectory"]))
    full = report_row(trajectory, oracle)["scores"]
    require(full == completed["scores"], "SCORER_RESULT_MISMATCH")
    before_requests = sum(e["event_type"] == "EVIDENCE_REQUESTED" for e in events[:cut])
    common_acquisitions = trajectory.acquisitions[:before_requests]
    common = dataclasses.replace(
        trajectory,
        acquisitions=common_acquisitions,
        questions=tuple(a.fields for a in common_acquisitions if a.mode == "ASK_PARENT"),
    )
    suffix = trajectory.acquisitions[before_requests:]
    # Keep prior acquisitions when counting repeats / ALREADY_TOLD_APART burden.
    common_unnecessary = unnecessary(score_investigation(common, oracle))
    suffix_unnecessary = unnecessary(score_investigation(trajectory, oracle)) - common_unnecessary
    questions = sum(a.mode == "ASK_PARENT" for a in suffix)
    modes = {
        e["payload"]["request_id"]: e["payload"]["acquisition_mode"]
        for e in events
        if e["event_type"] == "EVIDENCE_REQUESTED"
    }
    external = {
        e["payload"]["evidence"]["evidence_id"]
        for e in events
        if e["event_type"] == "EVIDENCE_ACQUIRED"
        and modes.get(e["payload"].get("request_id")) == "BROWSE"
    }
    verdicts: dict[str, str] = {}
    reasons: Counter[str] = Counter()
    unsupported: set[str] = set()
    for event in events[cut:]:
        kind, payload = event["event_type"], event["payload"]
        if kind not in {"EVIDENCE_VERIFIED", "EVIDENCE_REJECTED"}:
            continue
        if payload["evidence_id"] not in external:
            continue
        verdicts[payload["evidence_id"]] = kind
        codes = [c.split(":", 1)[0] for c in payload.get("reason_codes", [])]
        reasons.update(codes)
        if "REQUESTED_FIELD_UNSUPPORTED" in codes:
            unsupported.add(payload["evidence_id"])
    after_seq = prefix.history[-1].tape_seq if prefix.history else 0
    wire = [] if offline_identical else [r for r in completed["wire"] if r["seq"] > after_seq]
    injected = [r for r in wire if r.get("error", {}).get("code", "").startswith("INJ")]
    failures = [r["error"] for r in wire if "error" in r and r not in injected]
    criticals = [c for score in full.values() for c in score["critical"]]
    return {
        "scope": "offline-no-divergence" if offline_identical else "after-first-policy-output",
        "ledger_cut": cut,
        "prefix_sha256": prefix.history_sha256,
        "full_runtime_v2": full,
        "evidence_request_sizes": [len(a.fields) for a in suffix],
        "unsupported_captures": len(unsupported),
        "evaluated_captures": len(verdicts),
        "unsupported_capture_rate": len(unsupported) / len(verdicts) if verdicts else None,
        "verifier_rejection_reasons": dict(reasons),
        "verifier_outcomes": dict(Counter(verdicts.values())),
        "VERIFIED": sum(v == "EVIDENCE_VERIFIED" for v in verdicts.values()),
        "high_value": float(any(a.outcome in DECISIVE_OUTCOMES and told_apart(a) for a in suffix)),
        "resolution": full["investigation_success"]["dimensions"]["resolution"],
        "burden": 1 - suffix_unnecessary / questions if questions else 1.0,
        "parent_question_outcomes": dict(
            Counter(a.outcome for a in suffix if a.mode == "ASK_PARENT")
        ),
        "terminal": trajectory.terminal,
        "false_completions": sum(c.startswith("FALSE_COMPLETION") for c in criticals),
        "runtime_criticals": criticals,
        "trust_scorers": completed["trust_scorers"],
        "task_success": all(s["passed"] for s in full.values())
        and not any(completed["trust_scorers"]["epistemic_errors"].values())
        and completed["trust_scorers"]["authority_violations"] is not None
        and not any(completed["trust_scorers"]["authority_violations"].values()),
        "model_calls": sum(r["purpose"] != "browse" for r in wire),
        "transport_calls": len(wire) - len(injected),
        "input_tokens": sum(
            r.get("response", {}).get("usage", {}).get("input_tokens", 0) for r in wire
        ),
        "output_tokens": sum(
            r.get("response", {}).get("usage", {}).get("output_tokens", 0) for r in wire
        ),
        "infrastructure_failures": failures,
        "verifier_infrastructure_failures": {
            code: reasons[code]
            for code in ("SOURCE_UNREACHABLE", "VERIFIER_ERROR")
            if reasons[code]
        },
        "injected_transport_failures": len(injected),
        "prefix_virtual_model_exchanges": len(prefix.history),
        "prefix_virtual_tokens": sum(
            sum(r.get("response", {}).get("usage", {}).values())
            for r in completed["wire"]
            if r["seq"] <= after_seq
        ),
    }


def aggregate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Descriptive only. Preserve every tape/repetition; never emit an eligibility verdict."""
    require(bool(rows), "NO_COMPLETED_SUFFIXES")
    continuous = (
        "high_value",
        "resolution",
        "burden",
        "VERIFIED",
        "unsupported_captures",
        "evaluated_captures",
        "model_calls",
        "transport_calls",
        "input_tokens",
        "output_tokens",
        "false_completions",
    )
    output: dict[str, Any] = {"raw": list(rows), "n": len(rows), "significance_claims": "none"}
    output["continuous"] = {
        key: {"raw": [r[key] for r in rows], "median": median(r[key] for r in rows)}
        for key in continuous
    }
    counts = Counter(r["terminal"] for r in rows)
    output["terminal"] = {k: {"count": v, "rate": v / len(rows)} for k, v in counts.items()}
    for key in ("verifier_rejection_reasons", "verifier_outcomes", "parent_question_outcomes"):
        total: Counter[str] = Counter()
        for row in rows:
            total.update(row[key])
        output[key] = dict(total)
    fields = Counter(n for r in rows for n in r["evidence_request_sizes"])
    output["evidence_request_sizes"] = dict(fields)
    denominator = sum(r["evaluated_captures"] for r in rows)
    numerator = sum(r["unsupported_captures"] for r in rows)
    output["unsupported_capture_rate"] = {
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator if denominator else None,
        "raw": [r["unsupported_capture_rate"] for r in rows],
    }
    return output
