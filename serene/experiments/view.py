"""Read view of experiments and their approvals for the Experiments surface (issue #37).

`build_experiments_view` is a pure function of `KernelState` and `now`. It
carries no authority: it reports each experiment's intervention, safety class,
reversibility, approval request, lifecycle phase, outcomes and promotion
result as the ledger recorded them. Whether a parent can still decide is
reported (`decision_open`) so the surface can offer the choice, but the
decision itself goes through `serene.adapters.web.WebApprovalChannel` and the
ledger's admission, which recompute every rule.

Privacy: typed entity ids, intervention and outcome text, and reason codes
only. There is no child id and no actor id (the approval's `requested_of` and
an outcome's reporter are reduced to an actor kind).
"""

from __future__ import annotations

from datetime import datetime
from typing import Final, Literal, Self

from pydantic import Field, model_validator

from serene.domain.base import (
    ApprovalRequestId,
    ExperimentId,
    HypothesisId,
    InvestigationId,
    KernelModel,
    OutcomeId,
    ReasonCode,
    Sha256Hex,
    ShortText,
    Tag,
    UtcDatetime,
)
from serene.domain.entities import Burden, InterventionCategory, OutcomeResult
from serene.domain.events import SafetyClass
from serene.domain.values import ActorKind, EpistemicLevel, SourceKind
from serene.experiments.lifecycle import ExperimentPhase, experiment_phase
from serene.policies.experiments import outcome_due_at
from serene.projections.state import (
    OPEN_APPROVAL_STATES,
    ApprovalState,
    ExperimentRecord,
    ExperimentStatus,
    KernelState,
)

VIEW_VERSION: Final = "experiments-view/1"


class InterventionView(KernelModel):
    category: InterventionCategory
    description: ShortText
    reversible: bool
    max_duration_days: int = Field(ge=1, le=365)
    burden: Burden


class ApprovalView(KernelModel):
    approval_request_id: ApprovalRequestId
    state: ApprovalState
    safety_class: SafetyClass
    # The exact intervention the request binds; a grant must quote it back.
    intervention_digest: Sha256Hex
    requested_at: UtcDatetime | None
    expires_at: UtcDatetime
    nudges: int = Field(ge=0)
    decided_at: UtcDatetime | None
    decided_via: SourceKind | None
    # The request is open, unexpired and its experiment still awaits a decision.
    decision_open: bool

    @model_validator(mode="after")
    def _red_is_never_open(self) -> Self:
        if self.safety_class is SafetyClass.RED and self.decision_open:
            raise ValueError("a RED request can never be open for a decision")
        return self


class OutcomeView(KernelModel):
    outcome_id: OutcomeId
    result: OutcomeResult
    summary: ShortText
    reported_at: UtcDatetime
    reported_by: ActorKind


class PromotionView(KernelModel):
    granted: bool
    from_level: EpistemicLevel
    to_level: EpistemicLevel
    reason_codes: tuple[ReasonCode, ...]
    recorded_at: UtcDatetime | None


class ExperimentView(KernelModel):
    experiment_id: ExperimentId
    hypothesis_id: HypothesisId
    hypothesis_statement: ShortText | None
    investigation_id: InvestigationId
    intervention: InterventionView
    comparison: ShortText
    outcome_measure: ShortText
    contexts: tuple[Tag, ...]
    safety_class: SafetyClass | None
    classification_reasons: tuple[ReasonCode, ...]
    phase: ExperimentPhase
    proposed_at: UtcDatetime | None
    started_at: UtcDatetime | None
    outcome_due_at: UtcDatetime | None
    ended_at: UtcDatetime | None
    blocked_reasons: tuple[ReasonCode, ...]
    abandoned_reasons: tuple[ReasonCode, ...]
    outcome_timed_out: bool
    approval: ApprovalView | None
    outcomes: tuple[OutcomeView, ...]
    promotion: PromotionView | None

    @model_validator(mode="after")
    def _state_is_explained(self) -> Self:
        if self.phase is ExperimentPhase.BLOCKED and not self.blocked_reasons:
            raise ValueError("a blocked experiment carries the reasons it was blocked")
        if self.phase is ExperimentPhase.COMPLETED and not self.outcomes:
            raise ValueError("a completed experiment carries its outcomes")
        if self.safety_class is SafetyClass.RED and self.phase not in (
            ExperimentPhase.BLOCKED,
            ExperimentPhase.CLASSIFIED,
        ):
            raise ValueError("a RED experiment can only be classified or blocked")
        if self.approval is not None and self.approval.safety_class != self.safety_class:
            raise ValueError("the request's safety class must be the experiment's")
        open_decision = self.approval is not None and self.approval.decision_open
        if open_decision and self.phase is not ExperimentPhase.AWAITING_APPROVAL:
            raise ValueError("only an experiment awaiting approval has an open decision")
        return self


