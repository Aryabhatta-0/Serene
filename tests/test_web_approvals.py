"""Web approval channel (issue #37): a parent's decision in the web app goes through
the ledger's admission like any other channel; nothing the web sends can
approve RED, a changed intervention, or someone else's request."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from serene.adapters.web import WebApprovalChannel, WebApprovalCommand, WebDecision
from serene.domain.entities import Burden, Intervention
from serene.domain.events import EventType, SafetyClass
from serene.domain.values import ActorKind, ActorRef
from serene.ledger import AdmissionRejected
from serene.policies import safety
from serene.projections.state import ApprovalState, ExperimentStatus
from serene.testing import SyntheticFamily

from .experiments_view_fixture import COMMAND_EXAMPLE, build_fixture, command
from .trust_helpers import C, awaiting_approval, event_types, hypothesis, intervention


def _channel(fam: SyntheticFamily) -> WebApprovalChannel:
    return WebApprovalChannel(fam.ledger, fam.clock, new_source_id=lambda: fam.new_id("src"))


def _rid(n: int) -> str:
    return f"test-request-{n:08d}"


def test_approving_from_the_web_updates_the_lifecycle() -> None:
    fam = SyntheticFamily(seed="web-approve")
    exp, apr = awaiting_approval(fam)
    result = _channel(fam).decide(
        fam.parent, fam.child_id, command(fam, exp, WebDecision.APPROVE, _rid(1))
    )
    assert result.accepted and result.outcome == "APPROVAL_GRANTED"
    state = fam.state()
    assert state.experiments[exp.experiment_id].status is ExperimentStatus.APPROVED
    assert state.approvals[apr].state is ApprovalState.GRANTED
    assert state.approvals[apr].decided_via == "WEB_APP"
    event = fam.ledger.get_events_for_child(fam.child_id)[-1]
    assert event.event_type is EventType.APPROVAL_GRANTED
    assert event.source.kind.value == "WEB_APP" and event.actor == fam.parent


def test_declining_from_the_web_abandons_the_experiment() -> None:
    fam = SyntheticFamily(seed="web-decline")
    exp, apr = awaiting_approval(fam)
    result = _channel(fam).decide(
        fam.parent, fam.child_id, command(fam, exp, WebDecision.DECLINE, _rid(1))
    )
    assert result.outcome == "APPROVAL_REJECTED"
    state = fam.state()
    assert state.experiments[exp.experiment_id].status is ExperimentStatus.ABANDONED
    assert state.approvals[apr].state is ApprovalState.REJECTED


def test_red_cannot_be_approved_from_the_web() -> None:
    fam = SyntheticFamily(seed="web-red")
    _inv, hyp = hypothesis(fam)
    red = fam.propose_experiment(
        hyp,
        Intervention(
            category=C.MEDICATION,
            description="Give a calming supplement",
            reversible=True,
            max_duration_days=7,
            burden=Burden.LOW,
        ),
    )
    fam.classify(red)
    # A RED experiment never gets an approval request to approve.
    with pytest.raises(AdmissionRejected, match="RED"):
        fam.request_approval(red)

    # A command claiming to approve RED is refused before anything is appended.
    green, apr = awaiting_approval(fam)
    before = len(fam.ledger.get_events_for_child(fam.child_id))
    forged = command(fam, green, WebDecision.APPROVE, _rid(1)).model_copy(
        update={"shown_safety_class": SafetyClass.RED}
    )
    result = _channel(fam).decide(fam.parent, fam.child_id, forged)
    assert not result.accepted and result.reason_codes == ("RED_CANNOT_BE_APPROVED",)
    assert len(fam.ledger.get_events_for_child(fam.child_id)) == before
    assert fam.state().approvals[apr].state is ApprovalState.PENDING


def test_a_grant_binds_to_exactly_what_the_parent_was_shown() -> None:
    fam = SyntheticFamily(seed="web-digest")
    exp, apr = awaiting_approval(fam)
    stale = command(fam, exp, WebDecision.APPROVE, _rid(1)).model_copy(
        update={"shown_intervention_digest": "0" * 64}
    )
    result = _channel(fam).decide(fam.parent, fam.child_id, stale)
    assert "INTERVENTION_DIGEST_MISMATCH" in result.reason_codes
    understated = command(fam, exp, WebDecision.APPROVE, _rid(2)).model_copy(
        update={"shown_safety_class": SafetyClass.AMBER}
    )
    result = _channel(fam).decide(fam.parent, fam.child_id, understated)
    assert "SAFETY_CLASS_NOT_ACKNOWLEDGED" in result.reason_codes
    assert fam.state().approvals[apr].state is ApprovalState.PENDING


def test_only_the_requested_parent_can_decide() -> None:
    fam = SyntheticFamily(seed="web-principal")
    exp, apr = awaiting_approval(fam)
    cmd = command(fam, exp, WebDecision.APPROVE, _rid(1))
    caregiver = ActorRef(kind=ActorKind.CAREGIVER, actor_id=fam.new_id("act"))
    assert _channel(fam).decide(caregiver, fam.child_id, cmd).reason_codes == (
        "APPROVER_NOT_PARENT",
    )
    other_parent = ActorRef(kind=ActorKind.PARENT, actor_id=fam.new_id("act"))
    assert "APPROVER_MISMATCH" in _channel(fam).decide(other_parent, fam.child_id, cmd).reason_codes
    assert fam.state().approvals[apr].state is ApprovalState.PENDING


def test_a_resubmitted_decision_is_not_a_second_decision() -> None:
    fam = SyntheticFamily(seed="web-replay")
    exp, _apr = awaiting_approval(fam)
    cmd = command(fam, exp, WebDecision.APPROVE, _rid(1))
    assert _channel(fam).decide(fam.parent, fam.child_id, cmd).accepted
    again = _channel(fam).decide(fam.parent, fam.child_id, cmd)
    assert not again.accepted
    assert {r.split(":", 1)[0] for r in again.reason_codes} >= {"APPROVAL_NOT_OPEN"}
    assert event_types(fam).count(EventType.APPROVAL_GRANTED) == 1


def test_amber_needs_time_to_deliberate_and_expiry_closes_the_decision() -> None:
    fam = SyntheticFamily(seed="web-amber")
    amber, _apr = awaiting_approval(fam, intervention(C.SLEEP_SCHEDULE, "Earlier nap"))
    assert safety.classify_intervention(amber.intervention).safety_class is SafetyClass.AMBER
    early = _channel(fam).decide(
        fam.parent, fam.child_id, command(fam, amber, WebDecision.APPROVE, _rid(1))
    )
    assert "AMBER_DELIBERATION_TOO_SHORT" in early.reason_codes

    fam2 = SyntheticFamily(seed="web-expired")
    exp, _apr = awaiting_approval(fam2)
    fam2.clock.advance(timedelta(hours=25))  # SyntheticFamily requests expire after 24h
    late = _channel(fam2).decide(
        fam2.parent, fam2.child_id, command(fam2, exp, WebDecision.APPROVE, _rid(1))
    )
    assert "APPROVAL_EXPIRED" in late.reason_codes


def test_the_command_rejects_malformed_input() -> None:
    fam = SyntheticFamily(seed="web-malformed")
    exp, _apr = awaiting_approval(fam)
    good = command(fam, exp, WebDecision.APPROVE, _rid(1)).model_dump(mode="json")
    for bad in (
        {"decision": "MAYBE"},
        {"request_id": "short"},
        {"shown_safety_class": "BLUE"},
        {"approval_request_id": "exp_" + "0" * 32},
    ):
        with pytest.raises(ValidationError):
            WebApprovalCommand.model_validate(good | bad)


def test_the_web_apps_command_example_approves_through_the_channel() -> None:
    # The same JSON the web app's command builder is tested to produce.
    built = build_fixture()
    cmd = WebApprovalCommand.model_validate_json(COMMAND_EXAMPLE.read_text(encoding="utf-8"))
    result = built.web.decide(built.fam.parent, built.fam.child_id, cmd)
    assert result.accepted, result.reason_codes
    state = built.fam.state()
    assert state.experiments[built.awaiting_green.experiment_id].status is ExperimentStatus.APPROVED
