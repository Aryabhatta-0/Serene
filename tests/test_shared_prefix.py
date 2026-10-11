"""live-gate/3 integrity and immutable historical-result regression tests. No network."""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from eval.runners.shared_prefix_compare import (
    DEFAULT_CATALOG,
    FrozenContinuation,
    continue_pair,
    file_sha,
    load,
    validate_arms,
    write_new,
)
from eval.runners.shared_prefix_protocol import (
    PROTOCOL_VERSION,
    SCORER_VERSION,
    TRUST_VERSION,
    ContinuationJournal,
    Exchange,
    Refused,
    SharedPrefix,
    digest,
    request_key,
    sealed_tape,
    select_tapes,
    validate_versions,
)
from eval.scenarios.runtime_live import DEV
from eval.scorers.runtime_scorers import Trajectory, report_row

ARCHIVE = DEFAULT_CATALOG.parents[1] / "reports/archive/2026-10-11-pr67-dev-ab-fail"


def request(text: str) -> dict[str, str]:
    return {
        "purpose": "propose",
        "session_ref": "same-session",
        "instructions": "same prompt",
        "instructions_sha256": hashlib.sha256(b"same prompt").hexdigest(),
        "input": text,
    }


def record(text: str, seq: int = 1) -> dict[str, Any]:
    return {
        "seq": seq,
        **request_key(request(text)),
        "response": {
            "output_text": f"reply-for-{text}",
            "status": "completed",
            "model": "hermes-agent",
            "usage": {"input_tokens": 10, "output_tokens": 2},
            "latency_ms": 1,
            "tool_calls": [],
        },
    }


def boundary(text: str | None, arm: str = "A", *, divergent: bool = False) -> dict[str, Any]:
    return {
        "kind": "done" if text is None else "boundary",
        "request": None if text is None else request(text),
        "events": (
            [
                {
                    "event_type": "EVIDENCE_REQUESTED",
                    "payload": {
                        "requested_fields": ["one", "two"] if arm == "A" else ["one"],
                    },
                }
            ]
            if divergent
            else []
        ),
        "policy_selections": (
            [{"policy_version": "minimum-sufficient-data/" + ("1" if arm == "A" else "2")}]
            if divergent
            else []
        ),
    }


def divergent_prefix() -> SharedPrefix:
    prefix = SharedPrefix(sealed_tape([record("shared"), record("old", 2)], 2))
    prefix.step(boundary("shared"), boundary("shared", "B"))
    prefix.step(boundary("old", divergent=True), boundary("new", "B", divergent=True))
    return prefix


def test_identical_prefix_and_exact_first_different_input() -> None:
    prefix = SharedPrefix(sealed_tape([record("first"), record("second", 2), record("old", 3)], 3))
    deliveries = {"A": [], "B": []}
    for text in ("first", "second"):
        action = prefix.step(boundary(text), boundary(text, "B"))
        assert action["kind"] == "shared_reply"
        for arm in deliveries:
            deliveries[arm].append(copy.deepcopy(action["delivery"]))
    divergence = prefix.step(boundary("old", divergent=True), boundary("new", "B", divergent=True))
    assert deliveries["A"] == deliveries["B"]
    assert divergence["kind"] == "first_policy_divergence"
    assert divergence["next_shared_ordinal"] == 3
    assert divergence["ledger_common_events"] == 0
    assert divergence["source_tape_matches"] == ["A"]
    assert "delivery" not in divergence and len(prefix.history) == 2
    with pytest.raises(Refused, match="PREFIX_ALREADY_SEALED"):
        prefix.step(boundary("new"), boundary("new"))


@pytest.mark.parametrize("field", ["input", "instructions_sha256", "purpose", "session_ref"])
def test_recorded_reply_never_sent_to_another_input(field: str) -> None:
    exchange = Exchange.seal(record("x"))
    req = request("x")
    req[field] += "changed"
    with pytest.raises(Refused, match="TAPE_INPUT_MISMATCH"):
        exchange.deliver(req)


def test_both_requests_are_checked_before_either_reply() -> None:
    prefix = SharedPrefix((Exchange.seal(record("x")),))
    with pytest.raises(Refused, match="WITHOUT_POLICY_OUTPUT"):
        prefix.step(boundary("x"), boundary("unrelated", "B"))
    assert not prefix.history  # A never received a reply just because A matched.


