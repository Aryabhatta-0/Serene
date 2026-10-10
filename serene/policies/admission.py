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
    Evidence,
    EvidenceKind,
    InvestigationStatus,
    LearningStatus,
    OutcomeResult,
)
from serene.domain.events import (
    ApprovalGranted,
    ApprovalNudged,
    ApprovalRejected,
    ApprovalRequested,
    ApprovalTimedOut,
    DreamStage,
    EventDraft,
    EventType,
    EvidenceAcquired,
    EvidenceRejected,
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
    InvestigationOpened,
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
    OutcomeReported,
    PatternProposed,
    PromotionDecisionRecord,
    TrialRecorded,
)
from serene.domain.values import AUTHENTICATED_CHANNELS, EpistemicLevel, VerificationStatus
from serene.lineage.provenance import provenance_violations
from serene.policies import approval, memory_review, promotion, safety
from serene.policies.decision import PolicyDecision
from serene.policies.experiments import outcome_due_at
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


def admission_violations(draft: EventDraft, state: KernelState, now: datetime) -> list[str]:
    p = draft.payload
    et = draft.event_type
    match p:
        case ObservationReported(evidence=ev):
            reasons = _check_evidence(draft, ev, state)
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
        case EvidenceAcquired(evidence=ev):
            reasons = _check_evidence(draft, ev, state)
            if ev.kind not in _EXTERNAL_EVIDENCE:
                reasons.append("ONLY_EXTERNAL_EVIDENCE_IS_ACQUIRED")
            return reasons
        case EvidenceVerified(evidence_id=evidence_id) | EvidenceRejected(evidence_id=evidence_id):
            status = state.verification_of(evidence_id)
            if status is None:
                return ["UNKNOWN_EVIDENCE"]
            if status is not VerificationStatus.UNVERIFIED:
                return [f"ALREADY_DECIDED:{status.value}"]
            return []
        case ObservationStructured(observation=entity) | PatternProposed(pattern=entity):
            return _reasons(promotion.check_introduction(entity, state))
        case HypothesisProposed(hypothesis=hypothesis):
            return _reasons(promotion.check_introduction(hypothesis, state))
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
            # EVIDENCE_REQUESTED and PROMOTION_REQUESTED carry no authority.
            return []
