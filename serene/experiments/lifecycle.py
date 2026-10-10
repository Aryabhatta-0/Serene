"""Pure N-of-1 experiment lifecycle steps (issues #24, #25, #26).

    EXPERIMENT_PROPOSED (A: agent/parent)
      -> EXPERIMENT_CLASSIFIED (GREEN/AMBER/RED, recomputed by admission)
         -> EXPERIMENT_BLOCKED            RED, or structural requirements unmet
      -> APPROVAL_REQUESTED               GREEN/AMBER only, bounded expiry
         -> APPROVAL_NUDGED               at most once, GREEN only
         -> APPROVAL_TIMED_OUT            parks; never approves
         -> APPROVAL_GRANTED / REJECTED   (A: parent, authenticated channel receipt)
      -> EXPERIMENT_STARTED               admission re-verifies safety + approval binding
      -> WAITING_FOR_OUTCOME              until started_at + duration + grace
         -> OUTCOME_REPORTED / TRIAL_RECORDED (A: parent/caregiver)
         -> EXPERIMENT_OUTCOME_TIMED_OUT  no outcome by the deadline: abandoned
      -> EXPERIMENT_COMPLETED / ABANDONED
      -> Promotion Gate (PROMOTION_GRANTED / PROMOTION_DENIED, 3 -> 4)

Every function here is a pure function of `KernelState` and `now` that returns
`EventDraft`s. Nothing is appended here and nothing is decided here that the
ledger's admission does not independently recompute.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

from serene.domain.base import new_id
from serene.domain.events import (
    ApprovalNudged,
    ApprovalRequested,
    ApprovalTimedOut,
    EventDraft,
    EventPayload,
    EventType,
    ExperimentBlocked,
    ExperimentClassified,
    ExperimentCompleted,
    ExperimentOutcomeTimedOut,
    ExperimentStarted,
    LearningStatusChanged,
    SafetyClass,
)
from serene.domain.values import (
    ActorKind,
    ActorRef,
    EpistemicLevel,
    SourceKind,
    SourceRef,
    VerificationStatus,
)
from serene.policies import approval, experiments, learning, promotion, safety
from serene.projections.state import (
    OPEN_APPROVAL_STATES,
    ApprovalState,
    ExperimentRecord,
    ExperimentStatus,
    KernelState,
)

APPROVAL_TTL: Final[dict[SafetyClass, timedelta]] = {
    SafetyClass.GREEN: timedelta(hours=48),
    SafetyClass.AMBER: timedelta(hours=72),
}
# A GREEN request is nudged once, after this fraction of its window has passed.
NUDGE_AFTER_FRACTION: Final = 2


class ExperimentPhase(StrEnum):
    PROPOSED = "PROPOSED"
    CLASSIFIED = "CLASSIFIED"
    BLOCKED = "BLOCKED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    WAITING_FOR_OUTCOME = "WAITING_FOR_OUTCOME"
    OUTCOME_OVERDUE = "OUTCOME_OVERDUE"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"
    PARKED_UNRESOLVED = "PARKED_UNRESOLVED"


@dataclass(frozen=True, slots=True)
class LifecycleContext:
    """Who the lifecycle speaks as. Actors are the kernel's own POLICY / SYSTEM identities."""

    policy: ActorRef
    system: ActorRef
    new_source_id: Callable[[], str] = lambda: new_id("src")

    def __post_init__(self) -> None:
        if self.policy.kind is not ActorKind.POLICY or self.system.kind is not ActorKind.SYSTEM:
            raise ValueError("lifecycle steps are appended only as POLICY / SYSTEM")

    def draft(
        self,
        event_type: EventType,
        actor: ActorRef,
        payload: EventPayload,
        state: KernelState,
        now: datetime,
        derived_from: tuple[str, ...] = (),
    ) -> EventDraft:
        if state.child_id is None:
            raise ValueError("lifecycle steps need a non-empty child stream")
        return EventDraft(
            event_type=event_type,
            child_id=state.child_id,
            source=SourceRef(kind=SourceKind.KERNEL, source_id=self.new_source_id()),
            actor=actor,
            occurred_at=now,
            derived_from=derived_from,
            verification_status=VerificationStatus.NOT_APPLICABLE,
            payload=payload,
        )


def _origin(state: KernelState, experiment_id: str) -> tuple[str, ...]:
    record = state.entities.get(experiment_id)
    return () if record is None else (record.introduced_by,)