def test_reply_binding_tamper_fails_closed() -> None:
    exchange = dataclasses.replace(Exchange.seal(record("x")), reply_bytes=b'{"error":{}}')
    with pytest.raises(Refused, match="REPLY_BINDING_MISMATCH"):
        exchange.deliver(request("x"))


def test_tool_arguments_preserve_original_wire_bytes() -> None:
    source = record("browse")
    source["response"]["tool_calls"] = [{"name": "browser", "arguments": '{ "url": "pinned" }'}]
    exchange = Exchange.seal(source)
    assert exchange.deliver(request("browse"))["response"] == source["response"]
    source["response"]["tool_calls"][0].pop("arguments")
    with pytest.raises(Refused, match="INCOMPLETE_TOOL_CALL"):
        Exchange.seal(source)


@pytest.mark.parametrize(
    "records,count",
    [
        ([], 1),
        ([record("x")], 2),
        ([record("x", 2)], 1),
        ([{"seq": 1, **request_key(request("x"))}], 1),
    ],
)
def test_incomplete_tape_is_refused(records: list[Any], count: int) -> None:
    with pytest.raises(Refused):
        sealed_tape(records, count)


def test_upstream_input_or_state_drift_is_not_policy_divergence() -> None:
    prefix = SharedPrefix((Exchange.seal(record("x")),))
    with pytest.raises(Refused, match="TAPE_INPUT_MISMATCH"):
        prefix.step(boundary("different"), boundary("different", "B"))
    a, b = boundary("x"), boundary("x", "B")
    b["events"] = [{"event_type": "HYPOTHESIS_PROPOSED"}]
    with pytest.raises(Refused, match="UNEXPECTED_PRE_POLICY_DIVERGENCE"):
        prefix.step(a, b)
    a, b = boundary("old", divergent=True), boundary("new", "B", divergent=True)
    a["events"][0]["event_type"] = "HYPOTHESIS_PROPOSED"
    with pytest.raises(Refused, match="UNEXPECTED_PRE_POLICY_DIVERGENCE"):
        prefix.step(a, b)
    assert not prefix.history


def test_policy_output_may_precede_the_first_different_model_input() -> None:
    prefix = SharedPrefix(
        sealed_tape([record("shared"), record("still-shared", 2), record("old", 3)], 3)
    )
    prefix.step(boundary("shared"), boundary("shared", "B"))
    action = prefix.step(
        boundary("still-shared", divergent=True), boundary("still-shared", "B", divergent=True)
    )
    assert action["kind"] == "shared_reply"  # both exact inputs still match the tape
    divergence = prefix.step(boundary("old", divergent=True), boundary("new", "B", divergent=True))
    assert divergence["next_shared_ordinal"] == 3
    assert divergence["policy_output_observed_before_ordinal"] == 2
    assert len(prefix.history) == 2


def test_a_recorded_policy_output_witness_cannot_be_rewritten() -> None:
    prefix = SharedPrefix(sealed_tape([record("same"), record("old", 2)], 2))
    prefix.step(boundary("same", divergent=True), boundary("same", "B", divergent=True))
    a, b = boundary("old", divergent=True), boundary("new", "B", divergent=True)
    b["events"][0]["payload"]["requested_fields"] = ["tampered"]
    with pytest.raises(Refused, match="POLICY_OUTPUT_HISTORY_CHANGED"):
        prefix.step(a, b)
    assert len(prefix.history) == 1


def test_terminal_vs_pending_request_and_source_exhaustion() -> None:
    prefix = SharedPrefix((Exchange.seal(record("x")),))
    prefix.step(boundary("x"), boundary("x", "B"))
    a, b = boundary("next", divergent=True), boundary(None, "B", divergent=True)
    b["events"][0] = {
        "event_type": "INVESTIGATION_PHASE_CHANGED",
        "payload": {
            "reason_codes": ["NO_ADMISSIBLE_EVIDENCE"],
            "to_phase": "PARKED_UNRESOLVED",
        },
    }
    assert prefix.step(a, b)["kind"] == "first_policy_divergence"


