"""Fail-closed Promotion Gate over the epistemic ladder (issues #17, #18, #20).

0 RAW_EVIDENCE -> 1 OBSERVATION -> 2 PATTERN -> 3 HYPOTHESIS
  -> 4 TESTED_HYPOTHESIS -> 5 CONTEXTUAL_LEARNING

Rungs 1-3 are reached by *introducing* a new entity whose parents sit exactly
one rung below (`check_introduction`). Rungs 4-5 are promotions of an existing
hypothesis (`evaluate_promotion`, `check_learning`). Every legal move is listed
in `serene.policies.ladder.TRANSITIONS`; anything else fails closed before any
evidence is examined. The model may request a level; only these functions
decide. Model rationale text is never consulted.

Level 5 additionally requires complete verified provenance, counterevidence
consideration (no contradicting outcome anywhere, every cited experiment's
outcomes cited, confounders listed, no equally-tested rival, and no verified
parent/caregiver observation in a supporting pattern's scope left out of the
patterns' accounting), scope bounded by the contexts actually tested, and
validity/review metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

from serene.domain.base import EntityId, KernelModel, ShortText, id_prefix
from serene.domain.canonical import canonical_digest
from serene.domain.entities import (
    TERMINAL_INVESTIGATION_STATUSES,
    EvidenceKind,
    Hypothesis,
    Learning,
    Observation,
    OutcomeResult,
    Pattern,
    ReviewMetadata,
    ValidityWindow,
)
from serene.domain.events import EventType, PromotionDecisionRecord, SafetyClass
from serene.domain.values import (
    HUMAN_ACTORS,
    ActorRef,
    DerivationMethod,
    EpistemicLevel,
    Provenance,
    Scope,
    VerificationStatus,
)
from serene.lineage.provenance import provenance_violations, trace_lineage
from serene.policies.decision import PolicyDecision
from serene.policies.ladder import promotion_violation
from serene.policies.safety import classify_intervention
from serene.projections.state import (
    ApprovalState,
    ExperimentStatus,
    KernelState,
    LifecycleStatus,
)

POLICY_VERSION: Final = "promotion/2"
MAX_LEARNING_VALIDITY: Final = timedelta(days=180)
DEFAULT_LEARNING_REVIEW: Final = timedelta(days=60)

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


def lineage_reasons(subject_id: str, state: KernelState) -> list[str]:
    """Complete, verified, unrejected lineage from `subject_id` down to raw evidence."""
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


def tested_experiments(hypothesis_id: str, state: KernelState) -> list[str]:
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


@dataclass(frozen=True, slots=True)
class Counterevidence:
    """Everything in the ledger that speaks against a hypothesis. Never summarized away."""

    contradicting_outcomes: tuple[str, ...]
    inconclusive_outcomes: tuple[str, ...]
    counter_evidence_ids: tuple[str, ...]
    counter_observation_ids: tuple[str, ...]
    unresolved_competitors: tuple[str, ...]

    @property
    def all_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    *self.contradicting_outcomes,
                    *self.inconclusive_outcomes,
                    *self.counter_evidence_ids,
                    *self.counter_observation_ids,
                }
            )
        )


def _outcomes_for(hypothesis_id: str, state: KernelState) -> list[tuple[str, OutcomeResult]]:
    """Every reported outcome on any experiment of the hypothesis, whatever its status."""
    out: list[tuple[str, OutcomeResult]] = []
    for record in state.experiments.values():
        if record.experiment.hypothesis_id != hypothesis_id:
            continue
        for outcome_id in record.outcome_ids:
            out.append((outcome_id, state.entities[outcome_id].entity.result))
    return sorted(out)


def counterevidence_for(hypothesis_id: str, state: KernelState) -> Counterevidence:
    record = state.entities.get(hypothesis_id)
    if record is None:
        return Counterevidence((), (), (), (), ())
    hypothesis = record.entity
    outcomes = _outcomes_for(hypothesis_id, state)
    counter_obs: set[str] = set()
    for pattern_id in hypothesis.pattern_ids:
        pattern = state.entities.get(pattern_id)
        if pattern is not None:
            counter_obs |= set(pattern.entity.counter_observation_ids)
    rivals = set(hypothesis.competing_hypothesis_ids) | set(
        state.investigation_hypotheses.get(hypothesis.investigation_id, [])
    )
    rivals.discard(hypothesis_id)
    unresolved = sorted(
        rival
        for rival in rivals
        if rival in state.entities
        and state.entities[rival].status is LifecycleStatus.ACTIVE
        and state.hypothesis_levels.get(rival, _L.HYPOTHESIS) >= _L.TESTED_HYPOTHESIS
    )
    return Counterevidence(
        contradicting_outcomes=tuple(o for o, r in outcomes if r is OutcomeResult.CONTRADICTS),
        inconclusive_outcomes=tuple(o for o, r in outcomes if r is OutcomeResult.INCONCLUSIVE),
        counter_evidence_ids=tuple(sorted(hypothesis.counter_evidence_ids)),
        counter_observation_ids=tuple(sorted(counter_obs)),
        unresolved_competitors=tuple(unresolved),
    )


_HUMAN_REPORTS: Final = frozenset({EvidenceKind.PARENT_REPORT, EvidenceKind.CAREGIVER_REPORT})


def _is_verified_human_observation(record: Any, state: KernelState) -> bool:
    """An active, unrejected observation read from verified parent/caregiver reports."""
    observation = record.entity
    if record.status is not LifecycleStatus.ACTIVE:
        return False
    if record.verification_status is VerificationStatus.REJECTED:
        return False
    evidence = [state.entities.get(e) for e in observation.evidence_ids]
    if any(e is None or e.verification_status is not VerificationStatus.VERIFIED for e in evidence):
        return False
    # Human if either the structured observer or any raw report says so: the
    # model-extracted observer field alone cannot hide a parent's report.
    return observation.observer.kind in HUMAN_ACTORS or any(
        e is not None and e.entity.kind in _HUMAN_REPORTS for e in evidence
    )


def unaccounted_observations(hypothesis_id: str, state: KernelState) -> tuple[str, ...]:
    """Verified human observations in a supporting pattern's scope that no pattern accounts for.

    Relevance is structural, never semantic: the same child, an overlapping context
    (an observation or pattern with no declared context is in scope) and an
    observation time inside the pattern's own observation span. Whether the omitted
    report agrees or disagrees is not judged; it must appear in some supporting
    pattern's `observation_ids` or `counter_observation_ids`.
    """
    record = state.entities.get(hypothesis_id)
    if record is None:
        return ()
    patterns = [state.entities[p].entity for p in record.entity.pattern_ids if p in state.entities]
    accounted = {o for p in patterns for o in (*p.observation_ids, *p.counter_observation_ids)}
    observations = [
        r
        for r in state.entities.values()
        if isinstance(r.entity, Observation) and r.entity_id not in accounted
    ]
    missing: set[str] = set()
    for pattern in patterns:
        members = [state.entities[o].entity for o in pattern.observation_ids if o in state.entities]
        if not members:
            continue
        start = min(m.observed_at for m in members)
        end = max(m.observed_at for m in members)
        contexts = set(pattern.contexts) or {c for m in members for c in m.contexts}
        for r in observations:
            obs = r.entity
            if obs.child_id != pattern.child_id or not start <= obs.observed_at <= end:
                continue
            if contexts and obs.contexts and not contexts & set(obs.contexts):
                continue
            if _is_verified_human_observation(r, state):
                missing.add(r.entity_id)
    return tuple(sorted(missing))


def _counterevidence_reasons(
    hypothesis_id: str, to_level: EpistemicLevel, state: KernelState
) -> list[str]:
    counter = counterevidence_for(hypothesis_id, state)
    reasons: list[str] = []
    if counter.contradicting_outcomes:
        reasons.append("CONTRADICTING_OUTCOME")
    if to_level >= _L.CONTEXTUAL_LEARNING:
        hypothesis = state.entities[hypothesis_id].entity
        if not hypothesis.known_confounders:
            reasons.append("NO_CONFOUNDERS_CONSIDERED")
        reasons += [f"UNRESOLVED_COMPETITOR:{c}" for c in counter.unresolved_competitors]
        reasons += [
            f"UNACCOUNTED_RELEVANT_OBSERVATION:{o}"
            for o in unaccounted_observations(hypothesis_id, state)
        ]
    return reasons


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
    violation = promotion_violation(from_level, to_level)
    if violation is not None:
        return [violation]

    current = state.hypothesis_levels.get(subject_id)
    if current is None:
        return ["UNKNOWN_SUBJECT"]
    reasons: list[str] = []
    if current != from_level:
        reasons.append(f"LEVEL_MISMATCH:{current.name}")
    record = state.entities[subject_id]
    if record.status is not LifecycleStatus.ACTIVE:
        reasons.append("SUBJECT_INACTIVE")
    reasons += lineage_reasons(subject_id, state)

    tested = tested_experiments(subject_id, state)
    if not tested:
        reasons.append("NO_APPROVED_COMPLETED_EXPERIMENT")
    results = [
        state.entities[outcome_id].entity.result
        for exp_id in tested
        for outcome_id in state.experiments[exp_id].outcome_ids
    ]
    if OutcomeResult.SUPPORTS not in results:
        reasons.append("NO_SUPPORTING_OUTCOME")
    reasons += _counterevidence_reasons(subject_id, to_level, state)
    return reasons


def decide_promotion(
    subject_id: str, from_level: EpistemicLevel, to_level: EpistemicLevel, state: KernelState
) -> tuple[EventType, PromotionDecisionRecord]:
    """The gate's recorded verdict: PROMOTION_GRANTED or PROMOTION_DENIED, bound to the head."""
    decision = _decision(_promotion_reasons(subject_id, from_level, to_level, state))
    record = PromotionDecisionRecord(
        subject_id=subject_id,
        from_level=from_level,
        to_level=to_level,
        reason_codes=decision.reason_codes,
        policy_version=decision.policy_version,
        facts_digest=facts_digest(subject_id, decision, state),
    )
    event_type = EventType.PROMOTION_GRANTED if decision.allowed else EventType.PROMOTION_DENIED
    return event_type, record


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
    for parent in learning.provenance.derived_from:
        if parent in state.entities:
            reasons += lineage_reasons(parent, state)

    hypothesis_record = state.entities.get(learning.hypothesis_id)
    if hypothesis_record is not None:
        hypothesis = hypothesis_record.entity
        broadened = set(learning.scope.contexts) - set(hypothesis.scope.contexts)
        if broadened:
            reasons.append("SCOPE_BROADENED")
        if hypothesis_record.status is not LifecycleStatus.ACTIVE:
            reasons.append("SUBJECT_INACTIVE")
        reasons += _counterevidence_reasons(learning.hypothesis_id, _L.CONTEXTUAL_LEARNING, state)

    tested = set(tested_experiments(learning.hypothesis_id, state))
    tested_contexts: set[str] = set()
    for exp_id in learning.experiment_ids:
        if exp_id not in tested:
            reasons.append(f"UNTESTED_EXPERIMENT:{exp_id}")
        else:
            tested_contexts |= set(state.experiments[exp_id].experiment.scope.contexts)
            # No cherry-picking: every outcome of a cited experiment must be cited.
            for outcome_id in state.experiments[exp_id].outcome_ids:
                if outcome_id not in learning.outcome_ids:
                    reasons.append(f"OUTCOME_OMITTED:{outcome_id}")
    if set(learning.scope.contexts) - tested_contexts:
        reasons.append("SCOPE_EXCEEDS_TESTED_CONTEXTS")
    known_outcomes = {o for e in tested for o in state.experiments[e].outcome_ids}
    for outcome_id in learning.outcome_ids:
        if outcome_id not in known_outcomes:
            reasons.append(f"UNKNOWN_OUTCOME:{outcome_id}")
    cited = [state.entities[o].entity.result for o in learning.outcome_ids if o in known_outcomes]
    if OutcomeResult.SUPPORTS not in cited:
        reasons.append("NO_SUPPORTING_OUTCOME_CITED")

    window = learning.validity
    if window.review_after - window.valid_from > MAX_LEARNING_VALIDITY:
        reasons.append("VALIDITY_TOO_LONG")
    if window.review_after <= now:
        reasons.append("ALREADY_DUE_FOR_REVIEW")
    if window.valid_from > now:
        reasons.append("VALIDITY_STARTS_IN_FUTURE")
    return _decision(reasons)


