"""An experiment proposed while evaluating goes through Branch B's lifecycle (#24, #25).

Before this, an admitted experiment moved the investigation to NEEDS_APPROVAL but was
never classified, no approval was ever requested and no parent was ever asked, so the
investigation waited forever (seen in the 2026-10-11 live run).
"""

from __future__ import annotations

from typing import Any

from serene.adapters.hermes import wire_response
from serene.adapters.hermes.transport import HermesRequest, HermesResponse
from serene.domain.entities import InvestigationPhase as P
from serene.domain.events import EventType
from serene.domain.values import ActorKind, SourceKind, SourceRef
from serene.projections.state import ExperimentStatus
from tests.investigation_support import (
    TelegramScript,
    form_reply,
    make_investigation_rig,
    no_change_reply,
    plan_reply,
)
from tests.runtime_support import live_hypothesis_ids_in
from tests.test_investigation import (
    HUNGER,
    TRANSITION,
    _after_answer,
    _discriminating_question,
    _report_three,
)


def _experiment(category: str, description: str) -> Any:
    def reply(request: HermesRequest) -> HermesResponse:
        hyp = live_hypothesis_ids_in(request)[0]
        return wire_response(
            {
                "proposals": [
                    {
                        "kind": "experiment",
                        "hypothesis_ref": hyp,
                        "category": category,
                        "description": description,
                        "reversible": True,
                        "max_duration_days": 5,
                        "burden": "LOW",
                        "comparison": "days with the change vs the days before",
                        "outcome_measure": "minutes of crying at pickup",
                    }
                ]
            }
        )

    return reply


def _to_evaluating(seed: str, evaluating_reply: Any) -> tuple[Any, str, TelegramScript, list[Any]]:
    rig = make_investigation_rig(seed)
    script = TelegramScript(rig)
    _report_three(script, rig)
    inv = rig.stack.investigations.open(
        rig.family.child_id,
        "Why are daycare pickups so hard?",
        opened_by=rig.family.parent,
        source=SourceRef(kind=SourceKind.TELEGRAM, source_id=rig.family.new_id("src")),
    )
    rig.transport.push("propose", form_reply([{"statement": TRANSITION}, {"statement": HUNGER}]))
    rig.transport.push("plan_evidence", plan_reply(_discriminating_question))
    rig.stack.investigations.drive(rig.family.child_id, inv)
    assert script.tap_last(1).outcome == "ANSWER_RECORDED"  # NO, as in run_ask_investigation
    rig.transport.push("propose", evaluating_reply)
    steps = rig.stack.investigations.drive(rig.family.child_id, inv)
    return rig, inv, script, steps


def test_a_proposed_experiment_is_classified_and_the_parent_is_asked() -> None:
    rig, inv, script, steps = _to_evaluating(
        "approval-green", _experiment("ROUTINE_TIMING", "Give a two-minute warning before pickup")
    )
    assert steps[-1].phase is P.NEEDS_APPROVAL and steps[-1].action == "WAITING_FOR_APPROVAL"
    state = rig.stack.ledger.replay_events(rig.family.child_id)
    (record,) = state.experiments.values()
    assert record.status is ExperimentStatus.AWAITING_APPROVAL
    types = [e.event_type for e in rig.events()]
    assert EventType.EXPERIMENT_CLASSIFIED in types and EventType.APPROVAL_REQUESTED in types
    actors = {e.event_type: e.actor.kind for e in rig.events()}
    assert actors[EventType.EXPERIMENT_CLASSIFIED] is ActorKind.POLICY
    assert actors[EventType.APPROVAL_REQUESTED] is ActorKind.POLICY
    _chat, text, buttons = rig.outbox.sent[-1]
    assert "experiment" in text and [b[0] for b in buttons] == ["APPROVE", "REJECT"]
    assert EventType.APPROVAL_GRANTED not in types  # nothing but the parent can decide

    # The parent declines on the authenticated prompt; the investigation moves on.
    assert script.tap_last(1).outcome == "APPROVAL_REJECTED"
    rig.transport.push("propose", no_change_reply())
    rig.transport.push("plan_evidence", plan_reply(_after_answer))
    after = rig.stack.investigations.drive(rig.family.child_id, inv)
    assert [r.to_phase for r in after] == [P.EVALUATING, P.COMPLETE]
    state = rig.stack.ledger.replay_events(rig.family.child_id)
    assert next(iter(state.experiments.values())).status is ExperimentStatus.ABANDONED


def test_a_red_experiment_is_blocked_and_never_reaches_the_parent() -> None:
    rig, _inv, _script, steps = _to_evaluating(
        "approval-red", _experiment("SUPPLEMENT", "Try a calming supplement before pickup")
    )
    state = rig.stack.ledger.replay_events(rig.family.child_id)
    (record,) = state.experiments.values()
    assert record.status is ExperimentStatus.BLOCKED
    assert EventType.APPROVAL_REQUESTED not in [e.event_type for e in rig.events()]
    assert all("supplement" not in text for _c, text, _b in rig.outbox.sent)
    assert P.NEEDS_APPROVAL not in [r.to_phase for r in steps]


def test_after_a_parent_declines_the_model_is_not_offered_experiments_again() -> None:
    """Live 2026-10-11: the parent was prompted five times in a row after declining."""
    rig, inv, script, _steps = _to_evaluating(
        "approval-decline", _experiment("ROUTINE_TIMING", "Give a two-minute warning")
    )
    prompts = len(rig.outbox.sent)
    assert script.tap_last(1).outcome == "APPROVAL_REJECTED"
    # The model tries again; the experiment kind is no longer offered, so it is refused.
    rig.transport.push("propose", _experiment("ROUTINE_TIMING", "Try a shorter warning"))
    rig.transport.push("plan_evidence", plan_reply(_after_answer))
    after = rig.stack.investigations.drive(rig.family.child_id, inv)
    sent = rig.transport.requests[-2].input
    assert '"kind":"experiment"' not in sent and "The parent declined an experiment" in sent
    assert len(rig.outbox.sent) == prompts  # never asked again
    state = rig.stack.ledger.replay_events(rig.family.child_id)
    assert len(state.experiments) == 1
    assert P.NEEDS_APPROVAL not in [r.to_phase for r in after]