class ExperimentsView(KernelModel):
    version: Literal["experiments-view/1"] = VIEW_VERSION
    ledger_head: Sha256Hex
    as_of: UtcDatetime
    experiments: tuple[ExperimentView, ...]


def _approval(record: ExperimentRecord, state: KernelState, now: datetime) -> ApprovalView | None:
    if record.approval_request_id is None:
        return None
    apr = state.approvals[record.approval_request_id]
    return ApprovalView(
        approval_request_id=apr.approval_request_id,
        state=apr.state,
        safety_class=apr.safety_class,
        intervention_digest=apr.intervention_digest,
        requested_at=apr.requested_at,
        expires_at=apr.expires_at,
        nudges=apr.nudges,
        decided_at=apr.decided_at,
        decided_via=None if apr.decided_via is None else SourceKind(apr.decided_via),
        decision_open=(
            apr.state in OPEN_APPROVAL_STATES
            and now < apr.expires_at
            and record.status is ExperimentStatus.AWAITING_APPROVAL
            and apr.safety_class is not SafetyClass.RED
        ),
    )


def _promotion(record: ExperimentRecord, state: KernelState) -> PromotionView | None:
    """The Promotion Gate decision handed this experiment (it cites the proposal)."""
    exp = record.experiment
    proposal = state.entities[exp.experiment_id].introduced_by
    decisions = [
        p
        for p in state.promotions.values()
        if p.subject_id == exp.hypothesis_id and proposal in p.derived_from
    ]
    if not decisions:
        return None
    last = decisions[-1]  # insertion order is ledger order
    return PromotionView(
        granted=last.granted,
        from_level=last.from_level,
        to_level=last.to_level,
        reason_codes=last.reason_codes,
        recorded_at=last.recorded_at,
    )


def _experiment(record: ExperimentRecord, state: KernelState, now: datetime) -> ExperimentView:
    exp = record.experiment
    iv = exp.intervention
    hypothesis = state.entities.get(exp.hypothesis_id)
    outcomes = tuple(
        OutcomeView(
            outcome_id=o.outcome_id,
            result=o.result,
            summary=o.summary,
            reported_at=o.reported_at,
            reported_by=o.reported_by.kind,
        )
        for o in (state.entities[oid].entity for oid in record.outcome_ids)
    )
    return ExperimentView(
        experiment_id=exp.experiment_id,
        hypothesis_id=exp.hypothesis_id,
        hypothesis_statement=None if hypothesis is None else hypothesis.entity.statement,
        investigation_id=exp.investigation_id,
        intervention=InterventionView(
            category=iv.category,
            description=iv.description,
            reversible=iv.reversible,
            max_duration_days=iv.max_duration_days,
            burden=iv.burden,
        ),
        comparison=exp.comparison,
        outcome_measure=exp.outcome_measure,
        contexts=exp.scope.contexts,
        safety_class=record.safety_class,
        classification_reasons=record.classification_reasons,
        phase=experiment_phase(record, now),
        proposed_at=state.entities[exp.experiment_id].introduced_at,
        started_at=record.started_at,
        outcome_due_at=outcome_due_at(record),
        ended_at=record.ended_at,
        blocked_reasons=record.blocked_reasons,
        abandoned_reasons=record.abandoned_reasons,
        outcome_timed_out=record.outcome_timed_out,
        approval=_approval(record, state, now),
        outcomes=outcomes,
        promotion=_promotion(record, state),
    )


def build_experiments_view(state: KernelState, now: datetime) -> ExperimentsView:
    position = {event_id: i for i, event_id in enumerate(state.event_ids)}
    records = sorted(
        state.experiments.values(),
        key=lambda r: position[state.entities[r.experiment.experiment_id].introduced_by],
        reverse=True,  # newest proposal first
    )
    return ExperimentsView(
        ledger_head=state.last_event_hash,
        as_of=now,
        experiments=tuple(_experiment(r, state, now) for r in records),
    )


__all__ = [
    "ApprovalView",
    "ExperimentView",
    "ExperimentsView",
    "InterventionView",
    "OutcomeView",
    "PromotionView",
    "build_experiments_view",
]