def build_learning_candidate(
    hypothesis_id: str,
    state: KernelState,
    *,
    learning_id: str,
    created_by: ActorRef,
    reviewer: ActorRef,
    now: datetime,
    review_period: timedelta = DEFAULT_LEARNING_REVIEW,
) -> Learning:
    """The policy-built Level-5 candidate: scope = contexts actually tested, bounded validity.

    Nothing here comes from model text except the hypothesis statement it restates.
    `check_learning` still decides admission.
    """
    hypothesis = state.entities[hypothesis_id].entity
    tested = tested_experiments(hypothesis_id, state)
    outcomes = [o for exp_id in tested for o in state.experiments[exp_id].outcome_ids]
    tested_contexts = {c for e in tested for c in state.experiments[e].experiment.scope.contexts}
    contexts = tuple(c for c in hypothesis.scope.contexts if c in tested_contexts)
    parents = (hypothesis_id, *tested, *outcomes)
    sources: list[str] = []
    for parent in parents:
        sources.extend(state.entities[parent].entity.provenance.source_ids)
    triggers = (*hypothesis.known_confounders, *hypothesis.falsification_criteria)[:8]
    return Learning(
        child_id=hypothesis.child_id,
        provenance=Provenance(
            created_by=created_by,
            created_at=now,
            method=DerivationMethod.DETERMINISTIC_RULE,
            derived_from=parents,
            source_ids=tuple(dict.fromkeys(sources)),
            verification_status=VerificationStatus.VERIFIED,
        ),
        learning_id=learning_id,
        hypothesis_id=hypothesis_id,
        experiment_ids=tuple(tested),
        outcome_ids=tuple(outcomes),
        statement=hypothesis.statement,
        scope=Scope(child_id=hypothesis.child_id, contexts=contexts or hypothesis.scope.contexts),
        validity=ValidityWindow(valid_from=now, review_after=now + review_period),
        review=ReviewMetadata(reviewer=reviewer, retest_triggers=triggers),
    )


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
