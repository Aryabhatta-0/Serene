"""Deterministic fold of a child's ledger into kernel read state (issue #6).

`KernelState` is disposable: it is always rebuildable from the ledger by
`replay`. Policies read it to make decisions; nothing writes it except
`apply_event`, and `apply_event` only ever consumes already-admitted events.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from serene.domain.base import id_prefix
from serene.domain.entities import (
    Experiment,
    InvestigationStatus,
    LearningStatus,
)
from serene.domain.events import (
    GENESIS_HASH,
    ApprovalGranted,
    ApprovalNudged,
    ApprovalRejected,
    ApprovalRequested,
    ApprovalTimedOut,
    DomainEvent,
    EventType,
    EvidenceAcquired,
    EvidenceRejected,
    EvidenceVerified,
    ExperimentAbandoned,
    ExperimentBlocked,
    ExperimentClassified,
    ExperimentCompleted,
    ExperimentProposed,
    ExperimentStarted,
    HypothesisProposed,
    HypothesisRefuted,
    HypothesisSuperseded,
    InvestigationOpened,
    InvestigationStatusChanged,
    LearningRecorded,
    LearningStatusChanged,
    LearningSuperseded,
    MemoryPatchCommitted,
    MemoryPatchProposed,
    MemoryPatchRejected,
    ObservationReported,
    ObservationStructured,
    OutcomeReported,
    PatternProposed,
    PromotionDecisionRecord,
    SafetyClass,
    TrialRecorded,
)
from serene.domain.values import EpistemicLevel, VerificationStatus


class LifecycleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REFUTED = "REFUTED"


class ExperimentStatus(StrEnum):
    PROPOSED = "PROPOSED"
    CLASSIFIED = "CLASSIFIED"
    BLOCKED = "BLOCKED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"
    PARKED_UNRESOLVED = "PARKED_UNRESOLVED"


class ApprovalState(StrEnum):
    PENDING = "PENDING"
    NUDGED = "NUDGED"
    GRANTED = "GRANTED"
    REJECTED = "REJECTED"
    PARKED_UNRESOLVED = "PARKED_UNRESOLVED"


OPEN_APPROVAL_STATES = frozenset({ApprovalState.PENDING, ApprovalState.NUDGED})


@dataclass(slots=True)
class EntityRecord:
    entity_id: str
    kind: str
    level: EpistemicLevel | None
    introduced_by: str
    verification_status: VerificationStatus
    entity: Any
    status: LifecycleStatus = LifecycleStatus.ACTIVE
    superseded_by: str | None = None


@dataclass(slots=True)
class ExperimentRecord:
    experiment: Experiment
    status: ExperimentStatus = ExperimentStatus.PROPOSED
    safety_class: SafetyClass | None = None
    intervention_digest: str | None = None
    approval_request_id: str | None = None
    outcome_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ApprovalRecord:
    approval_request_id: str
    experiment_id: str
    intervention_digest: str
    safety_class: SafetyClass
    requested_of: str
    expires_at: datetime
    state: ApprovalState = ApprovalState.PENDING
    nudges: int = 0
    consumed_by: str | None = None


@dataclass(slots=True)
class PromotionRecord:
    event_id: str
    subject_id: str
    from_level: EpistemicLevel
    to_level: EpistemicLevel
    granted: bool
    consumed_by: str | None = None


@dataclass(slots=True)
class LearningRecord:
    learning_id: str
    status: LearningStatus
    valid_from: datetime
    review_after: datetime
    contexts: tuple[str, ...]
    hypothesis_id: str
    superseded_by: str | None = None


@dataclass(slots=True)
class KernelState:
    child_id: str | None = None
    last_sequence: int = 0
    last_event_hash: str = GENESIS_HASH
    event_ids: dict[str, EventType] = field(default_factory=dict)
    entities: dict[str, EntityRecord] = field(default_factory=dict)
    hypothesis_levels: dict[str, EpistemicLevel] = field(default_factory=dict)
    investigations: dict[str, InvestigationStatus] = field(default_factory=dict)
    investigation_hypotheses: dict[str, list[str]] = field(default_factory=dict)
    experiments: dict[str, ExperimentRecord] = field(default_factory=dict)
    approvals: dict[str, ApprovalRecord] = field(default_factory=dict)
    promotions: dict[str, PromotionRecord] = field(default_factory=dict)
    learnings: dict[str, LearningRecord] = field(default_factory=dict)
    memory_patches: dict[str, str] = field(default_factory=dict)

    def clone(self) -> KernelState:
        return copy.deepcopy(self)

    def verification_of(self, entity_id: str) -> VerificationStatus | None:
        record = self.entities.get(entity_id)
        return None if record is None else record.verification_status

    def level_of(self, entity_id: str) -> EpistemicLevel | None:
        if id_prefix(entity_id) == "hyp":
            return self.hypothesis_levels.get(entity_id)
        record = self.entities.get(entity_id)
        return None if record is None else record.level


def _register(state: KernelState, entity: Any, event: DomainEvent) -> None:
    state.entities[entity.entity_id] = EntityRecord(
        entity_id=entity.entity_id,
        kind=id_prefix(entity.entity_id),
        level=type(entity).level,
        introduced_by=event.event_id,
        verification_status=event.verification_status,
        entity=entity,
    )


def apply_event(state: KernelState, event: DomainEvent) -> None:
    """Fold one admitted event into `state` (in place). Deterministic and total."""
    payload = event.typed_payload()
    state.child_id = event.child_id
    state.last_sequence = event.sequence
    state.last_event_hash = event.event_hash
    state.event_ids[event.event_id] = event.event_type

    match payload:
        case ObservationReported(evidence=evidence) | EvidenceAcquired(evidence=evidence):
            _register(state, evidence, event)
        case EvidenceVerified(evidence_id=evidence_id):
            state.entities[evidence_id].verification_status = VerificationStatus.VERIFIED
        case EvidenceRejected(evidence_id=evidence_id):
            state.entities[evidence_id].verification_status = VerificationStatus.REJECTED
        case ObservationStructured(observation=entity) | PatternProposed(pattern=entity):
            _register(state, entity, event)
        case HypothesisProposed(hypothesis=hypothesis):
            _register(state, hypothesis, event)
            state.hypothesis_levels[hypothesis.hypothesis_id] = EpistemicLevel.HYPOTHESIS
            state.investigation_hypotheses.setdefault(hypothesis.investigation_id, []).append(
                hypothesis.hypothesis_id
            )
        case HypothesisSuperseded(hypothesis_id=hyp_id, superseded_by=successor):
            record = state.entities[hyp_id]
            record.status = LifecycleStatus.SUPERSEDED
            record.superseded_by = successor
        case HypothesisRefuted(hypothesis_id=hyp_id):
            state.entities[hyp_id].status = LifecycleStatus.REFUTED
        case PromotionDecisionRecord():
            granted = event.event_type is EventType.PROMOTION_GRANTED
            state.promotions[event.event_id] = PromotionRecord(
                event_id=event.event_id,
                subject_id=payload.subject_id,
                from_level=payload.from_level,
                to_level=payload.to_level,
                granted=granted,
            )
            if granted and payload.subject_id in state.hypothesis_levels:
                state.hypothesis_levels[payload.subject_id] = payload.to_level
        case InvestigationOpened(investigation=investigation):
            _register(state, investigation, event)
            state.investigations[investigation.investigation_id] = InvestigationStatus.OPEN
        case InvestigationStatusChanged(investigation_id=inv_id, to_status=to_status):
            state.investigations[inv_id] = to_status
        case ExperimentProposed(experiment=experiment):
            _register(state, experiment, event)
            state.experiments[experiment.experiment_id] = ExperimentRecord(experiment=experiment)
        case ExperimentClassified():
            record_e = state.experiments[payload.experiment_id]
            record_e.safety_class = payload.safety_class
            record_e.intervention_digest = payload.intervention_digest
            record_e.status = ExperimentStatus.CLASSIFIED
        case ExperimentBlocked(experiment_id=exp_id):
            state.experiments[exp_id].status = ExperimentStatus.BLOCKED
        case ApprovalRequested():
            state.approvals[payload.approval_request_id] = ApprovalRecord(
                approval_request_id=payload.approval_request_id,
                experiment_id=payload.experiment_id,
                intervention_digest=payload.intervention_digest,
                safety_class=payload.safety_class,
                requested_of=payload.requested_of,
                expires_at=payload.expires_at,
            )
            record_e = state.experiments[payload.experiment_id]
            record_e.status = ExperimentStatus.AWAITING_APPROVAL
            record_e.approval_request_id = payload.approval_request_id
        case ApprovalNudged(approval_request_id=apr_id):
            approval = state.approvals[apr_id]
            approval.state = ApprovalState.NUDGED
            approval.nudges += 1
        case ApprovalGranted(approval_request_id=apr_id):
            approval = state.approvals[apr_id]
            approval.state = ApprovalState.GRANTED
            state.experiments[approval.experiment_id].status = ExperimentStatus.APPROVED
        case ApprovalRejected(approval_request_id=apr_id):
            approval = state.approvals[apr_id]
            approval.state = ApprovalState.REJECTED
            state.experiments[approval.experiment_id].status = ExperimentStatus.ABANDONED
        case ApprovalTimedOut(approval_request_id=apr_id):
            approval = state.approvals[apr_id]
            approval.state = ApprovalState.PARKED_UNRESOLVED
            state.experiments[approval.experiment_id].status = ExperimentStatus.PARKED_UNRESOLVED
        case ExperimentStarted(experiment_id=exp_id, approval_request_id=apr_id):
            state.experiments[exp_id].status = ExperimentStatus.STARTED
            state.approvals[apr_id].consumed_by = event.event_id
        case TrialRecorded(trial=trial):
            _register(state, trial, event)
        case OutcomeReported(outcome=outcome):
            _register(state, outcome, event)
            state.experiments[outcome.experiment_id].outcome_ids.append(outcome.outcome_id)
        case ExperimentCompleted(experiment_id=exp_id):
            state.experiments[exp_id].status = ExperimentStatus.COMPLETED
        case ExperimentAbandoned(experiment_id=exp_id):
            state.experiments[exp_id].status = ExperimentStatus.ABANDONED
        case LearningRecorded(learning=learning, promotion_event_id=promotion_id):
            _register(state, learning, event)
            state.promotions[promotion_id].consumed_by = event.event_id
            state.learnings[learning.learning_id] = LearningRecord(
                learning_id=learning.learning_id,
                status=LearningStatus.ACTIVE,
                valid_from=learning.validity.valid_from,
                review_after=learning.validity.review_after,
                contexts=learning.scope.contexts,
                hypothesis_id=learning.hypothesis_id,
            )
        case LearningStatusChanged(learning_id=lrn_id, to_status=to_status):
            state.learnings[lrn_id].status = to_status
        case LearningSuperseded(learning_id=lrn_id, superseded_by=successor):
            state.learnings[lrn_id].status = LearningStatus.DEPRECATED
            state.learnings[lrn_id].superseded_by = successor
            state.entities[lrn_id].superseded_by = successor
            state.entities[lrn_id].status = LifecycleStatus.SUPERSEDED
        case MemoryPatchProposed(patch=patch):
            _register(state, patch, event)
            state.memory_patches[patch.patch_id] = "PROPOSED"
        case MemoryPatchCommitted(patch_id=patch_id):
            state.memory_patches[patch_id] = "COMMITTED"
        case MemoryPatchRejected(patch_id=patch_id):
            state.memory_patches[patch_id] = "REJECTED"
        case _:
            # Event types that carry no read-state (e.g. requests) still advance the cursor.
            pass


def replay(events: Iterable[DomainEvent]) -> KernelState:
    state = KernelState()
    for event in events:
        apply_event(state, event)
    return state
