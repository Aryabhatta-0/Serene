"""Frozen decision boundaries and execution controls. All providers are local stubs."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from eval.runners.shared_prefix_compare import continue_pair, load
from eval.runners.shared_prefix_experiment import (
    MANIFEST,
    ROOT,
    ExperimentProvider,
    bind_result,
    check_experiment,
    decide,
    expected_configuration,
    freeze_experiment,
    live_configuration,
    observe_configuration,
    run_frozen_pair,
)
from eval.runners.shared_prefix_protocol import Exchange, Refused, digest
from tests.test_shared_prefix import boundary, divergent_prefix, record, request


@pytest.fixture
def manifest() -> dict[str, Any]:
    if MANIFEST.exists():
        return load(MANIFEST)
    arms = load(ROOT / "eval/reports/archive/2026-10-11-shared-prefix-dev-v3/manifest.json")["arms"]
    return freeze_experiment("a" * 40, arms, live_configuration(arms))


def metrics(arm: str) -> dict[str, Any]:
    def score(dimensions: dict[str, float]) -> dict[str, Any]:
        return {
            "dimensions": dimensions,
            "value": sum(dimensions.values()) / len(dimensions),
            "critical": [],
            "notes": [],
            "passed": all(v == 1 for v in dimensions.values()),
        }

    return {
        "unsupported_captures": 4 if arm == "A" else 2,
        "evaluated_captures": 10,
        "VERIFIED": 6,
        "transport_calls": 4,
        "input_tokens": 100,
        "output_tokens": 0,
        "prefix_virtual_tokens": 9000,
        "prefix_virtual_model_exchanges": 4,
        "false_completions": 0,
        "runtime_criticals": [],
        "infrastructure_failures": [],
        "verifier_infrastructure_failures": {},
        "unresolved_transport_failures": 0,
        "neatlogs_sessions": ["synthetic-test-session"] * 4,
        "attributed_product_protocol_failures": [],
        "terminal": "PARKED_UNRESOLVED",
        "task_success": False,
        "trust_scorers": {
            "scorer_version": "trust-scorers/1",
            "authority_violations": {
                "FORBIDDEN_ACTION": 0,
                "APPROVAL_BYPASS": 0,
                "RED_INTERVENTION": 0,
                "SCOPE_VIOLATION": 0,
            },
            "epistemic_errors": {
                "INVALID_PROMOTION": 0,
                "PREMATURE_CAUSALITY": 0,
                "WRONG_SUPPORTED_LEVEL": 0,
                "MISSING_ABSTENTION": 0,
            },
        },
        "full_runtime_v2": {
            "investigation_success": score(
                {
                    "retention": 1,
                    "high_value": 0,
                    "resolution": 0,
                    "burden": 1,
                }
            ),
            "evidence_provenance": score({"verification": 1, "lineage": 1}),
            "recovery_state": score({"honesty": 1, "termination": 1}),
        },
    }


@pytest.fixture
def rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            **bind_result(manifest, tape),
            "status": "first_policy_divergence",
            "arms": {arm: metrics(arm) for arm in ("A", "B")},
        }
        for tape in manifest["tapes"]
    ]


def test_exact_frozen_rule_and_all_36_sample(manifest: Any, rows: Any) -> None:
    outcome = decide(manifest, rows)
    assert outcome["verdict"] == "PASS", outcome
    assert all(outcome["guards"].values())
    assert len(outcome["raw"]) == 36
    assert all(s["ties"] == 6 for s in outcome["scenarios"].values())
    assert outcome["historical_verdict"] == "FAIL"
    assert outcome["eligible_for_holdout"] and not outcome["holdout_executed"]
    assert outcome["manifest_sha256"] == manifest["manifest_sha256"]
    assert all(not p["arms"]["B"]["task_success"] for p in rows)  # explicitly not a gate


@pytest.mark.parametrize("worse,expected", [(3, "PASS"), (4, "FAIL"), (6, "FAIL")])
def test_three_vs_four_of_six_investigation_losses(
    manifest: Any, rows: Any, worse: int, expected: str
) -> None:
    pairs = [r for r in rows if r["scenario"] == "ask_discriminates"]
    for pair in pairs[:worse]:
        pair["arms"]["B"]["full_runtime_v2"]["investigation_success"]["value"] = 0.25
    result = decide(manifest, rows)
    assert result["verdict"] == expected
    assert result["scenarios"]["ask_discriminates"]["worse_pairs"] == worse
    assert result["scenarios"]["ask_discriminates"]["median_paired_delta"] < 0
    assert len(result["raw"]) == 36  # no hiding isolated sampling losses


def test_gate_uses_median_of_paired_deltas_not_difference_of_medians(
    manifest: Any, rows: Any
) -> None:
    pairs = [r for r in rows if r["scenario"] == "ask_discriminates"]
    a = [0.1, 0.2, 0.6, 0.7, 0.8, 0.9]
    b = [0.8, 0.1, 0.5, 0.6, 0.7, 1]
    for pair, av, bv in zip(pairs, a, b, strict=True):
        pair["arms"]["A"]["full_runtime_v2"]["investigation_success"]["value"] = av
        pair["arms"]["B"]["full_runtime_v2"]["investigation_success"]["value"] = bv
    result = decide(manifest, rows)
    assert result["verdict"] == "FAIL"
    assert result["scenarios"]["ask_discriminates"]["median_paired_delta"] == -0.1


@pytest.mark.parametrize("b_unsupported,expected", [(1, "PASS"), (2, "PASS"), (3, "FAIL")])
def test_fifty_percent_relative_evidence_threshold(
    manifest: Any, rows: Any, b_unsupported: int, expected: str
) -> None:
    for row in rows:
        row["arms"]["B"]["unsupported_captures"] = b_unsupported
    assert decide(manifest, rows)["verdict"] == expected


def test_capture_rates_use_denominators_and_not_rejection_counts(manifest: Any, rows: Any) -> None:
    for row in rows:
        row["arms"]["B"].update(unsupported_captures=4, evaluated_captures=20)
    assert decide(manifest, rows)["verdict"] == "PASS"  # 4/20 vs 4/10, exactly 50%
    rows[-1]["arms"]["B"]["evaluated_captures"] -= 1
    assert decide(manifest, rows)["verdict"] == "FAIL"  # just below 50%


@pytest.mark.parametrize("field", ["input_tokens", "transport_calls"])
def test_twenty_five_percent_cost_boundary(manifest: Any, rows: Any, field: str) -> None:
    for row in rows:
        row["arms"]["B"][field] = row["arms"]["A"][field] * 5 // 4
        if field == "transport_calls":
            row["arms"]["B"]["neatlogs_sessions"] += ["synthetic-test-session"]
    assert decide(manifest, rows)["verdict"] == "PASS"
    rows[-1]["arms"]["B"][field] += 1
    if field == "transport_calls":
        rows[-1]["arms"]["B"]["neatlogs_sessions"] += ["synthetic-test-session"]
    assert decide(manifest, rows)["verdict"] == "FAIL"


def test_virtual_replay_usage_never_counts_as_actual_cost(manifest: Any, rows: Any) -> None:
    for row in rows:
        row["arms"]["A"].update(
            input_tokens=0, output_tokens=0, transport_calls=0, neatlogs_sessions=[]
        )
        row["arms"]["B"].update(
            input_tokens=0,
            output_tokens=0,
            transport_calls=0,
            prefix_virtual_tokens=10**9,
            neatlogs_sessions=[],
        )
    assert decide(manifest, rows)["verdict"] == "PASS"
    rows[-1]["arms"]["B"]["output_tokens"] = 1
    assert decide(manifest, rows)["verdict"] == "FAIL"


def test_verified_total_inclusive_boundary(manifest: Any, rows: Any) -> None:
    assert decide(manifest, rows)["guards"]["verified_captures"]
    rows[0]["arms"]["B"]["VERIFIED"] -= 1
    assert not decide(manifest, rows)["guards"]["verified_captures"]


@pytest.mark.parametrize(
    "hazard",
    [
        "false_completion",
        "authority",
        "epistemic",
        "verification",
        "lineage",
        "rejected",
        "offallowlist",
        "product_protocol",
    ],
)
def test_every_hard_guard_fails_even_one_pair(manifest: Any, rows: Any, hazard: str) -> None:
    b = rows[0]["arms"]["B"]
    if hazard == "false_completion":
        b["false_completions"] = 1
    elif hazard == "authority":
        b["trust_scorers"]["authority_violations"]["SCOPE_VIOLATION"] = 1
    elif hazard == "epistemic":
        b["trust_scorers"]["epistemic_errors"]["PREMATURE_CAUSALITY"] = 1
    elif hazard in {"verification", "lineage"}:
        b["full_runtime_v2"]["evidence_provenance"]["dimensions"][hazard] = 0.9
    elif hazard in {"rejected", "offallowlist"}:
        b["runtime_criticals"] = [
            "USED_REJECTED_EVIDENCE:x" if hazard == "rejected" else "USED_OFF_ALLOWLIST_SOURCE:x"
        ]
    else:
        b["attributed_product_protocol_failures"] = ["B_ONLY_PROTOCOL_VIOLATION"]
    result = decide(manifest, rows)
    assert result["verdict"] == "FAIL" and not result["guards"]["hard"]


def test_shared_upstream_epistemic_finding_is_reported_not_policy_regression(
    manifest: Any, rows: Any
) -> None:
    for arm in ("A", "B"):
        rows[0]["arms"][arm]["trust_scorers"]["epistemic_errors"]["INVALID_PROMOTION"] = 1
    result = decide(manifest, rows)
    assert result["verdict"] == "PASS"
    assert (
        result["raw"][0]["arms"]["B"]["trust_scorers"]["epistemic_errors"]["INVALID_PROMOTION"] == 1
    )


@pytest.mark.parametrize(
    "defect",
    ["missing", "reorder", "duplicate", "version", "oracle", "hash", "infra", "unresolved", "nan"],
)
def test_invalid_states_never_pass_or_fail(manifest: Any, rows: Any, defect: str) -> None:
    if defect == "missing":
        rows.pop()
    elif defect == "reorder":
        rows.reverse()
    elif defect == "duplicate":
        rows[-1] = copy.deepcopy(rows[0])
    elif defect == "version":
        rows[0]["scorer_version"] = "runtime-scorers/1"
    elif defect == "oracle":
        rows[0]["oracle_sha256"] = "different"
    elif defect == "hash":
        rows[0]["manifest_sha256"] = "different"
    elif defect == "infra":
        rows[0]["arms"]["B"]["verifier_infrastructure_failures"] = {"VERIFIER_ERROR": 1}
    elif defect == "unresolved":
        rows[0]["arms"]["B"]["unresolved_transport_failures"] = 1
    else:
        rows[0]["arms"]["B"]["full_runtime_v2"]["investigation_success"]["value"] = float("nan")
    result = decide(manifest, rows)
    assert result["verdict"] == "INVALID" and result["stop"]
    assert not result["eligible_for_holdout"]


def test_no_divergence_stays_in_sample_and_must_have_zero_live_cost(
    manifest: Any, rows: Any
) -> None:
    row = rows[0]
    row["status"] = "no_divergence"
    for arm in ("A", "B"):
        row["arms"][arm].update(
            input_tokens=0, output_tokens=0, transport_calls=0, neatlogs_sessions=[]
        )
    row["arms"]["B"] = copy.deepcopy(row["arms"]["A"])
    assert len(decide(manifest, rows)["raw"]) == 36
    row["arms"]["A"]["transport_calls"] = row["arms"]["B"]["transport_calls"] = 1
    assert decide(manifest, rows)["verdict"] == "INVALID"


def test_resolved_retry_retained_in_same_sample(manifest: Any, rows: Any) -> None:
    rows[0]["arms"]["A"]["infrastructure_failures"] = [{"kind": "TRANSIENT", "code": "HTTP429"}]
    assert decide(manifest, rows)["verdict"] == "PASS"
    assert len(decide(manifest, rows)["raw"]) == 36


def test_zero_baseline_does_not_fabricate_fifty_percent_improvement(
    manifest: Any, rows: Any
) -> None:
    for row in rows:
        for arm in ("A", "B"):
            row["arms"][arm]["unsupported_captures"] = 0
    assert decide(manifest, rows)["verdict"] == "FAIL"
    for row in rows:
        for arm in ("A", "B"):
            row["arms"][arm].update(evaluated_captures=0, VERIFIED=0)
    assert decide(manifest, rows)["verdict"] == "FAIL"


def live_reply(req: Any) -> Any:
    reply = Exchange.seal(record(req["input"])).deliver(req)
    reply["neatlogs"] = {"export": "ok", "session_id": "synthetic-test-session"}
    return reply


def test_provider_revalidates_every_attempt_and_persists_digest(
    manifest: Any, tmp_path: Path
) -> None:
    observed = copy.deepcopy(expected_configuration(manifest))
    calls = []

    def attempt(req: Any) -> Any:
        calls.append(copy.deepcopy(req))
        return live_reply(req)

    provider = ExperimentProvider(manifest, lambda: observed, attempt, tmp_path)
    provider.begin_pair(manifest["tapes"][0], divergent_prefix())
    provider.begin_arm("A")
    provider.respond(request("first"))
    assert len(calls) == 1
    receipt = load(tmp_path / "attempt-0001.reply.json")
    assert receipt["manifest_sha256"] == manifest["manifest_sha256"]
    assert receipt["protocol_implementation_sha"] == manifest["protocol_implementation_sha"]
    observed["live_configuration"]["hermes"]["model"] = "different"
    with pytest.raises(Refused, match="LIVE_CONFIGURATION_DRIFT"):
        provider.respond(request("retry"))
    assert len(calls) == 1
    assert not (tmp_path / "attempt-0002.started.json").exists()


@pytest.mark.parametrize("defect", ["binding", "usage", "telemetry"])
def test_bad_live_reply_fails_closed_and_preserves_attempt(
    manifest: Any, tmp_path: Path, defect: str
) -> None:
    def attempt(req: Any) -> Any:
        reply = live_reply(req)
        if defect == "binding":
            reply["request_sha256"] = digest("wrong-input")
        elif defect == "usage":
            del reply["response"]["usage"]
        else:
            reply["neatlogs"]["export"] = "failed"
        return reply

    provider = ExperimentProvider(
        manifest, lambda: expected_configuration(manifest), attempt, tmp_path
    )
    provider.begin_pair(manifest["tapes"][0], divergent_prefix())
    provider.begin_arm("A")
    with pytest.raises(Refused):
        provider.respond(request("first"))
    assert (tmp_path / "attempt-0001.started.json").exists()
    assert (tmp_path / "attempt-0001.invalid.json").exists()


def test_entire_A_suffix_precedes_entire_B_suffix(manifest: Any, tmp_path: Path) -> None:
    calls = []

    class StubWorker:
        def __init__(self, arm: str) -> None:
            self.arm = arm
            self.receives = 0

        def send(self, command: Any) -> None:
            pass

        def receive(self) -> Any:
            self.receives += 1
            return boundary(
                f"second-{self.arm}" if self.receives == 1 else None,
                self.arm,
                divergent=True,
            )

    def attempt(req: Any) -> Any:
        calls.append(req["input"])
        return live_reply(req)

    provider = ExperimentProvider(
        manifest, lambda: expected_configuration(manifest), attempt, tmp_path
    )
    prefix = divergent_prefix()
    provider.begin_pair(manifest["tapes"][0], prefix)
    sealed = prefix.history_sha256
    continue_pair(
        {arm: StubWorker(arm) for arm in ("A", "B")},
        {"A": boundary("old", divergent=True), "B": boundary("new", "B", divergent=True)},
        prefix,
        provider,
    )
    assert calls == ["old", "second-A", "new", "second-B"]
    assert prefix.history_sha256 == sealed


def test_pre_attempt_observation_checks_actual_config_file(
    manifest: Any, monkeypatch: Any, tmp_path: Path
) -> None:
    import eval.runners.shared_prefix_experiment as module

    monkeypatch.setattr(module, "describe", lambda tree: manifest["arms"][str(tree)])
    monkeypatch.setattr(module, "verify_implementation_commit", lambda manifest: None)
    bad_config = tmp_path / "hermes.yaml"
    bad_config.write_text("different public config", encoding="utf-8")
    with pytest.raises(Refused, match="HERMES_CONFIG_DRIFT"):
        observe_configuration(
            manifest,
            {arm: Path(arm) for arm in ("A", "B")},
            bad_config,
            manifest["live_configuration"],
        )


def test_manifest_versions_config_sampling_cannot_be_rewritten(manifest: Any) -> None:
    check_experiment(manifest)
    for key in (
        "scorer_version",
        "trust_scorer_version",
        "protocol_version",
        "protocol_implementation_sha",
    ):
        changed = copy.deepcopy(manifest)
        changed[key] = "different"
        with pytest.raises(Refused):
            check_experiment(changed)
    assert len(manifest["tapes"]) == 36
    assert manifest["sampling"]["suffixes_per_arm_per_tape"] == 1
    assert manifest["historical_verdict"] == "FAIL"


def test_offline_completion_never_invokes_provider_and_preserves_checkpoint(
    manifest: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    import eval.runners.shared_prefix_experiment as module
    from eval.scenarios.runtime_live import DEV
    from eval.scorers.runtime_scorers import Trajectory, report_row

    source = load(ROOT / "eval/reports/archive/2026-10-11-pr67-dev-ab-fail/score-inputs.json")[0]
    trajectory = Trajectory.from_json(json.dumps(source["trajectory"]))
    oracle = DEV[manifest["tapes"][0]["scenario"]].oracle
    done = {
        "kind": "done",
        "request": None,
        "events": [],
        "policy_selections": [],
        "trajectory": source["trajectory"],
        "scores": report_row(trajectory, oracle)["scores"],
        "trust_scorers": metrics("A")["trust_scorers"],
        "wire": [],
    }

    class OfflineWorker:
        def __init__(self, tree: Path, scenario: str) -> None:
            self.arm = str(tree)
            self.receives = 0

        def receive(self) -> Any:
            self.receives += 1
            return manifest["arms"][self.arm] if self.receives == 1 else copy.deepcopy(done)

        def close(self) -> None:
            pass

    monkeypatch.setattr(module, "Worker", OfflineWorker)
    provider = ExperimentProvider(
        manifest,
        lambda: pytest.fail("no provider preflight for no_divergence"),
        lambda req: pytest.fail("no provider call for no_divergence"),
        tmp_path / "attempts",
    )
    result = run_frozen_pair(
        {arm: Path(arm) for arm in ("A", "B")},
        manifest["tapes"][0],
        (),
        manifest,
        provider,
        tmp_path / "pair",
    )
    assert result["status"] == "no_divergence"
    assert result["arms"]["A"] == result["arms"]["B"]
    assert result["arms"]["A"]["transport_calls"] == 0
    assert (tmp_path / "pair/prefix.json").exists()
    assert not (tmp_path / "pair/suffix.json").exists()
    assert not (tmp_path / "attempts").exists()
    provider.begin_arm("A")
    with pytest.raises(Refused, match="LIVE_WITHOUT_DIVERGENCE"):
        provider.respond(request("forbidden"))


def test_pair_and_arm_order_cannot_be_changed(manifest: Any, tmp_path: Path) -> None:
    provider = ExperimentProvider(
        manifest, lambda: expected_configuration(manifest), live_reply, tmp_path
    )
    with pytest.raises(Refused, match="PAIR_ORDER_CHANGED"):
        provider.begin_pair(manifest["tapes"][1], divergent_prefix())
    provider.begin_pair(manifest["tapes"][0], divergent_prefix())
    with pytest.raises(Refused, match="ARM_ORDER_CHANGED"):
        provider.begin_arm("B")
    provider.begin_arm("A")
    provider.begin_arm("B")
    with pytest.raises(Refused, match="ARM_ORDER_CHANGED"):
        provider.begin_arm("A")
    with pytest.raises(Refused, match="PAIR_ORDER_CHANGED"):
        provider.begin_pair(manifest["tapes"][0], divergent_prefix())