def test_no_divergence_requires_consuming_the_complete_tape() -> None:
    prefix = SharedPrefix((Exchange.seal(record("x")),))
    with pytest.raises(Refused, match="UNCONSUMED_TAPE"):
        prefix.step(boundary(None), boundary(None))
    prefix.step(boundary("x"), boundary("x"))
    assert prefix.step(boundary(None), boundary(None))["kind"] == "no_divergence"


def test_selection_uses_all_identities_even_if_outcomes_are_unfavorable() -> None:
    catalog = load(DEFAULT_CATALOG)
    baseline = select_tapes(catalog)
    changed = copy.deepcopy(catalog)
    for index, tape in enumerate(changed["tapes"]):
        tape["outcome"] = "FAIL" if index % 2 else "PASS"
        tape["retention"] = index % 2
    changed["tapes"].reverse()
    assert [t["tape_id"] for t in select_tapes(changed)] == [t["tape_id"] for t in baseline]
    assert len(baseline) == 36
    changed["tapes"].pop()
    with pytest.raises(Refused, match="INCOMPLETE_CATALOG"):
        select_tapes(changed)


@pytest.mark.parametrize(
    "key,code",
    [
        ("protocol_version", "PROTOCOL_MISMATCH"),
        ("scorer_version", "SCORER_MISMATCH"),
        ("trust_scorer_version", "TRUST_SCORER_MISMATCH"),
        ("oracle_sha256", "ORACLE_MISMATCH"),
    ],
)
def test_versions_must_match(key: str, code: str) -> None:
    metadata = {
        "protocol_version": PROTOCOL_VERSION,
        "scorer_version": SCORER_VERSION,
        "trust_scorer_version": TRUST_VERSION,
        "oracle_sha256": "oracle",
    }
    validate_versions(metadata, "oracle")
    metadata[key] = "different"
    with pytest.raises(Refused, match=code):
        validate_versions(metadata, "oracle")


@pytest.mark.parametrize("field", ["oracles", "runtime", "protected_sha256", "kernel_sha256"])
def test_protected_runtime_cannot_drift(field: str) -> None:
    a = {
        "protocol_version": PROTOCOL_VERSION,
        "scorer_version": SCORER_VERSION,
        "trust_scorer_version": TRUST_VERSION,
        "oracles": dict.fromkeys(DEV, "oracle"),
        "runtime": {},
        "protected_sha256": {},
        "kernel_sha256": {},
        "policy_sha256": {"p": "old"},
    }
    b = copy.deepcopy(a)
    b["policy_sha256"] = {"p": "new"}
    validate_arms({"A": a, "B": b})
    b[field][next(iter(b[field]), "changed")] = "different"
    with pytest.raises(Refused):
        validate_arms({"A": a, "B": b})


def test_continuation_cannot_rewrite_prefix_and_never_uses_tape() -> None:
    prefix = divergent_prefix()
    saved, saved_hash = prefix.history, prefix.history_sha256
    pending = {"A": boundary("old", divergent=True), "B": boundary("new", "B", divergent=True)}
    calls: list[tuple[str, str]] = []

    class FakeWorker:
        def __init__(self, arm: str) -> None:
            self.arm = arm

        def send(self, command: Any) -> None:
            assert command["delivery"]["response"]["output_text"].startswith("LIVE:")

        def receive(self) -> Any:
            return boundary(None, self.arm, divergent=True)

    def provider(req: dict[str, Any]) -> dict[str, Any]:
        arm = "A" if req["input"] == "old" else "B"
        calls.append((arm, req["input"]))
        reply = Exchange.seal(record(req["input"])).deliver(req)
        reply["response"]["output_text"] = "LIVE:" + arm
        req["input"] = "attempted provider mutation"
        return reply

    states, journal = continue_pair(
        {"A": FakeWorker("A"), "B": FakeWorker("B")},
        pending,
        prefix,
        FrozenContinuation(live_configuration(), live_configuration, provider),
    )
    assert calls == [("A", "old"), ("B", "new")]
    assert all(s["request"] is None for s in states.values())
    assert prefix.history == saved and prefix.history_sha256 == saved_hash
    assert journal.prefix == saved and journal.prefix_sha256 == saved_hash
    mutable = journal.records()
    mutable[0]["request"]["input"] = "tampered"
    assert journal.records()[0]["request"]["input"] == "old"
    view = prefix.divergence
    assert view is not None
    view["requests"]["A"]["input"] = "tampered"
    assert prefix.divergence["requests"]["A"]["input"] == "old"


