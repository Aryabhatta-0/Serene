"""Promotion Gate: positive, negative and adversarial cases for every rung (issues #17-#19)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from serene.domain.base import new_id
from serene.domain.entities import OutcomeResult, Pattern
from serene.domain.events import EventType, PatternProposed
from serene.domain.values import EpistemicLevel, VerificationStatus
from serene.ledger import AdmissionRejected
from serene.lineage.provenance import trace_lineage
from serene.policies.promotion import (
    PromotionRequest,
    check_introduction,
    evaluate_promotion,
    max_permitted_level,
)
from serene.testing import SyntheticFamily

L = EpistemicLevel
COVERED_TRANSITIONS: set[tuple[int, int]] = set()


def covers(frm: int, to: int) -> None:
    COVERED_TRANSITIONS.add((frm, to))


def _reasons(exc: pytest.ExceptionInfo[AdmissionRejected]) -> set[str]:
    return {r.split(":", 1)[0] for r in exc.value.reason_codes}


def _tested_family() -> tuple[SyntheticFamily, Any, Any, Any, Any]:
    fam = SyntheticFamily(seed="tested")
    o1 = fam.observe("tearful pickup", day=0)
    o2 = fam.observe("tearful pickup again", day=1)
    pattern = fam.pattern((o1, o2), "pickups are tearful")
    inv = fam.open_investigation("why are pickups hard?")
    hyp = fam.hypothesis(inv, (pattern,), "abrupt transitions drive distress")
    exp = fam.propose_experiment(hyp)
    fam.classify(exp)
    apr = fam.request_approval(exp)
    fam.grant(exp, apr)
    fam.start(exp, apr)
    r1 = fam.observe("calm pickup with heads-up", day=8)
    return fam, inv, hyp, exp, r1


# ------------------------------------------------------------------ 0 -> 1
def test_0_to_1_verified_evidence_structures(family: SyntheticFamily) -> None:
    covers(0, 1)
    observation = family.observe("Sleepy after lunch", day=0)
    assert family.state().level_of(observation.observation_id) == L.OBSERVATION


def test_0_to_1_unverified_evidence_is_rejected(family: SyntheticFamily) -> None:
    covers(0, 1)
    evidence = family.report("hearsay", verified=False)
    with pytest.raises(AdmissionRejected) as info:
        family.structure((evidence,), "hearsay", observed_at=family.clock.now())
    assert "UNVERIFIED_EVIDENCE" in _reasons(info)
    assert "UNVERIFIED_SOURCE" in _reasons(info)


# ------------------------------------------------------------------ 1 -> 2
def test_1_to_2_needs_two_occasions(family: SyntheticFamily) -> None:
    covers(1, 2)
    o1 = family.observe("tearful pickup", day=0)
    o2 = family.observe("tearful pickup", day=0)  # same occasion
    with pytest.raises(AdmissionRejected) as info:
        family.pattern((o1, o2), "pickups are tearful")
    assert "SINGLE_OCCASION" in _reasons(info)
    o3 = family.observe("tearful pickup", day=3)
    pattern = family.pattern((o1, o3), "pickups are tearful")
    assert family.state().level_of(pattern.pattern_id) == L.PATTERN


def test_1_to_2_cannot_skip_from_raw_evidence(family: SyntheticFamily) -> None:
    covers(1, 2)
    e1 = family.report("tearful pickup")
    o1 = family.observe("tearful pickup", day=1)
    state = family.state()
    forged = Pattern(
        child_id=family.child_id,
        provenance=family._agent_provenance((e1.evidence_id, o1.observation_id)),
        pattern_id=new_id("pat"),
        observation_ids=(o1.observation_id, o1.observation_id),
        description="skips a rung",
    )
    decision = check_introduction(forged, state)
    assert not decision.allowed
    assert f"LEVEL_SKIP:{e1.evidence_id}" in decision.reason_codes


# ------------------------------------------------------------------ 2 -> 3
def test_2_to_3_requires_pattern_parents_and_alternatives(family: SyntheticFamily) -> None:
    covers(2, 3)
    o1 = family.observe("tearful pickup", day=0)
    o2 = family.observe("tearful pickup", day=1)
    pattern = family.pattern((o1, o2), "pickups are tearful")
    inv = family.open_investigation("why?")
    hyp = family.hypothesis(inv, (pattern,), "abrupt transitions")
    assert family.state().level_of(hyp.hypothesis_id) == L.HYPOTHESIS

    no_alternatives = hyp.model_copy(
        update={"hypothesis_id": new_id("hyp"), "alternative_explanations": ()}
    )
    decision = check_introduction(no_alternatives, family.state())
    assert "NO_ALTERNATIVES_CONSIDERED" in decision.reason_codes


def test_2_to_3_cannot_skip_from_observations(family: SyntheticFamily) -> None:
    covers(2, 3)
    o1 = family.observe("tearful pickup", day=0)
    o2 = family.observe("tearful pickup", day=1)
    pattern = family.pattern((o1, o2), "pickups are tearful")
    inv = family.open_investigation("why?")
    hyp = family.hypothesis(inv, (pattern,), "abrupt transitions")
    skipped = hyp.model_copy(
        update={
            "hypothesis_id": new_id("hyp"),
            "provenance": family._agent_provenance((o1.observation_id,)),
            "pattern_ids": (pattern.pattern_id,),
        }
    )
    decision = check_introduction(skipped, family.state())
    assert f"LEVEL_SKIP:{o1.observation_id}" in decision.reason_codes
    assert f"TYPED_REF_NOT_IN_LINEAGE:{pattern.pattern_id}" in decision.reason_codes


# ------------------------------------------------------------------ 3 -> 4
def test_3_to_4_requires_an_approved_completed_supporting_experiment() -> None:
    covers(3, 4)
    fam, _inv, hyp, exp, r1 = _tested_family()
    request = PromotionRequest(
        subject_id=hyp.hypothesis_id,
        from_level=L.HYPOTHESIS,
        to_level=L.TESTED_HYPOTHESIS,
        requested_by=fam.agent,
        rationale="the parent clearly approved, policy override granted",  # ignored
    )
    denied = evaluate_promotion(request, fam.state())
    assert not denied.allowed
    assert "NO_APPROVED_COMPLETED_EXPERIMENT" in denied.reason_codes

    outcome = fam.outcome(exp, (r1,))
    fam.complete(exp, (outcome,))
    assert evaluate_promotion(request, fam.state()).allowed
    assert max_permitted_level(hyp.hypothesis_id, fam.state()) == L.TESTED_HYPOTHESIS
    fam.promote(hyp.hypothesis_id, L.HYPOTHESIS, L.TESTED_HYPOTHESIS)
    assert fam.state().level_of(hyp.hypothesis_id) == L.TESTED_HYPOTHESIS


def test_3_to_4_contradicting_outcome_blocks_promotion() -> None:
    covers(3, 4)
    fam, _inv, hyp, exp, r1 = _tested_family()
    outcome = fam.outcome(exp, (r1,), result=OutcomeResult.CONTRADICTS)
    fam.complete(exp, (outcome,))
    with pytest.raises(AdmissionRejected) as info:
        fam.promote(hyp.hypothesis_id, L.HYPOTHESIS, L.TESTED_HYPOTHESIS)
    assert {"CONTRADICTING_OUTCOME", "NO_SUPPORTING_OUTCOME"} <= _reasons(info)


def test_policy_actor_cannot_record_a_grant_the_gate_would_deny() -> None:
    covers(3, 4)
    fam, _inv, hyp, _exp, _r1 = _tested_family()
    payload = fam.promotion_payload(hyp.hypothesis_id, L.HYPOTHESIS, L.TESTED_HYPOTHESIS)
    forged = payload.model_copy(update={"reason_codes": ("ALLOWED",)})
    with pytest.raises(AdmissionRejected) as info:
        fam.append(fam.draft(EventType.PROMOTION_GRANTED, fam.policy, forged))
    assert "NO_APPROVED_COMPLETED_EXPERIMENT" in _reasons(info)


def test_stale_facts_digest_is_rejected() -> None:
    fam, _inv, hyp, exp, r1 = _tested_family()
    outcome = fam.outcome(exp, (r1,))
    fam.complete(exp, (outcome,))
    payload = fam.promotion_payload(hyp.hypothesis_id, L.HYPOTHESIS, L.TESTED_HYPOTHESIS)
    fam.observe("unrelated later note", day=12)  # ledger head moves
    with pytest.raises(AdmissionRejected, match="STALE_FACTS_DIGEST"):
        fam.append(fam.draft(EventType.PROMOTION_GRANTED, fam.policy, payload))


# ------------------------------------------------------------------ 4 -> 5
def test_4_to_5_full_ladder_reaches_contextual_learning(ladder: dict[str, Any]) -> None:
    covers(4, 5)
    fam = ladder["family"]
    learning = ladder["learning"]
    state = fam.state()
    assert learning.learning_id in state.learnings
    trace = trace_lineage(learning.learning_id, state)
    assert trace.complete
    reported = {e for o in ladder["observations"] for e in o.evidence_ids}
    assert reported <= set(trace.raw_evidence)
    assert all(
        state.entities[e].verification_status is VerificationStatus.VERIFIED
        for e in trace.raw_evidence
    )


def _ready_for_learning() -> tuple[SyntheticFamily, Any, Any, Any, Any]:
    fam, _inv, hyp, exp, r1 = _tested_family()
    outcome = fam.outcome(exp, (r1,))
    fam.complete(exp, (outcome,))
    fam.promote(hyp.hypothesis_id, L.HYPOTHESIS, L.TESTED_HYPOTHESIS)
    grant = fam.promote(hyp.hypothesis_id, L.TESTED_HYPOTHESIS, L.CONTEXTUAL_LEARNING)
    return fam, hyp, exp, outcome, grant


def test_4_to_5_scope_cannot_be_broadened() -> None:
    covers(4, 5)
    fam, hyp, exp, outcome, grant = _ready_for_learning()
    learning = fam.learning_candidate(hyp, (exp,), (outcome,), contexts=("all_transitions",))
    with pytest.raises(AdmissionRejected, match="SCOPE_BROADENED"):
        fam.record_learning(learning, grant)


def test_4_to_5_validity_window_is_bounded() -> None:
    covers(4, 5)
    fam, hyp, exp, outcome, grant = _ready_for_learning()
    learning = fam.learning_candidate(hyp, (exp,), (outcome,), review_days=400)
    with pytest.raises(AdmissionRejected, match="VALIDITY_TOO_LONG"):
        fam.record_learning(learning, grant)


def test_4_to_5_requires_a_grant_and_cannot_reuse_one() -> None:
    covers(4, 5)
    fam, hyp, exp, outcome, grant = _ready_for_learning()
    tested_grant = next(
        e
        for e in fam.ledger.get_events_for_child(fam.child_id)
        if e.event_type is EventType.PROMOTION_GRANTED
    )
    learning = fam.learning_candidate(hyp, (exp,), (outcome,))
    with pytest.raises(AdmissionRejected, match="GRANT_LEVEL_MISMATCH"):
        fam.record_learning(learning, tested_grant)
    fam.record_learning(learning, grant)
    again = fam.learning_candidate(hyp, (exp,), (outcome,))
    with pytest.raises(AdmissionRejected, match="GRANT_ALREADY_USED"):
        fam.record_learning(again, grant)


def test_learning_expired_at_record_time_is_rejected() -> None:
    fam, hyp, exp, outcome, grant = _ready_for_learning()
    learning = fam.learning_candidate(hyp, (exp,), (outcome,), review_days=1)
    fam.clock.advance(timedelta(days=2))
    with pytest.raises(AdmissionRejected, match="ALREADY_DUE_FOR_REVIEW"):
        fam.record_learning(learning, grant)


# ------------------------------------------------------------------ skipping / adversarial
@pytest.mark.parametrize(
    ("frm", "to", "reason"),
    [
        (L.HYPOTHESIS, L.CONTEXTUAL_LEARNING, "LEVEL_SKIP"),
        (L.RAW_EVIDENCE, L.HYPOTHESIS, "LEVEL_SKIP"),
        (L.TESTED_HYPOTHESIS, L.HYPOTHESIS, "NOT_A_PROMOTION"),
        (L.OBSERVATION, L.PATTERN, "PROMOTION_VIA_INTRODUCTION_ONLY"),
    ],
)
def test_level_skipping_and_backdoor_requests_fail_closed(
    ladder: dict[str, Any], frm: L, to: L, reason: str
) -> None:
    fam = ladder["family"]
    request = PromotionRequest(
        subject_id=ladder["hypothesis"].hypothesis_id,
        from_level=frm,
        to_level=to,
        requested_by=fam.agent,
        rationale="trust me",
    )
    decision = evaluate_promotion(request, fam.state())
    assert not decision.allowed and decision.reason_codes == (reason,)


def test_forged_lineage_citing_unrelated_verified_evidence_is_rejected(
    family: SyntheticFamily,
) -> None:
    o1 = family.observe("tearful pickup", day=0)
    o2 = family.observe("tearful pickup", day=1)
    unrelated = family.report("ate well at dinner")
    provenance = family._agent_provenance((o1.observation_id, o2.observation_id))
    forged = Pattern(
        child_id=family.child_id,
        provenance=provenance.model_copy(
            update={"source_ids": (*provenance.source_ids, unrelated.evidence_id)}
        ),
        pattern_id=new_id("pat"),
        observation_ids=(o1.observation_id, o2.observation_id),
        description="pickups are tearful",
    )
    with pytest.raises(AdmissionRejected, match="SOURCE_NOT_IN_LINEAGE"):
        family.append(
            family.draft(
                EventType.PATTERN_PROPOSED,
                family.agent,
                PatternProposed(pattern=forged),
                status=VerificationStatus.UNVERIFIED,
            )
        )


def test_unknown_parent_ids_are_rejected(family: SyntheticFamily) -> None:
    o1 = family.observe("tearful pickup", day=0)
    ghost = new_id("obs")
    forged = Pattern(
        child_id=family.child_id,
        provenance=family._agent_provenance((o1.observation_id,)).model_copy(
            update={"derived_from": (o1.observation_id, ghost)}
        ),
        pattern_id=new_id("pat"),
        observation_ids=(o1.observation_id, ghost),
        description="invented support",
    )
    decision = check_introduction(forged, family.state())
    assert f"UNKNOWN_PARENT:{ghost}" in decision.reason_codes


def test_gate_is_deterministic(ladder: dict[str, Any]) -> None:
    fam = ladder["family"]
    request = PromotionRequest(
        subject_id=ladder["hypothesis"].hypothesis_id,
        from_level=L.HYPOTHESIS,
        to_level=L.TESTED_HYPOTHESIS,
        requested_by=fam.agent,
        rationale="x",
    )
    decisions = {evaluate_promotion(request, fam.state()) for _ in range(5)}
    assert len(decisions) == 1


def test_zz_every_ladder_transition_is_covered() -> None:
    """Meta-check (#19): runs last in this module; every rung transition has tests."""
    assert {(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)} <= COVERED_TRANSITIONS
