"""Parent approval lifecycle and experiment-start admission (issues #23, #24, #25).

Approval exists only as ledger state: an APPROVAL_GRANTED event appended by the
requested parent, over an authenticated channel, bound to the exact intervention
digest, before expiry, and used at most once. Model text saying "approved" has
no path into this state. RED fails closed even if a grant exists.
"""

from __future__ import annotations

from datetime import datetime
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
from serene.policies.safety import classify_intervention, intervention_digest
from serene.projections.state import (
    OPEN_APPROVAL_STATES,
    ApprovalState,
    ExperimentStatus,
    KernelState,
    LifecycleStatus,
)

POLICY_VERSION: Final = "approval/1"
MAX_NUDGES: Final = 1


def _decision(reasons: list[str]) -> PolicyDecision:
    return PolicyDecision.from_reasons(reasons, POLICY_VERSION)


def check_approval_request(payload: ApprovalRequested, state: KernelState) -> PolicyDecision:
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
    if isinstance(payload, ApprovalGranted):
        if approval.safety_class is SafetyClass.RED:
            reasons.append("RED_CANNOT_BE_APPROVED")
        if payload.intervention_digest != approval.intervention_digest:
            reasons.append("INTERVENTION_DIGEST_MISMATCH")
        if payload.acknowledged_safety_class != approval.safety_class:
            reasons.append("SAFETY_CLASS_NOT_ACKNOWLEDGED")
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
        if approval.consumed_by is not None:
            reasons.append("APPROVAL_ALREADY_USED")
        if now >= approval.expires_at:
            reasons.append("APPROVAL_EXPIRED")

    hypothesis = state.entities.get(experiment.hypothesis_id)
    if hypothesis is None or hypothesis.status is not LifecycleStatus.ACTIVE:
        reasons.append("HYPOTHESIS_INACTIVE")
    return _decision(reasons)
