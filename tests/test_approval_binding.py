"""Approval forgery and binding: identity + digest + channel receipt + expiry + current
safety class + single use; AMBER escalation; prose is never authority (issues #23, #24)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from serene.domain.events import (
    ApprovalNudged,
    ApprovalRequested,
    EventType,
    ExperimentAbandoned,
    SafetyClass,
)
from serene.domain.values import ActorKind, ActorRef, SourceKind
from serene.ledger import AdmissionRejected
from serene.policies import approval as approval_policy
from serene.policies.approval import AMBER_MIN_DELIBERATION, MAX_APPROVAL_TTL
from serene.policies.safety import SafetyDecision, intervention_digest
from serene.testing import SyntheticFamily

from .trust_helpers import C, awaiting_approval, grant_draft, intervention, reasons


def test_valid_grant_binds_every_element(family: SyntheticFamily) -> None:
    exp, apr = awaiting_approval(family)
    family.append(grant_draft(family, exp, apr))
    record = family.state().approvals[apr]
    assert record.state.value == "GRANTED"
    assert record.receipt_key == f"TELEGRAM:tg-callback-{apr[-12:]}"
    assert record.requested_of == family.parent.actor_id
    family.start(exp, apr)
    with pytest.raises(AdmissionRejected, match="APPROVAL_ALREADY_USED"):
        family.start(exp, apr)


@pytest.mark.parametrize(
    ("actor_kind", "expected"),
    [
        (ActorKind.AGENT, "ACTOR_NOT_PERMITTED"),
        (ActorKind.SYSTEM, "ACTOR_NOT_PERMITTED"),
        (ActorKind.POLICY, "ACTOR_NOT_PERMITTED"),
        (ActorKind.CAREGIVER, "ACTOR_NOT_PERMITTED"),
    ],
)
def test_only_a_parent_can_grant(
    family: SyntheticFamily, actor_kind: ActorKind, expected: str
) -> None:
    exp, apr = awaiting_approval(family)
    actor = ActorRef(kind=actor_kind, actor_id=family.parent.actor_id)
    with pytest.raises(AdmissionRejected) as info:
        family.append(grant_draft(family, exp, apr, actor=actor))
    assert expected in reasons(info)


def test_receipt_replay_cannot_authorize_a_second_request(family: SyntheticFamily) -> None:
    exp, apr = awaiting_approval(family)
    family.append(grant_draft(family, exp, apr, message_ref="tg-callback-shared"))
    exp2 = family.propose_experiment(family.state().entities[exp.hypothesis_id].entity)
    family.classify(exp2)
    apr2 = family.request_approval(exp2)
    with pytest.raises(AdmissionRejected) as info:
        family.append(grant_draft(family, exp2, apr2, message_ref="tg-callback-shared"))
    assert reasons(info) == {"RECEIPT_REPLAYED"}


def test_receipt_must_fall_inside_the_request_window(family: SyntheticFamily) -> None:
    exp, apr = awaiting_approval(family)
    requested_at = family.state().approvals[apr].requested_at
    assert requested_at is not None
    early = grant_draft(family, exp, apr, received_at=requested_at - timedelta(minutes=5))
    with pytest.raises(AdmissionRejected, match="RECEIPT_PREDATES_REQUEST"):
        family.append(early)
    future = grant_draft(family, exp, apr, received_at=family.clock.now() + timedelta(hours=1))
    with pytest.raises(AdmissionRejected, match="RECEIPT_IN_FUTURE"):
        family.append(future)


def test_receipt_channel_must_match_the_authenticated_source(family: SyntheticFamily) -> None:
    exp, apr = awaiting_approval(family)
    draft = grant_draft(
        family, exp, apr, source_kind=SourceKind.WEB_APP, receipt_channel=SourceKind.TELEGRAM
    )
    with pytest.raises(AdmissionRejected, match="CHANNEL_MISMATCH"):
        family.append(draft)


@pytest.mark.parametrize("prose", ["sure", "ok go ahead", "APPROVED", "yes, approve experiment"])
def test_prose_is_never_authority(family: SyntheticFamily, prose: str) -> None:
    """Parent text arrives as an observation; it carries no path into approval state."""
    exp, apr = awaiting_approval(family)
    family.report(prose)
    assert family.state().approvals[apr].state.value == "PENDING"
    with pytest.raises(AdmissionRejected) as info:
        family.start(exp, apr)
    assert {"EXPERIMENT_NOT_APPROVED", "APPROVAL_NOT_GRANTED"} <= reasons(info)
    # The runtime relaying the same words as a grant is refused at the channel boundary.
    relayed = grant_draft(family, exp, apr, source_kind=SourceKind.KERNEL, message_ref=prose)
    with pytest.raises(AdmissionRejected, match="UNAUTHENTICATED_CHANNEL"):
        family.append(relayed)


def test_grant_is_bound_to_the_current_safety_class(
    family: SyntheticFamily, monkeypatch: pytest.MonkeyPatch
) -> None:
    exp, apr = awaiting_approval(family)
    tightened = SafetyDecision(SafetyClass.AMBER, ("ESCALATED_CATEGORY:TRANSITION_SUPPORT",))
    monkeypatch.setattr(approval_policy, "classify_intervention", lambda _iv: tightened)
    with pytest.raises(AdmissionRejected, match="SAFETY_CLASS_CHANGED_SINCE_REQUEST"):
        family.append(grant_draft(family, exp, apr))


def test_start_rechecks_the_current_safety_class_after_the_grant(
    family: SyntheticFamily, monkeypatch: pytest.MonkeyPatch
) -> None:
    exp, apr = awaiting_approval(family)
    family.append(grant_draft(family, exp, apr))
    tightened = SafetyDecision(SafetyClass.AMBER, ("ESCALATED_CATEGORY:TRANSITION_SUPPORT",))
    monkeypatch.setattr(approval_policy, "classify_intervention", lambda _iv: tightened)
    with pytest.raises(AdmissionRejected) as info:
        family.start(exp, apr)
    assert {"APPROVAL_SAFETY_CLASS_STALE", "CLASSIFICATION_STALE"} <= reasons(info)


def test_late_grant_cannot_revive_an_abandoned_experiment(family: SyntheticFamily) -> None:
    exp, apr = awaiting_approval(family)
    family.append(
        family.draft(
            EventType.EXPERIMENT_ABANDONED,
            family.parent,
            ExperimentAbandoned(experiment_id=exp.experiment_id, reason_codes=("PARENT_DECLINED",)),
            source=family.source(),
        )
    )
    with pytest.raises(AdmissionRejected, match="EXPERIMENT_NOT_AWAITING_APPROVAL"):
        family.append(grant_draft(family, exp, apr))
    assert family.state().experiments[exp.experiment_id].status.value == "ABANDONED"


def test_request_expiry_is_bounded(family: SyntheticFamily) -> None:
    _inv_exp, _ = awaiting_approval(family)
    exp = family.propose_experiment(family.state().entities[_inv_exp.hypothesis_id].entity)
    family.classify(exp)
    base = ApprovalRequested(
        approval_request_id=family.new_id("apr"),
        experiment_id=exp.experiment_id,
        intervention_digest=intervention_digest(exp.intervention),
        safety_class=SafetyClass.GREEN,
        requested_of=family.parent.actor_id,
        expires_at=family.clock.now() + MAX_APPROVAL_TTL + timedelta(days=1),
    )
    with pytest.raises(AdmissionRejected, match="EXPIRY_TOO_LONG"):
        family.append(family.draft(EventType.APPROVAL_REQUESTED, family.policy, base))
    past = base.model_copy(update={"expires_at": family.clock.now() - timedelta(hours=1)})
    with pytest.raises(AdmissionRejected, match="EXPIRY_IN_PAST"):
        family.append(family.draft(EventType.APPROVAL_REQUESTED, family.policy, past))


# ------------------------------------------------------------------ AMBER escalation
def _amber(family: SyntheticFamily) -> tuple[object, str]:
    return awaiting_approval(
        family, intervention(C.SLEEP_SCHEDULE, "Move bedtime 15 minutes earlier")
    )


def test_amber_is_never_nudged(family: SyntheticFamily) -> None:
    _exp, apr = _amber(family)
    nudge = family.draft(
        EventType.APPROVAL_NUDGED, family.system, ApprovalNudged(approval_request_id=apr)
    )
    with pytest.raises(AdmissionRejected, match="NUDGE_NOT_PERMITTED:AMBER"):
        family.append(nudge)


def test_amber_requires_deliberation_and_explicit_acknowledgement(family: SyntheticFamily) -> None:
    exp, apr = _amber(family)
    with pytest.raises(AdmissionRejected, match="AMBER_DELIBERATION_TOO_SHORT"):
        family.append(grant_draft(family, exp, apr))  # type: ignore[arg-type]
    family.clock.advance(AMBER_MIN_DELIBERATION)
    family.append(grant_draft(family, exp, apr))  # type: ignore[arg-type]
    family.start(exp, apr)  # type: ignore[arg-type]
    assert family.state().experiments[exp.experiment_id].status.value == "STARTED"  # type: ignore[attr-defined]


def test_amber_rejection_needs_no_deliberation(family: SyntheticFamily) -> None:
    """Saying no is always safe and immediate."""
    from serene.domain.events import ApprovalRejected, ChannelReceipt

    _exp, apr = _amber(family)
    family.append(
        family.draft(
            EventType.APPROVAL_REJECTED,
            family.parent,
            ApprovalRejected(
                approval_request_id=apr,
                receipt=ChannelReceipt(
                    channel=SourceKind.TELEGRAM,
                    message_ref="tg-no-1",
                    received_at=family.clock.now(),
                ),
            ),
            source=family.source(SourceKind.TELEGRAM),
        )
    )
    assert family.state().approvals[apr].state.value == "REJECTED"
