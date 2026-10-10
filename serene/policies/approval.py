"""Parent approval lifecycle and experiment-start admission (issues #23, #24, #25).

Approval exists only as ledger state: an APPROVAL_GRANTED event appended by the
requested parent, over an authenticated channel, carrying a channel receipt
that was received inside the request window and never used before, bound to
the exact intervention digest and the *current* safety class, before expiry,
and consumed at most once. Model text saying "approved" (or "sure") has no
path into this state. RED fails closed even if a grant exists.

AMBER escalates for stronger human judgement: it is never nudged, its grant
must acknowledge AMBER explicitly, and the grant must arrive after a minimum
deliberation window rather than as a reflexive tap.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final

from serene.domain.events import (
    ApprovalGranted,
    ApprovalNudged,
    ApprovalRejected,
    ApprovalRequested,
    ApprovalTimedOut,
    EventDraft,
    SafetyClass,
)
from serene.domain.values import AUTHENTICATED_CHANNELS, ActorKind
from serene.policies.decision import PolicyDecision
from serene.policies.experiments import requirement_violations
from serene.policies.safety import classify_intervention, intervention_digest
from serene.projections.state import (
    OPEN_APPROVAL_STATES,
    ApprovalState,
    ExperimentRecord,
    ExperimentStatus,
    KernelState,
    LifecycleStatus,
    receipt_key,
)

POLICY_VERSION: Final = "approval/2"
MAX_NUDGES: Final = 1
MAX_APPROVAL_TTL: Final = timedelta(days=7)
# An AMBER grant must arrive at least this long after the request was raised.
AMBER_MIN_DELIBERATION: Final = timedelta(minutes=10)


def _decision(reasons: list[str]) -> PolicyDecision:
    return PolicyDecision.from_reasons(reasons, POLICY_VERSION)


def _unmet(record: ExperimentRecord, state: KernelState) -> list[str]:
    return [
        f"EXPERIMENT_REQUIREMENTS_UNMET:{r}"
        for r in requirement_violations(record.experiment, state)
    ]


def check_approval_request(
    payload: ApprovalRequested, state: KernelState, now: datetime
) -> PolicyDecision:
    reasons: list[str] = []
    if payload.approval_request_id in state.approvals:
        reasons.append("DUPLICATE_APPROVAL_REQUEST")
    record = state.experiments.get(payload.experiment_id)
    if record is None:
        return _decision([*reasons, "UNKNOWN_EXPERIMENT"])
    computed = classify_intervention(record.experiment.intervention)
    if computed.safety_class is SafetyClass.RED or record.safety_class is SafetyClass.RED:
        reasons.append("RED_CANNOT_BE_APPROVED")
    if record.status is not ExperimentStatus.CLASSIFIED:
        reasons.append(f"EXPERIMENT_NOT_CLASSIFIED:{record.status.value}")
    if payload.safety_class != computed.safety_class:
        reasons.append("SAFETY_CLASS_MISMATCH")
    if payload.intervention_digest != intervention_digest(record.experiment.intervention):
        reasons.append("INTERVENTION_DIGEST_MISMATCH")
    if payload.expires_at <= now:
        reasons.append("EXPIRY_IN_PAST")
    if payload.expires_at - now > MAX_APPROVAL_TTL:
        reasons.append("EXPIRY_TOO_LONG")
    reasons += _unmet(record, state)
    return _decision(reasons)


def check_approval_nudge(payload: ApprovalNudged, state: KernelState) -> PolicyDecision:
    approval = state.approvals.get(payload.approval_request_id)
    if approval is None:
        return _decision(["UNKNOWN_APPROVAL_REQUEST"])
    reasons: list[str] = []
    if approval.state not in OPEN_APPROVAL_STATES:
        reasons.append(f"APPROVAL_NOT_OPEN:{approval.state.value}")
    if approval.nudges >= MAX_NUDGES:
        reasons.append("SINGLE_NUDGE_EXCEEDED")
    if approval.safety_class is not SafetyClass.GREEN:
        # Higher-burden decisions are escalated for judgement, never chased.
        reasons.append(f"NUDGE_NOT_PERMITTED:{approval.safety_class.value}")
    return _decision(reasons)


def check_approval_decision(
    draft: EventDraft,
    payload: ApprovalGranted | ApprovalRejected,
    state: KernelState,
    now: datetime,
) -> PolicyDecision:
    """A parent decision is valid only from the requested parent over an authenticated channel."""
    approval = state.approvals.get(payload.approval_request_id)
    if approval is None:
        return _decision(["UNKNOWN_APPROVAL_REQUEST"])
    reasons: list[str] = []
    if approval.state not in OPEN_APPROVAL_STATES:
        reasons.append(f"APPROVAL_NOT_OPEN:{approval.state.value}")
    if draft.actor.kind is not ActorKind.PARENT:
        reasons.append("APPROVER_NOT_PARENT")
    if draft.actor.actor_id != approval.requested_of:
        reasons.append("APPROVER_MISMATCH")
    if draft.source.kind not in AUTHENTICATED_CHANNELS:
        reasons.append("UNAUTHENTICATED_CHANNEL")
    if payload.receipt.channel != draft.source.kind:
        reasons.append("CHANNEL_MISMATCH")
    if now >= approval.expires_at:
        reasons.append("APPROVAL_EXPIRED")

    receipt = payload.receipt
    if receipt_key(receipt.channel.value, receipt.message_ref) in state.channel_receipts:
        reasons.append("RECEIPT_REPLAYED")
    if receipt.received_at > now:
        reasons.append("RECEIPT_IN_FUTURE")
    if approval.requested_at is None or receipt.received_at < approval.requested_at:
        reasons.append("RECEIPT_PREDATES_REQUEST")
    if receipt.received_at >= approval.expires_at:
        reasons.append("APPROVAL_EXPIRED")

    record = state.experiments.get(approval.experiment_id)
    if record is None or record.status is not ExperimentStatus.AWAITING_APPROVAL:
        status = "UNKNOWN" if record is None else record.status.value
        reasons.append(f"EXPERIMENT_NOT_AWAITING_APPROVAL:{status}")

    if isinstance(payload, ApprovalGranted):
        if approval.safety_class is SafetyClass.RED:
            reasons.append("RED_CANNOT_BE_APPROVED")
        if payload.intervention_digest != approval.intervention_digest:
            reasons.append("INTERVENTION_DIGEST_MISMATCH")
        if payload.acknowledged_safety_class != approval.safety_class:
            reasons.append("SAFETY_CLASS_NOT_ACKNOWLEDGED")
        if record is not None:
            current = classify_intervention(record.experiment.intervention).safety_class
            if current is not approval.safety_class:
                reasons.append("SAFETY_CLASS_CHANGED_SINCE_REQUEST")
            reasons += _unmet(record, state)
        if (
            approval.safety_class is SafetyClass.AMBER
            and approval.requested_at is not None
            and receipt.received_at - approval.requested_at < AMBER_MIN_DELIBERATION
        ):
            reasons.append("AMBER_DELIBERATION_TOO_SHORT")
    return _decision(reasons)


def check_approval_timeout(
    payload: ApprovalTimedOut, state: KernelState, now: datetime
) -> PolicyDecision:
    approval = state.approvals.get(payload.approval_request_id)
    if approval is None:
        return _decision(["UNKNOWN_APPROVAL_REQUEST"])
    reasons: list[str] = []
    if approval.state not in OPEN_APPROVAL_STATES:
        reasons.append(f"APPROVAL_NOT_OPEN:{approval.state.value}")
    if now < approval.expires_at:
        reasons.append("NOT_YET_EXPIRED")
    return _decision(reasons)


def admit_experiment_start(
    experiment_id: str, approval_request_id: str, state: KernelState, now: datetime
) -> PolicyDecision:
    """Admission immediately before an experiment starts. Recomputes everything it relies on."""
    record = state.experiments.get(experiment_id)
    if record is None:
        return _decision(["UNKNOWN_EXPERIMENT"])
    reasons: list[str] = []
    experiment = record.experiment

    computed = classify_intervention(experiment.intervention)
    if computed.safety_class is SafetyClass.RED or record.safety_class is SafetyClass.RED:
        reasons.append("RED_FAIL_CLOSED")
        reasons.extend(computed.reason_codes)
    if record.safety_class != computed.safety_class:
        reasons.append("CLASSIFICATION_STALE")
    if record.status is not ExperimentStatus.APPROVED:
        reasons.append(f"EXPERIMENT_NOT_APPROVED:{record.status.value}")
    reasons += _unmet(record, state)

    approval = state.approvals.get(approval_request_id)
    if approval is None:
        reasons.append("NO_APPROVAL")
    else:
        if approval.experiment_id != experiment_id:
            reasons.append("APPROVAL_FOR_OTHER_EXPERIMENT")
        if approval.state is not ApprovalState.GRANTED:
            reasons.append(f"APPROVAL_NOT_GRANTED:{approval.state.value}")
        if approval.intervention_digest != intervention_digest(experiment.intervention):
            reasons.append("INTERVENTION_CHANGED_SINCE_APPROVAL")
        if approval.safety_class != computed.safety_class:
            reasons.append("APPROVAL_SAFETY_CLASS_STALE")
        if approval.consumed_by is not None:
            reasons.append("APPROVAL_ALREADY_USED")
        if now >= approval.expires_at:
            reasons.append("APPROVAL_EXPIRED")

    hypothesis = state.entities.get(experiment.hypothesis_id)
    if hypothesis is None or hypothesis.status is not LifecycleStatus.ACTIVE:
        reasons.append("HYPOTHESIS_INACTIVE")
    return _decision(reasons)
