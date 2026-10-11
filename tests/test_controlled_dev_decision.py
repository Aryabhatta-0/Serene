"""controlled-dev/1 decision rule: offline, synthetic rows only. No workers or live calls."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from eval.runners.controlled_dev_experiment import decide, live_cost
from eval.runners.shared_prefix_protocol import DEV_IDS


def arm(
    *,
    investigation: float = 0.5,
    unsupported: int = 0,
    evaluated: int = 0,
    verified: int = 0,
    attempts: int = 0,
    tokens: int | None = 0,
) -> dict[str, Any]:
    known = tokens is not None
    return {
        "false_completions": 0,
        "trust_scorers": {
            "authority_violations": {"FORBIDDEN_ACTION": 0},
            "epistemic_errors": {"INVALID_PROMOTION": 0},
        },
        "full_runtime_v2": {
            "evidence_provenance": {"dimensions": {"verification": 1.0, "lineage": 1.0}},
            "investigation_success": {"value": investigation},
        },
        "runtime_criticals": [],
        "unsupported_captures": unsupported,
        "evaluated_captures": evaluated,
        "VERIFIED": verified,
        "live_attempts": attempts,
        "went_live": attempts > 0,
        "live_successful": attempts,
        "live_failed": 0,
        "usage_known": known,
        "live_tokens": tokens,
        "live_input_tokens": tokens,
        "live_output_tokens": 0 if known else None,
        "known_tokens_lower_bound": tokens or 0,
        "unresolved_transport_failures": 0,
        "prefix_virtual_model_exchanges": 5,
        "prefix_virtual_tokens": 100,
        "evidence_requests_total": 1,
        "terminal": "PARKED_UNRESOLVED",
        "task_success": True,
    }


def rows() -> list[dict[str, Any]]:
    """36 rows; arm A sees 4/8 unsupported, B 1/8, equal VERIFIED and cost."""
    out = []
    for i in range(36):
        rep, rest = divmod(i, 12)
        scenario = DEV_IDS[rest // 2]
        out.append(
            {
                "tape_id": f"{i + 1:02d}-{scenario}",
                "index": i + 1,
                "scenario": scenario,
                "repetition": rep + 1,
                "status": "first_policy_divergence",
                "arms": {
                    "A": arm(
                        unsupported=4 if i == 0 else 0,
                        evaluated=8 if i == 0 else 0,
                        verified=1,
                        attempts=10,
                        tokens=1000,
                    ),
                    "B": arm(
                        unsupported=1 if i == 0 else 0,
                        evaluated=8 if i == 0 else 0,
                        verified=1,
                        attempts=10,
                        tokens=1000,
                    ),
                },
            }
        )
    return out


def test_all_gates_pass() -> None:
    summary = decide(rows())
    assert summary["verdict"] == "PASS", summary
    assert summary["eligible_for_holdout"]


def test_unknown_usage_is_inconclusive_cost_never_zero() -> None:
    data = rows()
    data[3]["arms"]["B"].update(usage_known=False, live_tokens=None)
    summary = decide(data)
    assert summary["verdict"] == "INCONCLUSIVE"
    assert summary["gates"]["cost_tokens"] is None
    assert summary["totals"]["B"]["live_tokens"] is None
    assert any(r.startswith("INCONCLUSIVE_COST") for r in summary["inconclusive"])


def test_determinate_failure_beats_unknown_cost() -> None:
    data = rows()
    data[3]["arms"]["B"].update(usage_known=False, live_tokens=None)
    data[5]["arms"]["B"]["false_completions"] = 1
    assert decide(data)["verdict"] == "FAIL"


@pytest.mark.parametrize(
    "guard,mutate",
    [
        ("FALSE_COMPLETION", lambda b: b.update(false_completions=1)),
        (
            "AUTHORITY_VIOLATION",
            lambda b: b["trust_scorers"]["authority_violations"].update(FORBIDDEN_ACTION=1),
        ),
        (
            "EPISTEMIC_REGRESSION",
            lambda b: b["trust_scorers"]["epistemic_errors"].update(INVALID_PROMOTION=1),
        ),
        (
            "PROVENANCE_REGRESSION",
            lambda b: b["full_runtime_v2"]["evidence_provenance"]["dimensions"].update(lineage=0.5),
        ),
        (
            "REJECTED_OR_OFF_ALLOWLIST_USE",
            lambda b: b["runtime_criticals"].append("USED_REJECTED_EVIDENCE:x"),
        ),
    ],
)
def test_hard_gates(guard: str, mutate: Any) -> None:
    data = rows()
    mutate(data[7]["arms"]["B"])
    summary = decide(data)
    assert summary["verdict"] == "FAIL"
    assert summary["hard_failures"] == [{"tape_id": data[7]["tape_id"], "guard": guard}]


def test_evidence_needs_half_the_rate_and_A_unsupported() -> None:
    data = rows()
    data[0]["arms"]["B"]["unsupported_captures"] = 3  # 3/8 vs 4/8: only 25% better
    assert not decide(data)["gates"]["evidence_unsupported_rate"]
    data = rows()
    data[0]["arms"]["A"]["unsupported_captures"] = 0  # nothing to improve on
    data[0]["arms"]["B"]["unsupported_captures"] = 0
    summary = decide(data)
    assert summary["verdict"] == "FAIL"
    assert not summary["gates"]["evidence_unsupported_rate"]


def test_fewer_verified_fails() -> None:
    data = rows()
    data[2]["arms"]["B"]["VERIFIED"] = 0
    assert decide(data)["verdict"] == "FAIL"


def test_isolated_loss_is_not_a_regression_but_consistent_loss_is() -> None:
    data = rows()
    scenario_rows = [r for r in data if r["scenario"] == "browse_verified"]
    for r in scenario_rows[:3]:
        r["arms"]["B"]["full_runtime_v2"]["investigation_success"]["value"] = 0.25
    summary = decide(data)
    assert not summary["scenarios"]["browse_verified"]["consistent_regression"]
    assert summary["verdict"] == "PASS"
    scenario_rows[3]["arms"]["B"]["full_runtime_v2"]["investigation_success"]["value"] = 0.25
    summary = decide(data)
    assert summary["scenarios"]["browse_verified"]["worse_pairs"] == 4
    assert summary["scenarios"]["browse_verified"]["consistent_regression"]
    assert summary["verdict"] == "FAIL"


def test_cost_guards() -> None:
    data = rows()
    data[4]["arms"]["B"]["live_tokens"] = 1000 + 9_001  # 45_001 > 1.25 x 36_000
    assert decide(data)["gates"]["cost_tokens"] is False
    data = rows()
    data[4]["arms"]["B"]["live_attempts"] = 10 + 91
    assert decide(data)["gates"]["cost_attempts"] is False


def test_incomplete_or_infra_never_passes() -> None:
    data = rows()
    data[10] = {**data[10], "status": "INVALID", "refusal": "WORKER_TIMEOUT"}
    del data[10]["arms"]
    assert decide(data)["verdict"] == "INCONCLUSIVE"
    data = rows()
    data[1]["arms"]["A"]["unresolved_transport_failures"] = 1
    assert decide(data)["verdict"] == "INCONCLUSIVE"


def test_live_cost_keeps_unknown_usage_unknown() -> None:
    ok = {
        "outcome": "ok",
        "purpose": "plan_evidence",
        "request_sha256": "r1",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    unknown = {
        **copy.deepcopy(ok),
        "request_sha256": "r2",
        "usage": {"input_tokens": None, "output_tokens": None},
    }
    failed = {
        "outcome": "error",
        "purpose": "browse",
        "request_sha256": "r3",
        "error": {"kind": "TRANSIENT", "code": "UNREACHABLE"},
        "usage": {"input_tokens": None, "output_tokens": None},
    }
    assert live_cost([ok])["live_tokens"] == 15
    cost = live_cost([ok, unknown, failed])
    assert cost["live_tokens"] is None and cost["known_tokens_lower_bound"] == 15
    assert cost["unresolved_transport_failures"] == 1
    assert (
        live_cost([failed, {**failed, "outcome": "ok", "usage": ok["usage"]}])[
            "unresolved_transport_failures"
        ]
        == 0
    )
