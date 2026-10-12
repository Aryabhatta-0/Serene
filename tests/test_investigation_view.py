"""The `investigations` projection (issue #35): state, hypotheses, missing evidence,
selected source, verification, explicit uncertainty, and a next action that is
exactly what the investigation controller does next."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from serene.domain.entities import InvestigationPhase
from serene.domain.values import SourceKind, SourceRef
from serene.policies.investigation import (
    NEXT_ACTION_BY_PHASE,
    PHASE_TRANSITIONS,
    NextActionKind,
    latest_request,
    next_action,
    pending_evidence,
)
from serene.projections.investigations import UNCERTAINTY_ORDER
from serene.projections.views import project

from .investigation_support import (
    TelegramScript,
    form_reply,
    make_investigation_rig,
    plan_reply,
)
from .investigation_view_fixture import (
    FIXTURE,
    HUNGER,
    QUESTION,
    TRANSITION,
    InvestigationFixture,
    build_fixture,
    fixture_json,
)

P = InvestigationPhase


@pytest.fixture(scope="module")
def built() -> InvestigationFixture:
    return build_fixture()


def _view(rows: list[dict[str, Any]], inv: str) -> dict[str, Any]:
    (row,) = [r for r in rows if r["projection"] == "investigations"]
    return row["state"][inv]


def test_the_web_fixture_is_exactly_what_the_kernel_produces(built: InvestigationFixture) -> None:
    assert FIXTURE.read_text(encoding="utf-8") == fixture_json(built), (
        "regenerate with: uv run python -m tests.investigation_view_fixture"
    )


def test_every_phase_has_a_next_action() -> None:
    assert set(NEXT_ACTION_BY_PHASE) == set(InvestigationPhase)
    # PROCESS_ANSWER is ASKING_HUMAN once the parent has answered (see below).
    assert set(NEXT_ACTION_BY_PHASE.values()) | {NextActionKind.PROCESS_ANSWER} == set(
        NextActionKind
    )


def test_next_action_is_what_the_controller_does_next(built: InvestigationFixture) -> None:
    inv = built.investigation_id
    kinds = []
    for before, result in built.steps:
        action = next_action(inv, before)
        kinds.append(action.kind)
        assert action.phase is before.investigation_phases[inv] is result.phase
        if action.kind is NextActionKind.WAIT_FOR_PARENT_ANSWER:
            assert result.action == "WAITING_FOR_PARENT"
            record = latest_request(inv, before)
            assert record is not None and action.request_id == record.request.request_id
        elif action.kind is NextActionKind.PROCESS_ANSWER:
            assert result.to_phase is P.VERIFYING
        elif action.kind in (NextActionKind.NONE_COMPLETE, NextActionKind.NONE_PARKED):
            assert result.action == "TERMINAL"
        else:
            # The controller acted in exactly that phase and moved on legally.
            assert result.to_phase in PHASE_TRANSITIONS[action.phase]
        if action.kind is NextActionKind.VERIFY_EVIDENCE:
            assert action.evidence_ids == tuple(pending_evidence(inv, before))
    assert kinds == [
        NextActionKind.UNDERSTAND_QUESTION,
        NextActionKind.RETRIEVE_CONTEXT,
        NextActionKind.FORM_HYPOTHESES,
        NextActionKind.CHOOSE_EVIDENCE,
        NextActionKind.WAIT_FOR_PARENT_ANSWER,
        NextActionKind.PROCESS_ANSWER,
        NextActionKind.VERIFY_EVIDENCE,
        NextActionKind.EVALUATE,
        NextActionKind.NONE_COMPLETE,
    ]


def test_the_question_asked_is_the_next_action_shown(built: InvestigationFixture) -> None:
    view = _view(built.snapshot, built.investigation_id)
    assert view["phase"] == "ASKING_HUMAN"
    assert view["next_action"]["kind"] == "WAIT_FOR_PARENT_ANSWER"
    sent = built.rig.outbox.sent[0][1]
    assert view["next_action"]["question"] in sent


def test_an_active_investigation_shows_every_element(built: InvestigationFixture) -> None:
    view = _view(built.snapshot, built.investigation_id)
    assert view["question"] == QUESTION
    assert view["status"] and view["phase"]
    assert {h["statement"] for h in view["hypotheses"]} == {HUNGER, TRANSITION}
    assert all(h["status"] == "ACTIVE" for h in view["hypotheses"])
    (request,) = view["evidence_requests"]
    assert request["status"] == "OPEN"  # missing evidence
    assert request["acquisition_mode"] == "ASK_PARENT"  # selected source
    assert request["information_value"] == "HIGH"
    statement = {h["hypothesis_id"]: h["statement"] for h in view["hypotheses"]}
    expected = {statement[p["hypothesis_id"]]: p["expected"] for p in request["predictions"]}
    assert expected == {HUNGER: "YES", TRANSITION: "NO"}  # as the rationale says
    assert request["evidence"] == []  # nothing to verify yet
    assert view["uncertainty"] == [
        "COMPETING_EXPLANATIONS",
        "NOTHING_TESTED",
        "PREDICTIONS_DISAGREE",
        "EVIDENCE_REQUESTED",
    ]


def test_verification_state_follows_the_verifier(built: InvestigationFixture) -> None:
    inv = built.investigation_id
    by_phase = {
        _view([c], inv)["phase"]: _view([c], inv)
        for c in built.changes
        if c["projection"] == "investigations"
    }
    # The parent's answer arrived over an authenticated channel, so it is a
    # verified first-hand report: nothing is left for the verifier to decide.
    verifying = by_phase["VERIFYING"]
    (evidence,) = verifying["evidence_requests"][0]["evidence"]
    assert evidence["verification_status"] == "VERIFIED"
    assert evidence["kind"] == "PARENT_REPORT" and evidence["source_kind"] == "TELEGRAM"
    assert verifying["evidence_requests"][0]["status"] == "ANSWERED"
    assert verifying["next_action"] == verifying["next_action"] | {
        "kind": "VERIFY_EVIDENCE",
        "evidence_ids": [],
    }
    assert "EVIDENCE_UNVERIFIED" not in verifying["uncertainty"]
    assert "EVIDENCE_REQUESTED" not in verifying["uncertainty"]

    complete = by_phase["COMPLETE"]
    (decided,) = complete["evidence_requests"][0]["evidence"]
    assert decided["verification_status"] == "VERIFIED"
    assert complete["next_action"]["kind"] == "NONE_COMPLETE"
    assert complete["next_action"]["reason_codes"]
    # Generation never declared a winner, so the uncertainty is still shown.
    assert "COMPETING_EXPLANATIONS" in complete["uncertainty"]


def test_uncertainty_is_never_a_number(built: InvestigationFixture) -> None:
    for row in [*built.snapshot, *built.changes]:
        if row["projection"] != "investigations":
            continue
        for view in row["state"].values():
            assert set(view["uncertainty"]) <= set(UNCERTAINTY_ORDER)
            assert not any(isinstance(v, float) for v in _leaves(view))


def _leaves(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return [x for v in value.values() for x in _leaves(v)]
    if isinstance(value, list):
        return [x for v in value for x in _leaves(v)]
    return [value]


def test_no_raw_reports_or_actor_ids_reach_the_projection(built: InvestigationFixture) -> None:
    text = fixture_json(built)
    for raw in ("crying at the door", "meltdown at pickup today", "calmer in the car"):
        assert raw not in text.lower()
    assert "act_" not in text


def test_a_parked_investigation_says_why_and_offers_no_next_step() -> None:
    rig = make_investigation_rig("view-parked")
    script = TelegramScript(rig)
    from tests.runtime_support import structure_reply

    for text, statement in [
        ("Pickup was awful", "Crying at daycare pickup"),
        ("Another meltdown", "Meltdown at daycare pickup"),
        ("Tears again", "Tearful at pickup"),
    ]:
        rig.transport.push("propose", structure_reply(statement))
        script.say(text)
    inv = rig.stack.investigations.open(
        rig.family.child_id,
        "Why?",
        opened_by=rig.family.parent,
        source=SourceRef(kind=SourceKind.TELEGRAM, source_id=rig.family.new_id("src")),
    )
    rig.transport.push("propose", form_reply([{"statement": TRANSITION}, {"statement": HUNGER}]))
    from .investigation_view_fixture import discriminating_question

    rig.transport.push("plan_evidence", plan_reply(discriminating_question(rig)))
    rig.stack.investigations.drive(rig.family.child_id, inv)
    rig.family.clock.advance(timedelta(hours=49))
    rig.stack.investigations.drive(rig.family.child_id, inv)
    view = project(rig.stack.ledger.replay_events(rig.family.child_id))["investigations"][inv]
    assert view["phase"] == "PARKED_UNRESOLVED"
    assert view["next_action"]["kind"] == "NONE_PARKED"
    assert "PARENT_NO_RESPONSE" in view["next_action"]["reason_codes"]
    assert "PARKED_UNRESOLVED" in view["uncertainty"]


def test_the_web_app_knows_exactly_the_kernels_projections() -> None:
    import re
    from pathlib import Path

    from serene.projections import PROJECTIONS

    source = (Path(__file__).resolve().parents[1] / "app/web/lib/projections/model.ts").read_text(
        encoding="utf-8"
    )
    block = source[source.index("PROJECTION_NAMES = [") : source.index("] as const")]
    assert set(re.findall(r'"([a-z_]+)"', block)) == set(PROJECTIONS)