def experiment_phase(record: ExperimentRecord, now: datetime) -> ExperimentPhase:
    """Presentation phase, including the time-derived WAITING_FOR_OUTCOME / OUTCOME_OVERDUE."""
    if record.status is ExperimentStatus.STARTED:
        due = experiments.outcome_due_at(record)
        if due is not None and now >= due:
            return ExperimentPhase.OUTCOME_OVERDUE
        return ExperimentPhase.WAITING_FOR_OUTCOME
    return ExperimentPhase(record.status.value)


# ------------------------------------------------------------------ classification
def classify(
    experiment_id: str, state: KernelState, now: datetime, ctx: LifecycleContext
) -> list[EventDraft]:
    """EXPERIMENT_CLASSIFIED, followed by EXPERIMENT_BLOCKED when RED or structurally unfit.

    Append in order; the second draft is admissible after the first.
    """
    record = state.experiments[experiment_id]
    if record.status is not ExperimentStatus.PROPOSED:
        return []
    experiment = record.experiment
    decision = safety.classify_intervention(experiment.intervention)
    origin = _origin(state, experiment_id)
    drafts = [
        ctx.draft(
            EventType.EXPERIMENT_CLASSIFIED,
            ctx.policy,
            ExperimentClassified(
                experiment_id=experiment_id,
                safety_class=decision.safety_class,
                intervention_digest=safety.intervention_digest(experiment.intervention),
                reason_codes=decision.reason_codes,
                policy_version=decision.policy_version,
            ),
            state,
            now,
            origin,
        )
    ]
    blockers: list[str] = []
    if decision.safety_class is SafetyClass.RED:
        blockers += ["RED_FAIL_CLOSED", *decision.reason_codes]
    blockers += experiments.requirement_violations(experiment, state)
    if blockers:
        drafts.append(
            ctx.draft(
                EventType.EXPERIMENT_BLOCKED,
                ctx.policy,
                ExperimentBlocked(
                    experiment_id=experiment_id,
                    reason_codes=tuple(dict.fromkeys(blockers)),
                    policy_version=experiments.POLICY_VERSION,
                ),
                state,
                now,
                origin,
            )
        )
    return drafts


# ------------------------------------------------------------------ approval
def request_approval(
    experiment_id: str,
    state: KernelState,
    now: datetime,
    ctx: LifecycleContext,
    *,
    requested_of: str,
    approval_request_id: str,
) -> EventDraft | None:
    """APPROVAL_REQUESTED for a classified GREEN/AMBER experiment; None if not eligible."""
    record = state.experiments[experiment_id]
    if record.status is not ExperimentStatus.CLASSIFIED:
        return None
    decision = safety.classify_intervention(record.experiment.intervention)
    if decision.safety_class is SafetyClass.RED:
        return None
    return ctx.draft(
        EventType.APPROVAL_REQUESTED,
        ctx.policy,
        ApprovalRequested(
            approval_request_id=approval_request_id,
            experiment_id=experiment_id,
            intervention_digest=safety.intervention_digest(record.experiment.intervention),
            safety_class=decision.safety_class,
            requested_of=requested_of,
            expires_at=now + APPROVAL_TTL[decision.safety_class],
        ),
        state,
        now,
        _origin(state, experiment_id),
    )


def nudge_due(state: KernelState, now: datetime, ctx: LifecycleContext) -> list[EventDraft]:
    """The single permitted nudge for open GREEN requests past the nudge point."""
    drafts: list[EventDraft] = []
    for apr_id, record in sorted(state.approvals.items()):
        if record.state not in OPEN_APPROVAL_STATES or record.nudges >= approval.MAX_NUDGES:
            continue
        if record.safety_class is not SafetyClass.GREEN or record.requested_at is None:
            continue
        nudge_at = record.requested_at + (record.expires_at - record.requested_at) / (
            NUDGE_AFTER_FRACTION
        )
        if nudge_at <= now < record.expires_at:
            drafts.append(
                ctx.draft(
                    EventType.APPROVAL_NUDGED,
                    ctx.system,
                    ApprovalNudged(approval_request_id=apr_id),
                    state,
                    now,
                    _origin(state, record.experiment_id),
                )
            )
    return drafts


