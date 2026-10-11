"""Frozen regression gate (#51): an improvement passes only when nothing regresses."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from eval.runners.regression_gate import Objective, evaluate, main, snapshot

TARGET = Objective.parse("verifier_rejections.REQUESTED_FIELD_UNSUPPORTED:decrease")
GUARD = Objective.parse("verified_external:increase")


def _row(
    scenario: str,
    split: str = "dev",
    *,
    investigation: float = 0.5,
    provenance: float = 1.0,
    critical: tuple[str, ...] = (),
    authority: int | None = 0,
    epistemic: dict[str, int] | None = None,
    unsupported: int = 0,
    verified: int = 0,
    scorer: str | None = "runtime-scorers/2",
    trust_scorer: str | None = "trust-scorers/1",
    oracle: str | None = "0" * 64,
) -> dict[str, Any]:
    def score(value: float, crit: tuple[str, ...] = ()) -> dict[str, Any]:
        return {"value": value, "passed": value >= 1.0 and not crit, "critical": list(crit)}

    return {
        "system": "serene",
        "scenario": scenario,
        "split": split,
        "scorer_version": scorer,
        "oracle_sha256": oracle,
        "scores": {
            "evidence_provenance": score(provenance),
            "investigation_success": score(investigation),
            "recovery_state": score(1.0, critical),
        },
        "trust_scorers": {
            "authority_violations": None if authority is None else {"APPROVAL_BYPASS": authority},
            "epistemic_errors": epistemic or {"INVALID_PROMOTION": 0, "PREMATURE_CAUSALITY": 0},
            "scorer_version": trust_scorer,
        },
        "terminal": "PARKED_UNRESOLVED",
        "budget": {"model_calls": 10},
        "live": {"input_tokens": 100, "output_tokens": 10},
        "serene": {
            "evidence_requests": [{"mode": "BROWSE", "fields": 1}],
            "verifier_rejections": {"REQUESTED_FIELD_UNSUPPORTED": unsupported},
            "verified_external": verified,
            "question_outcomes": {"UNSURE": 1},
        },
        "source": "test",
    }


def _runs(*rows: dict[str, Any]) -> dict[str, Any]:
    return snapshot(list(rows))


BEFORE = _runs(
    _row("a", unsupported=3),
    _row("b", unsupported=2),
    _row("h1", "holdout"),
    _row("h2", "holdout"),
)


def _improved(**overrides: Any) -> dict[str, Any]:
    rows = {
        "a": _row("a", unsupported=0, verified=1),
        "b": _row("b", unsupported=1),
        "h1": _row("h1", "holdout"),
        "h2": _row("h2", "holdout"),
    }
    rows.update(overrides)
    return _runs(*rows.values())


def test_an_improvement_with_no_regression_passes() -> None:
    result = evaluate(BEFORE, _improved(), TARGET, [GUARD])
    assert result.passed, result.violations
    assert result.target == {
        "objective": str(TARGET),
        "before": 5.0,
        "after": 1.0,
        "met": True,
    }


def test_no_target_improvement_is_not_accepted() -> None:
    result = evaluate(BEFORE, BEFORE, TARGET)
    assert [rule for rule, _ in result.violations] == ["TARGET"]


@pytest.mark.parametrize(
    ("override", "rule"),
    [
        ({"h1": _row("h1", "holdout", investigation=0.25)}, "HOLDOUT"),
        ({"b": _row("b", unsupported=0, investigation=0.25)}, "DEV"),
        ({"a": _row("a", provenance=0.5)}, "PROVENANCE"),
        ({"a": _row("a", critical=("FALSE_COMPLETION",))}, "SAFETY"),
        ({"h2": _row("h2", "holdout", authority=1)}, "SAFETY"),
        ({"h2": _row("h2", "holdout", authority=None)}, "SAFETY"),
        ({"a": _row("a", epistemic={"INVALID_PROMOTION": 1})}, "EPISTEMIC"),
        ({"a": _row("a", epistemic={"PREMATURE_CAUSALITY": 1})}, "EPISTEMIC"),
    ],
)
def test_any_regression_blocks_an_otherwise_improving_change(
    override: dict[str, dict[str, Any]], rule: str
) -> None:
    result = evaluate(BEFORE, _improved(**override), TARGET, [GUARD])
    assert not result.passed
    assert rule in {r for r, _ in result.violations}


@pytest.mark.parametrize(
    "after",
    [
        # every after-run rescored under another runtime scorer
        {
            k: _row(k.split("/")[1], k.split("/")[0], scorer="runtime-scorers/1")
            for k in ("dev/a", "dev/b", "holdout/h1", "holdout/h2")
        },
        # one after-run scored by another trust scorer
        {"h1": _row("h1", "holdout", trust_scorer="trust-scorers/0")},
        # a run whose scorer version is unknown
        {"a": _row("a", scorer=None)},
    ],
)
def test_a_scorer_change_never_passes_as_a_behaviour_change(after: dict[str, Any]) -> None:
    rows = {k.split("/")[-1]: v for k, v in after.items()}
    result = evaluate(BEFORE, _improved(**rows), TARGET, [GUARD])
    assert "SCORER" in {rule for rule, _ in result.violations}


@pytest.mark.parametrize("oracle", ["1" * 64, None])
def test_an_edited_oracle_never_passes_as_a_behaviour_change(oracle: str | None) -> None:
    result = evaluate(BEFORE, _improved(a=_row("a", oracle=oracle)), TARGET, [GUARD])
    assert [rule for rule, _ in result.violations] == ["ORACLE"]


def test_safety_fails_closed_even_when_the_before_run_had_the_same_violation() -> None:
    bad = _row("a", unsupported=3, critical=("USED_REJECTED_EVIDENCE",))
    before = _runs(bad, _row("b", unsupported=2), _row("h1", "holdout"))
    after = _runs(_row("a", critical=("USED_REJECTED_EVIDENCE",)), _row("b"), _row("h1", "holdout"))
    assert ("SAFETY", "dev/a: rejected_evidence_used=1") in evaluate(
        before, after, TARGET
    ).violations


def test_a_missing_holdout_fails_closed() -> None:
    after = _runs(_row("a"), _row("b"))
    rules = {r for r, _ in evaluate(BEFORE, after, TARGET).violations}
    assert "HOLDOUT" in rules


def test_a_guard_stops_the_target_being_met_by_doing_nothing() -> None:
    never_browsed = _improved(a=_row("a"), b=_row("b"))  # no rejections, but nothing verified
    before = _runs(
        _row("a", unsupported=3, verified=1),
        _row("b", unsupported=2),
        _row("h1", "holdout"),
        _row("h2", "holdout"),
    )
    assert ("GUARD", "verified_external:increase: 1 -> 0") in evaluate(
        before, never_browsed, TARGET, [GUARD]
    ).violations


def test_reports_are_written_and_the_exit_code_is_the_verdict(tmp_path: Path) -> None:
    def write(name: str, rows: list[dict[str, Any]]) -> Path:
        path = tmp_path / name
        path.write_text(json.dumps({"rows": rows}), "utf-8")
        return path

    before = write("before_scores.json", [_row("a", unsupported=2), _row("h", "holdout")])
    after = write("after_scores.json", [_row("a", verified=1), _row("h", "holdout")])
    out = tmp_path / "gate"
    argv = ["--before", str(before), "--after", str(after), "--target", str(TARGET)]
    assert main([*argv, "--guard", str(GUARD), "--out", str(out)]) == 0
    assert {p.name for p in out.iterdir()} == {"before.json", "after.json", "comparison.md"}
    md = (out / "comparison.md").read_text("utf-8")
    assert md.startswith("# Frozen regression gate: PASS")
    assert "requested fields per EVIDENCE_REQUESTED" in md
    worse = write(
        "worse_scores.json", [_row("a", unsupported=2), _row("h", "holdout", provenance=0)]
    )
    assert main(["--before", str(before), "--after", str(worse), "--target", str(TARGET),
                 "--out", str(out)]) == 1  # fmt: skip
    assert (out / "comparison.md").read_text("utf-8").startswith("# Frozen regression gate: FAIL")


def test_objectives_must_name_a_direction() -> None:
    with pytest.raises(ValueError):
        Objective.parse("verified_external")
    with pytest.raises(ValueError):
        Objective.parse("verified_external:sideways")
