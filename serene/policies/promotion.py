"""Fail-closed Promotion Gate over the epistemic ladder (issues #17, #18).

0 RAW_EVIDENCE -> 1 OBSERVATION -> 2 PATTERN -> 3 HYPOTHESIS
  -> 4 TESTED_HYPOTHESIS -> 5 CONTEXTUAL_LEARNING

Rungs 1-3 are reached by *introducing* a new entity whose parents sit exactly
one rung below (`check_introduction`). Rungs 4-5 are promotions of an existing
hypothesis (`evaluate_promotion`, `check_learning`). The model may request a
level; only these functions decide. Model rationale text is never consulted.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Final

from serene.domain.base import EntityId, KernelModel, ShortText, id_prefix
from serene.domain.canonical import canonical_digest
from serene.domain.entities import (
    TERMINAL_INVESTIGATION_STATUSES,
    Hypothesis,
    Learning,
    Observation,
    OutcomeResult,
    Pattern,
)
from serene.domain.events import SafetyClass
from serene.domain.values import ActorRef, EpistemicLevel, VerificationStatus
from serene.lineage.provenance import provenance_violations, trace_lineage
from serene.policies.decision import PolicyDecision
from serene.policies.safety import classify_intervention
from serene.projections.state import (
    ApprovalState,
    ExperimentStatus,
    KernelState,
    LifecycleStatus,
)

POLICY_VERSION: Final = "promotion/1"
MAX_LEARNING_VALIDITY: Final = timedelta(days=180)

_L = EpistemicLevel


class PromotionRequest(KernelModel):
    """A request to move an existing subject one rung. Carries no authority."""

    subject_id: EntityId
    from_level: EpistemicLevel
    to_level: EpistemicLevel
    requested_by: ActorRef
    rationale: ShortText


def _decision(reasons: list[str]) -> PolicyDecision:
    return PolicyDecision.from_reasons(reasons, POLICY_VERSION)


def facts_digest(subject_id: str, decision: PolicyDecision, state: KernelState) -> str:
    """Bind a decision to the exact ledger head it was computed against."""
    return canonical_digest(
        {
            "subject_id": subject_id,
            "reason_codes": list(decision.reason_codes),
            "policy_version": decision.policy_version,
            "ledger_head": state.last_event_hash,
        }
    )


def _parents_at_level(entity: Any, expected: EpistemicLevel, state: KernelState) -> list[str]:
    reasons: list[str] = []
    for parent in entity.provenance.derived_from:
        level = state.level_of(parent)
        if level is None:
            continue  # reported by provenance_violations as UNKNOWN_PARENT
        if level != expected:
            reasons.append(f"LEVEL_SKIP:{parent}")
        record = state.entities[parent]
        if record.status is not LifecycleStatus.ACTIVE:
            reasons.append(f"PARENT_INACTIVE:{parent}")
        if record.verification_status is VerificationStatus.REJECTED:
            reasons.append(f"PARENT_REJECTED:{parent}")
    return reasons


def check_introduction(entity: Any, state: KernelState) -> PolicyDecision:
    """Gate for entering the ledger at rung 1 (Observation), 2 (Pattern) or 3 (Hypothesis)."""
    reasons: list[str] = []
    entity_id = entity.entity_id
    if entity_id in state.entities:
        reasons.append("DUPLICATE_ENTITY")
    if state.child_id is not None and entity.child_id != state.child_id:
        reasons.append("CHILD_MISMATCH")
    if entity.provenance.verification_status is VerificationStatus.REJECTED:
        reasons.append("SUBJECT_REJECTED")
    reasons += provenance_violations(entity, state)

    match entity:
        case Observation():
            reasons += _parents_at_level(entity, _L.RAW_EVIDENCE, state)
            for evidence_id in entity.evidence_ids:
                status = state.verification_of(evidence_id)
                if status is not VerificationStatus.VERIFIED:
                    reasons.append(f"UNVERIFIED_EVIDENCE:{evidence_id}")
        case Pattern():
            reasons += _parents_at_level(entity, _L.OBSERVATION, state)
            if len(set(entity.observation_ids)) < 2:
                reasons.append("INSUFFICIENT_OBSERVATIONS")
            occasions = {
                state.entities[o].entity.observed_at
                for o in entity.observation_ids
                if o in state.entities
            }
            if len(occasions) < 2:
                reasons.append("SINGLE_OCCASION")
            for counter in entity.counter_observation_ids:
                if counter not in state.entities:
                    reasons.append(f"UNKNOWN_COUNTER_OBSERVATION:{counter}")
        case Hypothesis():
            reasons += _parents_at_level(entity, _L.PATTERN, state)
            if not (entity.alternative_explanations or entity.competing_hypothesis_ids):
                reasons.append("NO_ALTERNATIVES_CONSIDERED")
            for competitor in entity.competing_hypothesis_ids:
                if competitor not in state.hypothesis_levels:
                    reasons.append(f"UNKNOWN_COMPETITOR:{competitor}")
            inv_status = state.investigations.get(entity.investigation_id)
            if inv_status is None:
                reasons.append("UNKNOWN_INVESTIGATION")
            elif inv_status in TERMINAL_INVESTIGATION_STATUSES:
                reasons.append("INVESTIGATION_CLOSED")
            for evidence_id in (*entity.supporting_evidence_ids, *entity.counter_evidence_ids):
                if state.verification_of(evidence_id) is not VerificationStatus.VERIFIED:
                    reasons.append(f"UNVERIFIED_EVIDENCE:{evidence_id}")
        case _:
            reasons.append("NOT_A_LADDER_ENTITY")
    return _decision(reasons)


def _lineage_reasons(subject_id: str, state: KernelState) -> list[str]:
    trace = trace_lineage(subject_id, state)
    reasons = [f"MISSING_ANCESTOR:{m}" for m in trace.missing]
    if not trace.raw_evidence:
        reasons.append("NO_RAW_EVIDENCE")
    for node in trace.nodes:
        if node.verification_status is VerificationStatus.REJECTED:
            reasons.append(f"REJECTED_IN_LINEAGE:{node.entity_id}")
        if id_prefix(node.entity_id) == "evd" and (
            node.verification_status is not VerificationStatus.VERIFIED
        ):
            reasons.append(f"UNVERIFIED_EVIDENCE:{node.entity_id}")
    return reasons


def _tested_experiments(hypothesis_id: str, state: KernelState) -> list[str]:
    """Completed experiments for the hypothesis that ran under a granted, non-RED approval."""
    tested: list[str] = []
    for exp_id, record in sorted(state.experiments.items()):
        if record.experiment.hypothesis_id != hypothesis_id:
            continue
        if record.status is not ExperimentStatus.COMPLETED:
            continue
        approval = state.approvals.get(record.approval_request_id or "")
        if approval is None or approval.state is not ApprovalState.GRANTED:
            continue
        if approval.consumed_by is None:
            continue
        if classify_intervention(record.experiment.intervention).safety_class is SafetyClass.RED:
            continue
        tested.append(exp_id)
    return tested


def evaluate_promotion(request: PromotionRequest, state: KernelState) -> PolicyDecision:
    """Decide a promotion of an existing hypothesis (3->4 or 4->5).

    `request.rationale` and `request.requested_by` are recorded but never consulted.
    """
    return _decision(
        _promotion_reasons(request.subject_id, request.from_level, request.to_level, state)
    )


def _promotion_reasons(
    subject_id: str, from_level: EpistemicLevel, to_level: EpistemicLevel, state: KernelState
) -> list[str]:
    reasons: list[str] = []
    if to_level != from_level + 1:
        return ["LEVEL_SKIP" if to_level > from_level else "NOT_A_PROMOTION"]
    if to_level not in (_L.TESTED_HYPOTHESIS, _L.CONTEXTUAL_LEARNING):
        return ["PROMOTION_VIA_INTRODUCTION_ONLY"]

    current = state.hypothesis_levels.get(subject_id)
    if current is None:
        return ["UNKNOWN_SUBJECT"]
    if current != from_level:
        reasons.append(f"LEVEL_MISMATCH:{current.name}")
    record = state.entities[subject_id]
    if record.status is not LifecycleStatus.ACTIVE:
        reasons.append("SUBJECT_INACTIVE")
    reasons += _lineage_reasons(subject_id, state)

    tested = _tested_experiments(subject_id, state)
    if not tested:
        reasons.append("NO_APPROVED_COMPLETED_EXPERIMENT")
    results = [
        state.entities[outcome_id].entity.result
        for exp_id in tested
        for outcome_id in state.experiments[exp_id].outcome_ids
    ]
    if OutcomeResult.SUPPORTS not in results:
        reasons.append("NO_SUPPORTING_OUTCOME")
    if OutcomeResult.CONTRADICTS in results:
        reasons.append("CONTRADICTING_OUTCOME")
    return reasons


def check_learning(
    learning: Learning, promotion_event_id: str, state: KernelState, now: datetime
) -> PolicyDecision:
    """Gate for recording a Level-5 learning against a prior PROMOTION_GRANTED to level 5."""
    reasons: list[str] = []
    promotion = state.promotions.get(promotion_event_id)
    if promotion is None or not promotion.granted:
        reasons.append("NO_PROMOTION_GRANT")
    else:
        if promotion.subject_id != learning.hypothesis_id:
            reasons.append("GRANT_SUBJECT_MISMATCH")
        if promotion.to_level != _L.CONTEXTUAL_LEARNING:
            reasons.append("GRANT_LEVEL_MISMATCH")
        if promotion.consumed_by is not None:
            reasons.append("GRANT_ALREADY_USED")

    if learning.learning_id in state.entities:
        reasons.append("DUPLICATE_ENTITY")
    if state.hypothesis_levels.get(learning.hypothesis_id) != _L.CONTEXTUAL_LEARNING:
        reasons.append("HYPOTHESIS_NOT_PROMOTED")
    if learning.hypothesis_id not in learning.provenance.derived_from:
        reasons.append("HYPOTHESIS_NOT_IN_LINEAGE")
    reasons += provenance_violations(learning, state)

    hypothesis_record = state.entities.get(learning.hypothesis_id)
    if hypothesis_record is not None:
        hypothesis = hypothesis_record.entity
        broadened = set(learning.scope.contexts) - set(hypothesis.scope.contexts)
        if broadened:
            reasons.append("SCOPE_BROADENED")
        if hypothesis_record.status is not LifecycleStatus.ACTIVE:
            reasons.append("SUBJECT_INACTIVE")

    tested = set(_tested_experiments(learning.hypothesis_id, state))
    for exp_id in learning.experiment_ids:
        if exp_id not in tested:
            reasons.append(f"UNTESTED_EXPERIMENT:{exp_id}")
    known_outcomes = {o for e in tested for o in state.experiments[e].outcome_ids}
    for outcome_id in learning.outcome_ids:
        if outcome_id not in known_outcomes:
            reasons.append(f"UNKNOWN_OUTCOME:{outcome_id}")

    window = learning.validity
    if window.review_after - window.valid_from > MAX_LEARNING_VALIDITY:
        reasons.append("VALIDITY_TOO_LONG")
    if window.review_after <= now:
        reasons.append("ALREADY_DUE_FOR_REVIEW")
    if window.valid_from > now:
        reasons.append("VALIDITY_STARTS_IN_FUTURE")
    return _decision(reasons)


def max_permitted_level(hypothesis_id: str, state: KernelState) -> EpistemicLevel | None:
    """Highest rung the evidence currently supports for a hypothesis (no skipping).

    Capped at TESTED_HYPOTHESIS: rung 5 additionally needs an explicit, scoped
    Learning candidate with validity/review metadata (see `check_learning`).
    """
    current = state.hypothesis_levels.get(hypothesis_id)
    if current is None:
        return None
    permitted = current
    while permitted < _L.TESTED_HYPOTHESIS:
        nxt = EpistemicLevel(permitted + 1)
        if _promotion_reasons(hypothesis_id, permitted, nxt, state):
            break
        permitted = nxt
    return permitted