def timeout_due(state: KernelState, now: datetime, ctx: LifecycleContext) -> list[EventDraft]:
    """Approval timeouts (park) and WAITING_FOR_OUTCOME deadlines (complete or time out)."""
    drafts: list[EventDraft] = []
    for apr_id, record in sorted(state.approvals.items()):
        if record.state in OPEN_APPROVAL_STATES and now >= record.expires_at:
            drafts.append(
                ctx.draft(
                    EventType.APPROVAL_TIMED_OUT,
                    ctx.system,
                    ApprovalTimedOut(approval_request_id=apr_id),
                    state,
                    now,
                    _origin(state, record.experiment_id),
                )
            )
    for exp_id, exp in sorted(state.experiments.items()):
        if exp.status is not ExperimentStatus.STARTED:
            continue
        due = experiments.outcome_due_at(exp)
        if due is None or now < due:
            continue
        if exp.outcome_ids:
            drafts.append(complete(exp_id, state, now, ctx))
        else:
            drafts.append(
                ctx.draft(
                    EventType.EXPERIMENT_OUTCOME_TIMED_OUT,
                    ctx.policy,
                    ExperimentOutcomeTimedOut(
                        experiment_id=exp_id,
                        outcome_due_at=due,
                        policy_version=experiments.POLICY_VERSION,
                    ),
                    state,
                    now,
                    _origin(state, exp_id),
                )
            )
    return drafts


# ------------------------------------------------------------------ run
def start_due(state: KernelState, now: datetime, ctx: LifecycleContext) -> list[EventDraft]:
    """EXPERIMENT_STARTED for approved experiments whose grant the start gate still admits."""
    drafts: list[EventDraft] = []
    for exp_id, exp in sorted(state.experiments.items()):
        if exp.status is not ExperimentStatus.APPROVED or exp.approval_request_id is None:
            continue
        grant = state.approvals.get(exp.approval_request_id)
        if grant is None or grant.state is not ApprovalState.GRANTED:
            continue
        if not approval.admit_experiment_start(
            exp_id, grant.approval_request_id, state, now
        ).allowed:
            continue  # admission would refuse; the reasons surface via `start_blockers`
        drafts.append(
            ctx.draft(
                EventType.EXPERIMENT_STARTED,
                ctx.policy,
                ExperimentStarted(
                    experiment_id=exp_id,
                    approval_request_id=grant.approval_request_id,
                    intervention_digest=safety.intervention_digest(exp.experiment.intervention),
                    policy_version=approval.POLICY_VERSION,
                ),
                state,
                now,
                _origin(state, exp_id),
            )
        )
    return drafts


def start_blockers(experiment_id: str, state: KernelState, now: datetime) -> tuple[str, ...]:
    exp = state.experiments[experiment_id]
    decision = approval.admit_experiment_start(
        experiment_id, exp.approval_request_id or "", state, now
    )
    return () if decision.allowed else decision.reason_codes


def complete(
    experiment_id: str, state: KernelState, now: datetime, ctx: LifecycleContext
) -> EventDraft:
    exp = state.experiments[experiment_id]
    return ctx.draft(
        EventType.EXPERIMENT_COMPLETED,
        ctx.policy,
        ExperimentCompleted(experiment_id=experiment_id, outcome_ids=tuple(exp.outcome_ids)),
        state,
        now,
        _origin(state, experiment_id),
    )


def promotion_after_completion(
    experiment_id: str, state: KernelState, now: datetime, ctx: LifecycleContext
) -> EventDraft | None:
    """Hand a completed experiment's hypothesis to the Promotion Gate (3 -> 4)."""
    exp = state.experiments[experiment_id]
    if exp.status is not ExperimentStatus.COMPLETED:
        return None
    hypothesis_id = exp.experiment.hypothesis_id
    if state.hypothesis_levels.get(hypothesis_id) is not EpistemicLevel.HYPOTHESIS:
        return None
    event_type, payload = promotion.decide_promotion(
        hypothesis_id, EpistemicLevel.HYPOTHESIS, EpistemicLevel.TESTED_HYPOTHESIS, state
    )
    return ctx.draft(event_type, ctx.policy, payload, state, now, _origin(state, experiment_id))


# ------------------------------------------------------------------ learning validity
def learning_validity_due(
    state: KernelState, now: datetime, ctx: LifecycleContext
) -> list[EventDraft]:
    """LEARNING_STATUS_CHANGED for every learning whose validity has lapsed (issue #20)."""
    drafts: list[EventDraft] = []
    for lrn_id, record in sorted(state.learnings.items()):
        step = learning.due_transition(record, state, now)
        if step is None:
            continue
        to_status, reasons = step
        drafts.append(
            ctx.draft(
                EventType.LEARNING_STATUS_CHANGED,
                ctx.policy,
                LearningStatusChanged(
                    learning_id=lrn_id,
                    from_status=record.status,
                    to_status=to_status,
                    reason_codes=reasons,
                ),
                state,
                now,
                (state.entities[lrn_id].introduced_by,),
            )
        )
    return drafts