def live_configuration() -> dict[str, Any]:
    return {
        "provider": "stub",
        "model": "stub-model",
        "config_sha256": "0" * 64,
        "timeout_s": 120,
        "retry_configuration": "runtime-controlled",
        "budget": {"max_model_calls": 18},
        "neatlogs_path": "committed-test-sink",
    }


def test_live_configuration_is_checked_before_every_call() -> None:
    config = live_configuration()
    calls: list[Any] = []
    provider = FrozenContinuation(config, lambda: config, lambda req: calls.append(req))
    config["model"] = "different"
    with pytest.raises(Refused, match="LIVE_CONFIGURATION_DRIFT"):
        provider.respond(request("x"))
    assert calls == []


def test_live_continuation_must_start_at_the_sealed_pending_input() -> None:
    prefix = divergent_prefix()
    provider = FrozenContinuation(
        live_configuration(),
        live_configuration,
        lambda req: pytest.fail("provider must not be called"),
    )
    pending = {"A": boundary("changed", divergent=True), "B": boundary("new", "B", divergent=True)}
    with pytest.raises(Refused, match="CONTINUATION_BOUNDARY_CHANGED"):
        continue_pair({}, pending, prefix, provider)


def test_downstream_metrics_keep_shared_burden_context_and_count_unique_captures() -> None:
    from eval.runners.shared_prefix_metrics import downstream
    from eval.scorers.runtime_scorers import Acquisition, Oracle

    common_event = {
        "event_type": "EVIDENCE_REQUESTED",
        "payload": {
            "request_id": "common",
            "acquisition_mode": "ASK_PARENT",
            "requested_fields": ["x"],
        },
    }
    prefix = SharedPrefix(sealed_tape([record("shared"), record("old", 2)], 2))
    a, b = boundary("shared"), boundary("shared", "B")
    a["events"] = b["events"] = [common_event]
    prefix.step(a, b)
    a, b = boundary("old", divergent=True), boundary("new", "B", divergent=True)
    a["events"].insert(0, common_event)
    b["events"].insert(0, common_event)
    prefix.step(a, b)
    predictions = (("h1", "YES"), ("h2", "NO"))
    first = Acquisition("ASK_PARENT", ("x",), "same?", ("h1", "h2"), predictions, "YES")
    repeat = dataclasses.replace(first)
    browse = Acquisition("BROWSE", ("y",), "", ("h1", "h2"), predictions, "VERIFIED")
    t = Trajectory(
        "serene",
        "fixture",
        questions=(("x",), ("x",)),
        acquisitions=(first, repeat, browse),
        hypotheses_retained=("true",),
        terminal="PARKED_UNRESOLVED",
        step_budget=128,
    )
    oracle = Oracle(("true",), (), "PARKED_UNRESOLVED")
    events = [
        common_event,
        {
            "event_type": "EVIDENCE_REQUESTED",
            "payload": {
                "request_id": "repeat",
                "acquisition_mode": "ASK_PARENT",
                "requested_fields": ["x"],
            },
        },
        {
            "event_type": "EVIDENCE_REQUESTED",
            "payload": {
                "request_id": "browse",
                "acquisition_mode": "BROWSE",
                "requested_fields": ["y"],
            },
        },
        {
            "event_type": "EVIDENCE_ACQUIRED",
            "payload": {"request_id": "browse", "evidence": {"evidence_id": "ev"}},
        },
        {"event_type": "EVIDENCE_VERIFIED", "payload": {"evidence_id": "ev"}},
    ]
    done = {
        "kind": "done",
        "events": events,
        "trajectory": json.loads(t.to_json()),
        "scores": report_row(t, oracle)["scores"],
        "wire": [record("shared"), record("old", 2)],
        "trust_scorers": {"authority_violations": {}, "epistemic_errors": {}},
    }
    metrics = downstream(done, prefix, oracle)
    assert metrics["burden"] == 0  # repeated common-prefix question is still unnecessary
    assert metrics["full_runtime_v2"]["investigation_success"]["dimensions"]["burden"] == 0.5
    assert metrics["high_value"] == 1 and metrics["VERIFIED"] == 1
    assert metrics["evaluated_captures"] == 1 and metrics["evidence_request_sizes"] == [1, 1]
    assert metrics["model_calls"] == 1 and metrics["input_tokens"] == 10
    assert metrics["unsupported_capture_rate"] == 0
    from eval.runners.shared_prefix_metrics import aggregate

    summary = aggregate([metrics, copy.deepcopy(metrics)])
    assert summary["continuous"]["burden"] == {"raw": [0, 0], "median": 0}
    assert summary["terminal"]["PARKED_UNRESOLVED"] == {"count": 2, "rate": 1}
    assert len(summary["raw"]) == 2
    assert "verdict" not in summary
    metrics["evaluated_captures"] = metrics["unsupported_captures"] = 0
    metrics["unsupported_capture_rate"] = None
    assert aggregate([metrics])["unsupported_capture_rate"]["rate"] is None
    done["events"][0] = {"tampered": True}
    with pytest.raises(Refused, match="PREFIX_HISTORY_CHANGED"):
        downstream(done, prefix, oracle)


