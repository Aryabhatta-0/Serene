"""Stateful admission for every ledger append (fail closed).

`admission_violations` is consulted by the ledger *before* an event is sealed.
It recomputes every decision it depends on from current ledger state, so even a
POLICY-attributed event cannot record a grant, classification or start that
the deterministic policies would not themselves produce.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from serene.domain.canonical import sha256_hex
from serene.domain.entities import (
    TERMINAL_INVESTIGATION_STATUSES,
    Burden,
    Evidence,
    EvidenceKind,
    Intervention,
    InterventionCategory,
    InvestigationPhase,
    InvestigationStatus,
    LearningStatus,
    OutcomeResult,
)
from serene.domain.events import (
    AcquisitionMode,
    ApprovalGranted,
    ApprovalNudged,
    ApprovalRejected,
    ApprovalRequested,
    ApprovalTimedOut,
    DreamStage,
    EventDraft,
    EventType,
    EvidenceAcquired,
    EvidenceAcquisitionFailed,
    EvidenceRejected,
    EvidenceRequested,
    EvidenceVerified,
    ExperimentAbandoned,
    ExperimentBlocked,
    ExperimentClassified,
    ExperimentCompleted,
    ExperimentOutcomeTimedOut,
    ExperimentProposed,
    ExperimentStarted,
    HypothesisProposed,
    HypothesisRefuted,
    HypothesisSuperseded,
    InformationValue,
    InvestigationOpened,
    InvestigationPhaseChanged,
    InvestigationStatusChanged,
    LearningRecorded,
    LearningStatusChanged,
    LearningSuperseded,
    MemoryDreamStageRecorded,
    MemoryPatchCommitted,
    MemoryPatchProposed,
    MemoryPatchRejected,
    MemoryPatchReviewed,
    ObservationReported,
    ObservationStructured,
    ObservationStructuringFailed,
    OutcomeReported,
    PatternProposed,
    PromotionDecisionRecord,
    SafetyClass,
    TrialRecorded,
)
from serene.domain.values import AUTHENTICATED_CHANNELS, EpistemicLevel, VerificationStatus
from serene.lineage.provenance import provenance_violations
from serene.policies import approval, investigation, memory_review, promotion, safety
from serene.policies.decision import PolicyDecision
from serene.policies.experiments import outcome_due_at
from serene.policies.external_evidence import (
    domain_allowed,
    external_verification_violations,
    host_of,
)
from serene.policies.learning import LEARNING_TRANSITIONS, check_status_change
from serene.projections.state import ExperimentStatus, KernelState, LifecycleStatus

_I = InvestigationStatus
INVESTIGATION_TRANSITIONS: Final[dict[InvestigationStatus, frozenset[InvestigationStatus]]] = {
    _I.OPEN: frozenset({_I.GATHERING_EVIDENCE, _I.PARKED_UNRESOLVED, _I.CLOSED}),
    _I.GATHERING_EVIDENCE: frozenset(
        {_I.AWAITING_APPROVAL, _I.PARKED_UNRESOLVED, _I.RESOLVED, _I.CLOSED}
    ),
    _I.AWAITING_APPROVAL: frozenset(
        {_I.EXPERIMENTING, _I.GATHERING_EVIDENCE, _I.PARKED_UNRESOLVED, _I.CLOSED}
    ),
    _I.EXPERIMENTING: frozenset({_I.GATHERING_EVIDENCE, _I.PARKED_UNRESOLVED, _I.RESOLVED}),
    _I.PARKED_UNRESOLVED: frozenset({_I.GATHERING_EVIDENCE, _I.CLOSED}),
    _I.RESOLVED: frozenset(),
    _I.CLOSED: frozenset(),
}

__all__ = ["INVESTIGATION_TRANSITIONS", "LEARNING_TRANSITIONS", "admission_violations"]

_EXTERNAL_EVIDENCE = frozenset({EvidenceKind.DOCUMENT, EvidenceKind.BROWSER_CAPTURE})


def _reasons(decision: PolicyDecision) -> list[str]:
    return [] if decision.allowed else list(decision.reason_codes)


def _check_evidence(draft: EventDraft, ev: Evidence, state: KernelState) -> list[str]:
    reasons: list[str] = []
    if ev.evidence_id in state.entities:
        reasons.append("DUPLICATE_ENTITY")
    if ev.child_id != draft.child_id:
        reasons.append("CHILD_MISMATCH")
    if sha256_hex(ev.content.encode("utf-8")) != ev.content_digest:
        reasons.append("CONTENT_DIGEST_MISMATCH")
    if ev.provenance.verification_status != draft.verification_status:
        reasons.append("VERIFICATION_STATUS_MISMATCH")
    if ev.source != draft.source:
        reasons.append("SOURCE_MISMATCH")
    return reasons


def _undecided_patch(patch_id: str, state: KernelState) -> list[str]:
    patch_status = state.memory_patches.get(patch_id)
    if patch_status is None:
        return ["UNKNOWN_PATCH"]
    if patch_status != "PROPOSED":
        return [f"ALREADY_DECIDED:{patch_status}"]
    return []


def _check_answer(request_id: str, state: KernelState) -> list[str]:
    record = state.evidence_requests.get(request_id)
    if record is None:
        return ["UNKNOWN_EVIDENCE_REQUEST"]
    reasons: list[str] = []
    if record.request.acquisition_mode is not AcquisitionMode.ASK_PARENT:
        reasons.append("REQUEST_NOT_A_QUESTION")
    if not record.open:
        reasons.append("REQUEST_NOT_OPEN")
    return reasons


def _check_acquired_for_request(ev: Evidence, request_id: str, state: KernelState) -> list[str]:
    record = state.evidence_requests.get(request_id)
    if record is None:
        return ["UNKNOWN_EVIDENCE_REQUEST"]
    reasons: list[str] = []
    if record.request.acquisition_mode is not AcquisitionMode.BROWSE:
        reasons.append("REQUEST_NOT_A_BROWSE_REQUEST")
    if record.exhausted:
        reasons.append("REQUEST_EXHAUSTED")
    if not domain_allowed(host_of(ev.source.uri), record.request.allowed_domains):
        reasons.append("SOURCE_DOMAIN_NOT_ALLOWED")
    return reasons


_VALUE_RANK: Final = {InformationValue.HIGH: 0, InformationValue.MEDIUM: 1, InformationValue.LOW: 2}


def _check_evidence_request(p: EvidenceRequested, state: KernelState) -> list[str]:
    """The recorded request is code's decision, so admission re-derives what it can.

    Only SYSTEM/POLICY may record one (taxonomy). Independently of who wrote it, the
    request must be well-formed for its mode, ask nothing already asked, carry an
    information value its own predictions justify (never LOW, never inflated), and an
    ASK_PARENT question must pass the same RED screen the selection policy applies.
    """
    inv = p.investigation_id
    reasons = investigation.investigation_accepts_work(inv, state)
    if p.request_id in state.evidence_requests:
        reasons.append("DUPLICATE_EVIDENCE_REQUEST")
    phase = state.investigation_phases.get(inv)
    if phase is not None and phase is not InvestigationPhase.NEEDS_EVIDENCE:
        reasons.append(f"WRONG_PHASE:{phase.value}")
    if any(record.open for record in investigation.requests_of(inv, state)):
        reasons.append("OPEN_REQUEST_OUTSTANDING")
    browse_bounds = bool(p.allowed_domains) or p.subject is not None
    if p.acquisition_mode is None:
        reasons.append("ACQUISITION_MODE_REQUIRED")
    elif p.acquisition_mode is AcquisitionMode.ASK_PARENT:
        if p.question is None:
            reasons.append("QUESTION_REQUIRED")
        elif _question_is_red(p.question):
            reasons.append("UNSAFE_QUESTION")
        if browse_bounds or p.max_age_days is not None:
            reasons.append("QUESTION_WITH_BROWSE_BOUNDS")
    elif p.acquisition_mode is AcquisitionMode.BROWSE:
        if not p.allowed_domains or p.subject is None:
            reasons.append("BROWSE_BOUNDS_REQUIRED")
        if p.question is not None:
            reasons.append("BROWSE_WITH_QUESTION")
    asked = {f for r in investigation.requests_of(inv, state) for f in r.request.requested_fields}
    if set(p.requested_fields) <= asked:
        reasons.append("REDUNDANT_FIELDS")
    active = set(investigation.active_hypotheses(inv, state))
    predicted = [prediction.hypothesis_id for prediction in p.predictions]
    if len(predicted) != len(set(predicted)):
        reasons.append("DUPLICATE_PREDICTION")
    for hypothesis_id in predicted:
        if hypothesis_id not in active:
            reasons.append(f"PREDICTION_FOR_INACTIVE_HYPOTHESIS:{hypothesis_id}")
    # The selection policy scores over *live* hypotheses (a subset of active ones), so
    # its value can be at most the value recomputed here: anything higher is inflated.
    justified = investigation.information_value_of(p.predictions, frozenset(active))
    if justified is InformationValue.LOW:
        reasons.append("LOW_VALUE_REQUEST")
    elif _VALUE_RANK[p.information_value] < _VALUE_RANK[justified]:
        reasons.append(f"INFORMATION_VALUE_INFLATED:{justified.value}")
    return reasons


def _question_is_red(question: str) -> bool:
    """The RED screen MinimumDataPolicy applies: a question must not smuggle an intervention."""
    screened = safety.classify_intervention(
        Intervention(
            category=InterventionCategory.COMMUNICATION,
            description=question,
            reversible=True,
            max_duration_days=1,
            burden=Burden.LOW,
        )
    )
    return screened.safety_class is SafetyClass.RED


def admission_violations(draft: EventDraft, state: KernelState, now: datetime) -> list[str]:
    p = draft.payload
    et = draft.event_type
    match p:
        case ObservationReported(evidence=ev, request_id=request_id):
            reasons = _check_evidence(draft, ev, state)
            if request_id is not None:
                reasons += _check_answer(request_id, state)
            if ev.observer != draft.actor:
                reasons.append("OBSERVER_MISMATCH")
            if ev.kind in _EXTERNAL_EVIDENCE:
                reasons.append("EXTERNAL_EVIDENCE_MUST_BE_ACQUIRED")
            if (
                draft.verification_status is VerificationStatus.VERIFIED
                and draft.source.kind not in AUTHENTICATED_CHANNELS
            ):
                reasons.append("UNAUTHENTICATED_CHANNEL")
            return reasons
        case EvidenceAcquired(evidence=ev, request_id=request_id):
            reasons = _check_evidence(draft, ev, state)
            if ev.kind not in _EXTERNAL_EVIDENCE:
                reasons.append("ONLY_EXTERNAL_EVIDENCE_IS_ACQUIRED")
            if request_id is not None:
                reasons += _check_acquired_for_request(ev, request_id, state)
            return reasons
        case EvidenceVerified(evidence_id=evidence_id) | EvidenceRejected(evidence_id=evidence_id):
            status = state.verification_of(evidence_id)
            if status is None:
                return ["UNKNOWN_EVIDENCE"]
            if status is not VerificationStatus.UNVERIFIED:
                return [f"ALREADY_DECIDED:{status.value}"]
            entity = state.entities[evidence_id].entity
            if (
                isinstance(p, EvidenceVerified)
                and isinstance(entity, Evidence)
                and entity.kind in _EXTERNAL_EVIDENCE
            ):
                return external_verification_violations(entity, p.checks_passed, state)
            return []
        case EvidenceRequested():
            return _check_evidence_request(p, state)
        case EvidenceAcquisitionFailed(request_id=request_id, attempt=attempt):
            request_record = state.evidence_requests.get(request_id)
            if request_record is None:
                return ["UNKNOWN_EVIDENCE_REQUEST"]
            reasons = []
            if request_record.request.acquisition_mode is not AcquisitionMode.BROWSE:
                reasons.append("REQUEST_NOT_A_BROWSE_REQUEST")
            if not request_record.open:
                reasons.append("REQUEST_NOT_OPEN")
            if attempt != request_record.failed_attempts + 1:
                reasons.append(f"ATTEMPT_OUT_OF_ORDER:{request_record.failed_attempts}")
            return reasons
        case ObservationStructuringFailed(evidence_id=evidence_id, attempt=attempt):
            reasons = []
            evidence_record = state.entities.get(evidence_id)
            if evidence_record is None or evidence_record.kind != "evd":
                reasons.append("UNKNOWN_EVIDENCE")
            if attempt != state.structuring_failures.get(evidence_id, 0) + 1:
                reasons.append("ATTEMPT_OUT_OF_ORDER")
            return reasons
        case InvestigationPhaseChanged():
            return _reasons(investigation.check_phase_transition(p, state))
        case ObservationStructured(observation=entity) | PatternProposed(pattern=entity):
            return _reasons(promotion.check_introduction(entity, state))
        case HypothesisProposed(hypothesis=hypothesis):
            reasons = _reasons(promotion.check_introduction(hypothesis, state))
            return reasons + investigation.hypothesis_admission(hypothesis.investigation_id, state)
        case HypothesisSuperseded(hypothesis_id=old, superseded_by=new):
            reasons = []
            for hyp in (old, new):
                if hyp not in state.hypothesis_levels:
                    reasons.append(f"UNKNOWN_HYPOTHESIS:{hyp}")
            if old in state.entities and state.entities[old].status is not LifecycleStatus.ACTIVE:
                reasons.append("ALREADY_INACTIVE")
            if old == new:
                reasons.append("SELF_SUPERSESSION")
            return reasons
        case HypothesisRefuted(hypothesis_id=hyp, outcome_ids=outcome_ids):
            if hyp not in state.hypothesis_levels:
                return ["UNKNOWN_HYPOTHESIS"]
            results = [state.entities[o].entity.result for o in outcome_ids if o in state.entities]
            if len(results) != len(outcome_ids):
                return ["UNKNOWN_OUTCOME"]
            return [] if OutcomeResult.CONTRADICTS in results else ["NO_CONTRADICTING_OUTCOME"]
        case PromotionDecisionRecord():
            # Grants and denials alike must be exactly what the gate computes now.
            expected_type, expected = promotion.decide_promotion(
                p.subject_id, p.from_level, p.to_level, state
            )
            if et is EventType.PROMOTION_GRANTED and expected_type is not et:
                return list(expected.reason_codes)
            if et is EventType.PROMOTION_DENIED and expected_type is not et:
                return ["DENIAL_NOT_JUSTIFIED"]
            reasons = []
            if p.reason_codes != expected.reason_codes:
                reasons.append("REASON_CODES_MISMATCH")
            if p.policy_version != expected.policy_version:
                reasons.append("POLICY_VERSION_MISMATCH")
            if p.facts_digest != expected.facts_digest:
                reasons.append("STALE_FACTS_DIGEST")
            return reasons
        case InvestigationOpened(investigation=inv):
            reasons = []
            if inv.investigation_id in state.investigations:
                reasons.append("DUPLICATE_ENTITY")
            if inv.child_id != draft.child_id:
                reasons.append("CHILD_MISMATCH")
            return reasons
        case InvestigationStatusChanged(investigation_id=inv_id, from_status=frm, to_status=to):
            current = state.investigations.get(inv_id)
            if current is None:
                return ["UNKNOWN_INVESTIGATION"]
            if current != frm:
                return [f"STALE_STATUS:{current.value}"]
            if to not in INVESTIGATION_TRANSITIONS[current]:
                return [f"ILLEGAL_TRANSITION:{current.value}_TO_{to.value}"]
            return []
        case ExperimentProposed(experiment=exp):
            reasons = []
            if exp.experiment_id in state.entities:
                reasons.append("DUPLICATE_ENTITY")
            level = state.hypothesis_levels.get(exp.hypothesis_id)
            if level is None:
                reasons.append("UNKNOWN_HYPOTHESIS")
            elif state.entities[exp.hypothesis_id].status is not LifecycleStatus.ACTIVE:
                reasons.append("HYPOTHESIS_INACTIVE")
            if exp.hypothesis_id not in exp.provenance.derived_from:
                reasons.append("HYPOTHESIS_NOT_IN_LINEAGE")
            inv_status = state.investigations.get(exp.investigation_id)
            if inv_status is None or inv_status in TERMINAL_INVESTIGATION_STATUSES:
                reasons.append("INVESTIGATION_NOT_ACTIVE")
            reasons += provenance_violations(exp, state)
            return reasons
        case ExperimentClassified(experiment_id=exp_id):
            record = state.experiments.get(exp_id)
            if record is None:
                return ["UNKNOWN_EXPERIMENT"]
            computed = safety.classify_intervention(record.experiment.intervention)
            reasons = []
            if record.status is not ExperimentStatus.PROPOSED:
                reasons.append(f"ALREADY_CLASSIFIED:{record.status.value}")
            if p.safety_class != computed.safety_class:
                reasons.append("CLASSIFICATION_MISMATCH")
            if p.intervention_digest != safety.intervention_digest(record.experiment.intervention):
                reasons.append("INTERVENTION_DIGEST_MISMATCH")
            return reasons
        case ExperimentBlocked(experiment_id=exp_id):
            record = state.experiments.get(exp_id)
            if record is None:
                return ["UNKNOWN_EXPERIMENT"]
            if record.status not in {ExperimentStatus.PROPOSED, ExperimentStatus.CLASSIFIED}:
                return [f"CANNOT_BLOCK:{record.status.value}"]
            return []
        case ApprovalRequested():
            return _reasons(approval.check_approval_request(p, state, now))
        case ApprovalNudged():
            return _reasons(approval.check_approval_nudge(p, state))
        case ApprovalGranted() | ApprovalRejected():
            return _reasons(approval.check_approval_decision(draft, p, state, now))
        case ApprovalTimedOut():
            return _reasons(approval.check_approval_timeout(p, state, now))
        case ExperimentStarted(experiment_id=exp_id, approval_request_id=apr_id):
            reasons = _reasons(approval.admit_experiment_start(exp_id, apr_id, state, now))
            record = state.experiments.get(exp_id)
            if record is not None and p.intervention_digest != safety.intervention_digest(
                record.experiment.intervention
            ):
                reasons.append("INTERVENTION_DIGEST_MISMATCH")
            return reasons
        case TrialRecorded(trial=entity) | OutcomeReported(outcome=entity):
            reasons = []
            record = state.experiments.get(entity.experiment_id)
            if record is None:
                reasons.append("UNKNOWN_EXPERIMENT")
            elif record.status is not ExperimentStatus.STARTED:
                reasons.append(f"EXPERIMENT_NOT_RUNNING:{record.status.value}")
            else:
                due = outcome_due_at(record)
                if due is None or now >= due:
                    reasons.append("OUTCOME_WINDOW_CLOSED")
            if entity.entity_id in state.entities:
                reasons.append("DUPLICATE_ENTITY")
            reasons += provenance_violations(entity, state)
            for obs in entity.observation_ids:
                if state.level_of(obs) != EpistemicLevel.OBSERVATION:
                    reasons.append(f"NOT_AN_OBSERVATION:{obs}")
            return reasons
        case ExperimentCompleted(experiment_id=exp_id, outcome_ids=outcome_ids):
            record = state.experiments.get(exp_id)
            if record is None:
                return ["UNKNOWN_EXPERIMENT"]
            reasons = []
            if record.status is not ExperimentStatus.STARTED:
                reasons.append(f"EXPERIMENT_NOT_RUNNING:{record.status.value}")
            if set(outcome_ids) != set(record.outcome_ids):
                reasons.append("OUTCOMES_MISMATCH")
            return reasons
        case ExperimentAbandoned(experiment_id=exp_id):
            record = state.experiments.get(exp_id)
            if record is None:
                return ["UNKNOWN_EXPERIMENT"]
            if record.status in {ExperimentStatus.COMPLETED, ExperimentStatus.ABANDONED}:
                return [f"ALREADY_TERMINAL:{record.status.value}"]
            return []
        case ExperimentOutcomeTimedOut(experiment_id=exp_id, outcome_due_at=claimed_due):
            record = state.experiments.get(exp_id)
            if record is None:
                return ["UNKNOWN_EXPERIMENT"]
            if record.status is not ExperimentStatus.STARTED:
                return [f"NOT_WAITING_FOR_OUTCOME:{record.status.value}"]
            due = outcome_due_at(record)
            reasons = []
            if record.outcome_ids:
                reasons.append("OUTCOMES_REPORTED_COMPLETE_INSTEAD")
            if due is None or claimed_due != due:
                reasons.append("DEADLINE_MISMATCH")
            if due is None or now < due:
                reasons.append("NOT_YET_DUE")
            return reasons
        case LearningRecorded(learning=learning, promotion_event_id=promotion_id):
            return _reasons(promotion.check_learning(learning, promotion_id, state, now))
        case LearningStatusChanged():
            return _reasons(check_status_change(p, state, now))
        case LearningSuperseded(learning_id=old, superseded_by=new):
            reasons = [f"UNKNOWN_LEARNING:{x}" for x in (old, new) if x not in state.learnings]
            if old == new:
                reasons.append("SELF_SUPERSESSION")
            return reasons
        case MemoryPatchProposed(patch=patch):
            reasons = provenance_violations(patch, state)
            if patch.patch_id in state.memory_patches:
                reasons.append("DUPLICATE_ENTITY")
            if patch.required_level == EpistemicLevel.CONTEXTUAL_LEARNING:
                active = [
                    parent
                    for parent in patch.provenance.derived_from
                    if parent in state.learnings
                    and state.learnings[parent].status is LearningStatus.ACTIVE
                ]
                if not active:
                    reasons.append("REQUIRES_ACTIVE_LEARNING")
            return reasons
        case MemoryPatchReviewed(patch_id=patch_id):
            # The verdict must be exactly the deterministic Critic's, at this ledger head.
            reasons = _undecided_patch(patch_id, state)
            if reasons:
                return reasons
            if patch_id in state.memory_reviews:
                return ["ALREADY_REVIEWED"]
            verdict = memory_review.review_payload(state.entities[patch_id].entity, state, now)
            if (p.passed, p.checks_passed, p.reason_codes) != (
                verdict.passed,
                verdict.checks_passed,
                verdict.reason_codes,
            ):
                reasons.append("VERDICT_MISMATCH")
            if p.critic_version != verdict.critic_version:
                reasons.append("CRITIC_VERSION_MISMATCH")
            if p.facts_digest != verdict.facts_digest:
                reasons.append("STALE_FACTS_DIGEST")
            return reasons
        case MemoryPatchCommitted(patch_id=patch_id):
            # Single writer: only after a passed review that still holds right now.
            reasons = _undecided_patch(patch_id, state)
            if reasons:
                return reasons
            review = state.memory_reviews.get(patch_id)
            if review is None or not review.passed:
                return ["NO_PASSED_REVIEW"]
            if review.event_id not in draft.derived_from:
                reasons.append("REVIEW_NOT_IN_LINEAGE")
            if state.entities[patch_id].introduced_by not in draft.derived_from:
                reasons.append("PROPOSAL_NOT_IN_LINEAGE")
            recheck = memory_review.review_patch(state.entities[patch_id].entity, state, now)
            if not recheck.passed:
                reasons += [
                    f"REVIEW_NO_LONGER_VALID:{r.split(':', 1)[0]}" for r in recheck.reason_codes
                ]
            if p.commit_sha in state.memory_commits.values():
                reasons.append("COMMIT_ALREADY_RECORDED")
            return reasons
        case MemoryPatchRejected(patch_id=patch_id):
            return _undecided_patch(patch_id, state)
        case MemoryDreamStageRecorded(dream_run_id=run_id, stage=stage, input_ids=input_ids):
            recorded = state.dream_runs.get(run_id, [])
            order = list(DreamStage)
            reasons = []
            if len(recorded) >= len(order):
                reasons.append("RUN_ALREADY_COMPLETE")
            elif stage is not order[len(recorded)]:
                reasons.append(f"STAGE_OUT_OF_ORDER:{order[len(recorded)].value}")
            reasons += [f"UNKNOWN_INPUT:{i}" for i in input_ids if i not in state.entities]
            if stage is DreamStage.PROPOSE_PATCH:
                reasons += [
                    f"NOT_A_PROPOSED_PATCH:{i}" for i in input_ids if i not in state.memory_patches
                ]
            return reasons  # fail closed until the owning policy lands
        case _:
            # PROMOTION_REQUESTED carries no authority.
            return []
