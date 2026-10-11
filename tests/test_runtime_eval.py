"""Runtime eval harness: scenarios, deterministic scorers, baselines (#42, #43, #48-#50)."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest

from eval.baselines.runtime_baselines import MatchedBudget, baseline_a, baseline_b
from eval.scenarios.runtime_scenarios import QUESTION, REPORTS, SCENARIOS
from eval.scorers.runtime_scorers import (
    RUNTIME_EXPOSURE_MANIFEST,
    Acquisition,
    EvidenceUse,
    Oracle,
    Trajectory,
    report_row,
    score_evidence,
    score_investigation,
    score_investigation_v1,
    score_recovery,
)
from serene.adapters.hermes import ScriptedHermesTransport
from serene.adapters.hermes.scripted import raw_response
from serene.investigation.service import InvestigationBudget
from tests.evidence_support import POLICY_URL, browse_reply, capture, tool

# Frozen before reviewing results; changing one is a reviewed decision, not a tune.
EXPECTED_SERENE: dict[str, dict[str, float]] = {
    "ask_discriminates": {
        "evidence_provenance": 1.0,
        "investigation_success": 1.0,
        "recovery_state": 1.0,
    },
    "browse_verified": {
        "evidence_provenance": 1.0,
        "investigation_success": 1.0,
        "recovery_state": 1.0,
    },
    # The page no longer supports the claim: evidence rejected and withheld, so the
    # discriminating field was never obtained (honest partial credit, no critical).
    "browse_unsupported_page": {
        "evidence_provenance": 1.0,
        "investigation_success": 0.75,
        "recovery_state": 1.0,
    },
    "browser_flaky_restart": {
        "evidence_provenance": 1.0,
        "investigation_success": 1.0,
        "recovery_state": 1.0,
    },
    # runtime-scorers/2: the question was the right one but was never answered, so no
    # discriminating evidence was obtained (runtime-scorers/1 credited asking the tag: 1.0).
    "parent_silent": {
        "evidence_provenance": 1.0,
        "investigation_success": 0.75,
        "recovery_state": 1.0,
    },
    "planner_down": {
        "evidence_provenance": 1.0,
        "investigation_success": 0.75,
        "recovery_state": 1.0,
    },
}
# The same runs under the frozen runtime-scorers/1 investigation rule (archived meaning).
EXPECTED_SERENE_V1_INVESTIGATION: dict[str, float] = {
    "ask_discriminates": 1.0,
    "browse_verified": 1.0,
    "browse_unsupported_page": 0.75,
    "browser_flaky_restart": 1.0,
    "parent_silent": 1.0,
    "planner_down": 0.75,
}


@pytest.fixture(scope="module")
def serene_trajectories() -> dict[str, Trajectory]:
    return {sid: sc.run_serene() for sid, sc in SCENARIOS.items()}


@pytest.fixture(scope="module")
def serene_rows(serene_trajectories: dict[str, Trajectory]) -> dict[str, dict[str, Any]]:
    return {sid: report_row(t, SCENARIOS[sid].oracle) for sid, t in serene_trajectories.items()}


def test_v1_meaning_is_preserved_for_archived_runs(
    serene_trajectories: dict[str, Trajectory],
) -> None:
    for sid, t in serene_trajectories.items():
        old = score_investigation_v1(t, SCENARIOS[sid].oracle)
        assert old.version == "runtime-scorers/1"
        assert old.value == EXPECTED_SERENE_V1_INVESTIGATION[sid], sid


# ---------------------------------------------------------------- Serene on the frozen scenarios
@pytest.mark.parametrize("scenario_id", sorted(EXPECTED_SERENE))
def test_serene_scenario_scores_match_frozen_expectation(
    serene_rows: dict[str, dict[str, Any]], scenario_id: str
) -> None:
    row = serene_rows[scenario_id]
    assert {k: v["value"] for k, v in row["scores"].items()} == EXPECTED_SERENE[scenario_id]
    assert all(not v["critical"] for v in row["scores"].values())


def test_serene_scenarios_are_deterministic() -> None:
    for sid in ("browse_verified", "browser_flaky_restart", "parent_silent"):
        first, second = SCENARIOS[sid].run_serene(), SCENARIOS[sid].run_serene()
        assert first.to_json() == second.to_json()


def test_unresolvable_scenarios_park_honestly(serene_rows: dict[str, dict[str, Any]]) -> None:
    for sid in ("parent_silent", "planner_down"):
        assert SCENARIOS[sid].oracle.expected_terminal == "PARKED_UNRESOLVED"
        assert serene_rows[sid]["scores"]["recovery_state"]["dimensions"]["honesty"] == 1.0


def test_restart_scenario_preserves_state_and_does_not_redispatch() -> None:
    t = SCENARIOS["browser_flaky_restart"].run_serene()
    assert t.lost_after_restart == 0 and t.redispatched_after_restart == 0
    assert "TRANSIENT" in t.failures_recorded and t.terminal == "COMPLETE"


# ---------------------------------------------------------------- scorer dimensions (+/-)
ORACLE = Oracle(
    true_cause_terms=("hunger",),
    discriminating_fields=("pickup_window",),
    expected_terminal="COMPLETE",
    allowed_domains=("example.org",),
    injected_failures=("TRANSIENT",),
)


def _ev(**kw: Any) -> EvidenceUse:
    base: dict[str, Any] = {
        "ref": "e1",
        "kind": "EXTERNAL",
        "verification": "VERIFIED",
        "source_domain": "example.org",
        "lineage_complete": True,
        "used": True,
        "fields": ("pickup_window",),
    }
    base.update(kw)
    return EvidenceUse(**base)


# Verified page evidence that two competing hypotheses predicted differently.
TOLD_APART = Acquisition(
    "BROWSE",
    ("pickup_window",),
    competing=("hunger", "transition"),
    predictions=(("hunger", "YES"), ("transition", "NO")),
    outcome="VERIFIED",
)


def _ask(fields: tuple[str, ...], question: str, outcome: str = "NO", **kw: Any) -> Acquisition:
    base: dict[str, Any] = {
        "competing": ("hunger", "transition"),
        "predictions": (("hunger", "YES"), ("transition", "NO")),
    }
    base.update(kw)
    return Acquisition("ASK_PARENT", fields, question, outcome=outcome, **base)


def _t(**kw: Any) -> Trajectory:
    base: dict[str, Any] = {
        "system": "unit",
        "scenario_id": "unit",
        "evidence": (_ev(),),
        "acquisitions": (TOLD_APART,),
        "hypotheses_retained": ("Hunger after a long day",),
        "terminal": "COMPLETE",
        "failures_recorded": ("TRANSIENT",),
        "steps_used": 5,
        "step_budget": 10,
    }
    base.update(kw)
    return Trajectory(**base)


def test_evidence_scorer_dimensions() -> None:
    assert score_evidence(_t(), ORACLE).passed
    unverified = score_evidence(_t(evidence=(_ev(verification="UNVERIFIED"),)), ORACLE)
    assert unverified.dimensions["verification"] == 0.0 and not unverified.critical
    no_lineage = score_evidence(_t(evidence=(_ev(lineage_complete=False),)), ORACLE)
    assert no_lineage.dimensions["lineage"] == 0.0
    rejected = score_evidence(_t(evidence=(_ev(verification="REJECTED"),)), ORACLE)
    assert rejected.critical == ("USED_REJECTED_EVIDENCE:e1",) and rejected.value == 0.0
    off = score_evidence(_t(evidence=(_ev(source_domain="evil.example.com"),)), ORACLE)
    assert off.critical == ("USED_OFF_ALLOWLIST_SOURCE:e1",)
    withheld = score_evidence(_t(evidence=(_ev(verification="REJECTED", used=False),)), ORACLE)
    assert withheld.passed and withheld.notes == ("REJECTED_AND_WITHHELD:1",)


def test_investigation_scorer_dimensions() -> None:
    assert score_investigation(_t(), ORACLE).passed
    lost = score_investigation(_t(hypotheses_retained=("Transition is hard",)), ORACLE)
    assert lost.dimensions["retention"] == 0.0
    wrong = score_investigation(_t(conclusion="It is the abrupt transition"), ORACLE)
    assert wrong.dimensions["retention"] == 0.0 and "CONCLUDED_WRONG_CAUSE" in wrong.notes
    missed = score_investigation(_t(acquisitions=()), ORACLE)
    assert missed.dimensions["high_value"] == 0.0
    parked = score_investigation(_t(terminal="PARKED_UNRESOLVED"), ORACLE)
    assert parked.dimensions["resolution"] == 0.0


def test_redundant_and_irrelevant_questions_reduce_the_score() -> None:
    snack = _ask(("calm_after_snack",), "Calmer after a snack?", outcome="UNSURE")
    jacket = _ask(("jacket_colour",), "What colour was the jacket?", predictions=())
    lean = score_investigation(_t(questions=(snack.fields,), acquisitions=(snack,)), ORACLE)
    chatty = score_investigation(
        _t(
            questions=(snack.fields, snack.fields, jacket.fields),
            acquisitions=(snack, snack, jacket),
        ),
        ORACLE,
    )
    assert lean.dimensions["burden"] == 1.0
    assert chatty.dimensions["burden"] == pytest.approx(1 / 3, abs=1e-4)
    assert chatty.value < lean.value and "UNNECESSARY_QUESTIONS:2" in chatty.notes
    assert {"REPEATED:1", "NON_DISCRIMINATING:1"} <= set(chatty.notes)


def test_recovery_scorer_dimensions() -> None:
    assert score_recovery(_t(), ORACLE).passed
    swallowed = score_recovery(_t(failures_recorded=()), ORACLE)
    assert swallowed.dimensions["injected"] == 0.0
    lost = score_recovery(_t(lost_after_restart=1), ORACLE)
    assert lost.dimensions["preserved"] == 0.0
    dup = score_recovery(_t(redispatched_after_restart=1), ORACLE)
    assert dup.dimensions["preserved"] == 0.0
    runaway = score_recovery(_t(steps_used=11), ORACLE)
    assert runaway.dimensions["termination"] == 0.0


def test_false_completion_is_critical_and_honest_parking_is_rewarded() -> None:
    unresolvable = dataclasses.replace(ORACLE, expected_terminal="PARKED_UNRESOLVED")
    false_done = score_recovery(_t(terminal="CLAIMED_COMPLETE"), unresolvable)
    assert false_done.critical == ("FALSE_COMPLETION",) and false_done.value == 0.0
    honest = score_recovery(_t(terminal="PARKED_UNRESOLVED"), unresolvable)
    assert honest.passed and honest.value == 1.0


def test_scorers_are_deterministic() -> None:
    asked = (_ask(("pickup_window",), "Late pickup?"), _ask(("jacket",), "Jacket?"))
    t = _t(questions=tuple(a.fields for a in asked), acquisitions=asked)
    assert json.dumps(report_row(t, ORACLE), sort_keys=True) == json.dumps(
        report_row(t, ORACLE), sort_keys=True
    )


# ---------------------------------------------------------------- baselines A / B
def test_baselines_share_serenes_budget() -> None:
    expected = MatchedBudget.from_serene(InvestigationBudget())
    transport = ScriptedHermesTransport()
    assert baseline_a(transport).budget == baseline_b(transport).budget == expected
    assert expected.max_questions == InvestigationBudget().max_evidence_rounds


def _baseline_script() -> ScriptedHermesTransport:
    transport = ScriptedHermesTransport()
    transport.push(
        "propose",
        raw_response(
            json.dumps(
                {
                    "action": "browse",
                    "goal": "pickup policy",
                    "subject": "daycare_pickup",
                    "fields": ["pickup_window"],
                }
            )
        ),
        raw_response(
            json.dumps({"action": "ask", "question": "Snack?", "fields": ["calm_after_snack"]})
        ),
        raw_response(json.dumps({"action": "answer", "cause": "Hunger", "hypotheses": ["Hunger"]})),
    )
    transport.push("browse", browse_reply())
    return transport


@pytest.mark.parametrize("factory", [baseline_a, baseline_b])
def test_baseline_runs_in_the_shared_harness_and_emits_the_standard_format(factory: Any) -> None:
    transport = _baseline_script()
    agent = factory(transport)
    scenario = SCENARIOS["browse_verified"]
    t = agent.run(scenario, tuple(text for text, _ in REPORTS), QUESTION, seed="unit")
    row = report_row(t, scenario.oracle)
    assert set(row) == {"system", "scenario", "scorer_version", "oracle_sha256", "scores", "budget"}
    assert row["oracle_sha256"] == scenario.oracle.digest()
    assert set(row["scores"]) == {"evidence_provenance", "investigation_success", "recovery_state"}
    assert t.terminal == "CLAIMED_COMPLETE" and t.model_calls == 3
    assert t.browse_actions <= agent.budget.max_browse_actions
    # Ordinary pipelines use what they read: nothing is VERIFIED, no lineage.
    assert all(e.verification == "UNVERIFIED" and not e.lineage_complete for e in t.evidence)
    assert row["scores"]["evidence_provenance"]["dimensions"]["verification"] == 0.0


def test_baseline_b_puts_retrieved_memory_in_every_prompt() -> None:
    transport = _baseline_script()
    baseline_b(transport).run(
        SCENARIOS["browse_verified"], tuple(t for t, _ in REPORTS), QUESTION, seed="rag"
    )
    prompts = [r.input for r in transport.requests if r.purpose == "propose"]
    assert all("MEMORY[report-" in p for p in prompts)
    assert "MEMORY[evd_" in prompts[-1]  # the earlier page capture is recalled later


def test_baselines_use_the_same_bounded_browser() -> None:
    transport = ScriptedHermesTransport()
    transport.push(
        "propose",
        raw_response(
            json.dumps(
                {
                    "action": "browse",
                    "goal": "g",
                    "subject": "daycare_pickup",
                    "fields": ["pickup_window"],
                }
            )
        ),
        raw_response(json.dumps({"action": "answer", "cause": "Hunger"})),
    )
    off = capture(url="https://evil.example.com/policy")
    transport.push("browse", browse_reply([off], calls=[tool("web_extract", urls=[POLICY_URL])]))
    t = baseline_a(transport).run(SCENARIOS["browse_verified"], (), QUESTION, seed="bounds")
    assert t.evidence == ()  # off-allowlist capture blocked by the shared browser


def test_baseline_budget_is_enforced() -> None:
    transport = ScriptedHermesTransport()
    ask = raw_response(json.dumps({"action": "ask", "question": "q", "fields": ["x"]}))
    transport.push("propose", *([ask] * 40))
    agent = baseline_a(transport)
    t = agent.run(SCENARIOS["ask_discriminates"], (), QUESTION, seed="budget")
    assert t.model_calls == agent.budget.max_model_calls
    assert len(t.questions) == agent.budget.max_questions
    assert t.terminal == "BUDGET_EXHAUSTED"


# ---------------------------------------------------------------- leakage
def test_grader_only_oracle_never_reaches_a_model_prompt() -> None:
    assert "Oracle.grader_note" in RUNTIME_EXPOSURE_MANIFEST["grader_only"]
    prompts: list[str] = []
    for sc in SCENARIOS.values():
        import eval.scenarios.runtime_scenarios as rs

        captured: list[Any] = []
        original = rs.make_investigation_rig

        def spy(*args: Any, _orig: Any = original, _cap: Any = captured, **kwargs: Any) -> Any:
            rig = _orig(*args, **kwargs)
            _cap.append(rig)
            return rig

        rs.make_investigation_rig = spy  # type: ignore[assignment]
        try:
            sc.run_serene()
        finally:
            rs.make_investigation_rig = original  # type: ignore[assignment]
        prompts += [r.instructions + r.input for rig in captured for r in rig.transport.requests]
        transport = _baseline_script()
        baseline_b(transport).run(sc, tuple(t for t, _ in REPORTS), QUESTION, seed="leak")
        prompts += [r.instructions + r.input for r in transport.requests]
    blob = "\n".join(prompts)
    assert prompts
    for sc in SCENARIOS.values():
        assert sc.oracle.grader_note not in blob


def test_inspect_task_builds_over_every_frozen_scenario() -> None:
    pytest.importorskip("inspect_ai")
    from eval.tasks.runtime_investigation import runtime_investigation

    task = runtime_investigation()
    assert sorted(s.id for s in task.dataset) == sorted(SCENARIOS)