def test_live_binding_refused_before_dispatch_and_before_divergence() -> None:
    with pytest.raises(Refused, match="LIVE_BEFORE_DIVERGENCE"):
        ContinuationJournal(SharedPrefix((Exchange.seal(record("x")),)))
    journal = ContinuationJournal(divergent_prefix())
    with pytest.raises(Refused, match="LIVE_INPUT_MISMATCH"):
        journal.append("A", request("new"), Exchange.seal(record("old")).deliver(request("old")))
    assert not journal.records()


def test_reports_cannot_overwrite_history(tmp_path: Path) -> None:
    target = tmp_path / "report.json"
    write_new(target, {"verdict": "FAIL"})
    with pytest.raises(FileExistsError):
        write_new(target, {"verdict": "PASS"})
    assert load(target) == {"verdict": "FAIL"}


def test_original_36_scores_are_reproducible_and_gate_remains_fail() -> None:
    for name, sha in load(ARCHIVE / "sha256.json").items():
        assert file_sha(ARCHIVE / name) == sha, name
    rows = load(ARCHIVE / "score-inputs.json")
    summary = load(ARCHIVE / "summary.json")
    assert len(rows) == len(summary["runs"]) == 36
    for row in rows:
        oracle = DEV[row["scenario"]].oracle
        assert row["oracle_sha256"] == oracle.digest()
        assert row["scorer_version"] == SCORER_VERSION
        scores = report_row(Trajectory.from_json(json.dumps(row["trajectory"])), oracle)["scores"]
        assert scores == row["scores"]
    # Reapply the original predeclared consistent-regression clause to all dimensions.
    from statistics import median

    regressions = []
    for sid in DEV:
        arms = {
            arm: sorted(
                (r for r in summary["runs"] if r["scenario"] == sid and r["arm"] == arm),
                key=lambda r: r["repetition"],
            )
            for arm in ("A", "B")
        }
        for metric in arms["A"][0]["scored_metrics"]:
            a = [r["scored_metrics"][metric] for r in arms["A"]]
            b = [r["scored_metrics"][metric] for r in arms["B"]]
            if median(b) < median(a) and sum(y < x for x, y in zip(a, b, strict=True)) >= 2:
                regressions.append((sid, metric))
    assert regressions == [
        (r["scenario"], r["metric"]) for r in summary["decision"]["consistent_scorer_regressions"]
    ]
    assert regressions  # Original rule necessarily implies FAIL, regardless of noise attribution.
    assert summary["decision"]["verdict"] == "FAIL"
    assert summary["decision"]["eligible_for_holdout"] is False
    assert load(DEFAULT_CATALOG)["historical_verdict"] == "FAIL"
    assert digest(summary["decision"])  # stable, separately checksummed original decision
