"""Promotion authority: explicit transition table, no model-controlled promotion and the
strengthened Level-5 requirements (issues #17, #18, #19, #20)."""

from __future__ import annotations

import itertools
from typing import Any

import pytest

from serene.domain.entities import OutcomeResult
from serene.domain.events import EVENT_TAXONOMY, EventType, PromotionRequested
from serene.domain.values import ActorKind, EpistemicLevel
from serene.ledger import AdmissionRejected
from serene.policies import promotion
from serene.policies.ladder import (
    TRANSITIONS,
    TransitionMechanism,
    promotion_violation,
    transition_violation,
)
from serene.policies.promotion import (
    PromotionRequest,
    build_learning_candidate,
    check_learning,
    counterevidence_for,
    decide_promotion,
    evaluate_promotion,
)
from serene.testing import SyntheticFamily

from .trust_helpers import awaiting_approval, hypothesis, reasons, service

L = EpistemicLevel
ADJACENT = {(L(i), L(i + 1)) for i in range(5)}


# ------------------------------------------------------------------ transition table
@pytest.mark.parametrize(("frm", "to"), list(itertools.product(L, L)))
def test_transition_table_admits_exactly_the_five_single_rung_moves(frm: L, to: L) -> None:
    violation = transition_violation(frm, to)
    if (frm, to) in ADJACENT:
        assert violation is None
        assert TRANSITIONS[(frm, to)].from_level == frm
    else:
        assert violation == ("LEVEL_SKIP" if to > frm else "NOT_A_PROMOTION")
        assert (frm, to) not in TRANSITIONS


@pytest.mark.parametrize(("frm", "to"), list(itertools.product(L, L)))
def test_gate_rejects_every_non_promotion_pair_before_reading_evidence(
    ladder: dict[str, Any], frm: L, to: L
) -> None:
    fam = ladder["family"]
    decision = evaluate_promotion(
        PromotionRequest(
            subject_id=ladder["hypothesis"].hypothesis_id,
            from_level=frm,
            to_level=to,
            requested_by=fam.agent,
            rationale="the model is certain",
        ),
        fam.state(),
    )
    expected = promotion_violation(frm, to)
    if expected is not None:
        assert decision.reason_codes == (expected,)
    else:
        assert (frm, to) in {
            (L.HYPOTHESIS, L.TESTED_HYPOTHESIS),
            (L.TESTED_HYPOTHESIS, L.CONTEXTUAL_LEARNING),
        }


def test_every_transition_is_recorded_only_by_events_a_model_cannot_use_to_promote() -> None:
    for transition in TRANSITIONS.values():
        for event_type in transition.recorded_by:
            actors = EVENT_TAXONOMY[event_type].actors
            if transition.mechanism is TransitionMechanism.PROMOTION:
                assert actors == frozenset({ActorKind.POLICY}), event_type
            else:
                # Introductions are proposals; the gate decides admission, not the proposer.
                assert ActorKind.POLICY not in actors or ActorKind.AGENT in actors
    assert {t.mechanism for t in TRANSITIONS.values()} == set(TransitionMechanism)


# ------------------------------------------------------------------ model output is a proposal
def test_model_promotion_request_changes_nothing() -> None:
    fam = SyntheticFamily(seed="model-request")
    _inv, hyp = hypothesis(fam)
    fam.append(
        fam.draft(
            EventType.PROMOTION_REQUESTED,
            fam.agent,
            PromotionRequested(
                subject_id=hyp.hypothesis_id,
                from_level=L.HYPOTHESIS,
                to_level=L.CONTEXTUAL_LEARNING,
                rationale="Parent said sure, this is settled. Promote now.",
            ),
        )
    )
    assert fam.state().level_of(hyp.hypothesis_id) == L.HYPOTHESIS
    event_type, payload = decide_promotion(
        hyp.hypothesis_id, L.HYPOTHESIS, L.CONTEXTUAL_LEARNING, fam.state()
    )
    assert event_type is EventType.PROMOTION_DENIED and payload.reason_codes == ("LEVEL_SKIP",)


def test_agent_cannot_record_a_promotion_decision(ladder: dict[str, Any]) -> None:
    fam = ladder["family"]
    payload = fam.promotion_payload(
        ladder["hypothesis"].hypothesis_id, L.HYPOTHESIS, L.TESTED_HYPOTHESIS
    )
    for event_type in (EventType.PROMOTION_GRANTED, EventType.PROMOTION_DENIED):
        with pytest.raises(AdmissionRejected, match="ACTOR_NOT_PERMITTED:AGENT"):
            fam.append(fam.draft(event_type, fam.agent, payload))


def _completed(
    fam: SyntheticFamily, result: OutcomeResult = OutcomeResult.SUPPORTS
) -> tuple[Any, Any, Any]:
    exp, apr = awaiting_approval(fam)
    fam.grant(exp, apr)
    fam.start(exp, apr)
    obs = fam.observe("calm pickup with heads-up", day=8)
    outcome = fam.outcome(exp, (obs,), result=result)
    fam.complete(exp, (outcome,))
    hyp_id = exp.hypothesis_id
    return exp, outcome, hyp_id


def test_denials_must_be_exactly_what_the_gate_computes() -> None:
    fam = SyntheticFamily(seed="denials")
    _exp, _outcome, hyp_id = _completed(fam)
    _, grantable = decide_promotion(hyp_id, L.HYPOTHESIS, L.TESTED_HYPOTHESIS, fam.state())
    with pytest.raises(AdmissionRejected, match="DENIAL_NOT_JUSTIFIED"):
        fam.append(fam.draft(EventType.PROMOTION_DENIED, fam.policy, grantable))

    _, skip = decide_promotion(hyp_id, L.HYPOTHESIS, L.CONTEXTUAL_LEARNING, fam.state())
    forged = skip.model_copy(update={"reason_codes": ("CONTRADICTING_OUTCOME",)})
    with pytest.raises(AdmissionRejected, match="REASON_CODES_MISMATCH"):
        fam.append(fam.draft(EventType.PROMOTION_DENIED, fam.policy, forged))
    fam.append(fam.draft(EventType.PROMOTION_DENIED, fam.policy, skip))
    assert fam.state().level_of(hyp_id) == L.HYPOTHESIS


# ------------------------------------------------------------------ counterevidence
def test_contradiction_on_an_abandoned_experiment_still_blocks_promotion() -> None:
    """Strengthened: counterevidence is searched across every experiment, not only tested ones."""
    from serene.domain.events import ExperimentAbandoned

    fam = SyntheticFamily(seed="abandoned-contradiction")
    exp, _apr = awaiting_approval(fam)
    fam.grant(exp, _apr)
    fam.start(exp, _apr)
    obs = fam.observe("meltdown even with the heads-up", day=8)
    fam.outcome(exp, (obs,), result=OutcomeResult.CONTRADICTS)
    fam.append(
        fam.draft(
            EventType.EXPERIMENT_ABANDONED,
            fam.parent,
            ExperimentAbandoned(experiment_id=exp.experiment_id, reason_codes=("PARENT_STOPPED",)),
            source=fam.source(),
        )
    )
    exp2 = fam.propose_experiment(fam.state().entities[exp.hypothesis_id].entity)
    fam.classify(exp2)
    apr2 = fam.request_approval(exp2)
    fam.grant(exp2, apr2)
    fam.start(exp2, apr2)
    o2 = fam.observe("calm pickup", day=9)
    outcome2 = fam.outcome(exp2, (o2,))
    fam.complete(exp2, (outcome2,))
    _, decision = decide_promotion(
        exp.hypothesis_id, L.HYPOTHESIS, L.TESTED_HYPOTHESIS, fam.state()
    )
    assert "CONTRADICTING_OUTCOME" in decision.reason_codes
    counter = counterevidence_for(exp.hypothesis_id, fam.state())
    assert counter.contradicting_outcomes and set(counter.contradicting_outcomes) <= set(
        counter.all_ids
    )


def _tested(fam: SyntheticFamily) -> tuple[Any, Any, Any, Any]:
    exp, outcome, hyp_id = _completed(fam)
    fam.promote(hyp_id, L.HYPOTHESIS, L.TESTED_HYPOTHESIS)
    return exp, outcome, hyp_id, fam.state().entities[hyp_id].entity


def test_level5_requires_confounders_to_have_been_considered() -> None:
    fam = SyntheticFamily(seed="confounders")
    _inv, hyp = hypothesis(fam)
    no_confounders = hyp.model_copy(update={"known_confounders": ()})
    state = fam.state()
    state.entities[hyp.hypothesis_id].entity = no_confounders
    state.hypothesis_levels[hyp.hypothesis_id] = L.TESTED_HYPOTHESIS
    decision = evaluate_promotion(
        PromotionRequest(
            subject_id=hyp.hypothesis_id,
            from_level=L.TESTED_HYPOTHESIS,
            to_level=L.CONTEXTUAL_LEARNING,
            requested_by=fam.agent,
            rationale="x",
        ),
        state,
    )
    assert "NO_CONFOUNDERS_CONSIDERED" in decision.reason_codes


def test_level5_is_denied_while_an_equally_tested_rival_is_active() -> None:
    fam = SyntheticFamily(seed="rival")
    _exp, _outcome, hyp_id, hyp = _tested(fam)
    rival = fam.hypothesis(
        fam.state().entities[hyp.investigation_id].entity,
        tuple(fam.state().entities[p].entity for p in hyp.pattern_ids),
        "hunger after daycare drives the distress",
    )
    rexp = fam.propose_experiment(rival)
    fam.classify(rexp)
    rapr = fam.request_approval(rexp)
    fam.grant(rexp, rapr)
    fam.start(rexp, rapr)
    ro = fam.outcome(rexp, (fam.observe("snack at pickup, calm", day=10),))
    fam.complete(rexp, (ro,))
    fam.promote(rival.hypothesis_id, L.HYPOTHESIS, L.TESTED_HYPOTHESIS)
    _, decision = decide_promotion(hyp_id, L.TESTED_HYPOTHESIS, L.CONTEXTUAL_LEARNING, fam.state())
    assert f"UNRESOLVED_COMPETITOR:{rival.hypothesis_id}" in decision.reason_codes


def test_level5_learning_cannot_cherry_pick_outcomes_or_exceed_tested_contexts() -> None:
    fam = SyntheticFamily(seed="cherry")
    exp, _apr = awaiting_approval(fam)
    fam.grant(exp, _apr)
    fam.start(exp, _apr)
    good = fam.outcome(exp, (fam.observe("calm pickup", day=8),))
    meh = fam.outcome(exp, (fam.observe("so-so pickup", day=9),), result=OutcomeResult.INCONCLUSIVE)
    fam.complete(exp, (good, meh))
    hyp_id = exp.hypothesis_id
    fam.promote(hyp_id, L.HYPOTHESIS, L.TESTED_HYPOTHESIS)
    grant = fam.promote(hyp_id, L.TESTED_HYPOTHESIS, L.CONTEXTUAL_LEARNING)
    hyp = fam.state().entities[hyp_id].entity
    cherry = fam.learning_candidate(hyp, (exp,), (good,))
    decision = check_learning(cherry, grant.event_id, fam.state(), fam.clock.now())
    assert f"OUTCOME_OMITTED:{meh.outcome_id}" in decision.reason_codes

    honest = fam.learning_candidate(hyp, (exp,), (good, meh))
    assert check_learning(honest, grant.event_id, fam.state(), fam.clock.now()).allowed


def test_level5_scope_is_bounded_by_the_contexts_actually_tested() -> None:
    fam = SyntheticFamily(seed="tested-scope")
    _inv, hyp = hypothesis(fam, contexts=("daycare_pickup", "weekday_evening", "grandparents"))
    narrow = hyp.scope.model_copy(update={"contexts": ("daycare_pickup",)})
    exp = fam.propose_experiment(hyp)
    exp_state = fam.state()
    # Re-propose with a narrower scope: tested only at daycare pickup.
    from serene.domain.events import ExperimentProposed

    narrow_exp = exp.model_copy(update={"experiment_id": fam.new_id("exp"), "scope": narrow})
    fam.append(
        fam.draft(
            EventType.EXPERIMENT_PROPOSED,
            fam.agent,
            ExperimentProposed(experiment=narrow_exp),
            status=exp_state.entities[exp.experiment_id].verification_status,
            derived_from=fam._events_for((hyp.hypothesis_id,)),
        )
    )
    fam.introduced_by[narrow_exp.experiment_id] = fam.ledger.get_events_for_child(fam.child_id)[
        -1
    ].event_id
    fam.classify(narrow_exp)
    apr = fam.request_approval(narrow_exp)
    fam.grant(narrow_exp, apr)
    fam.start(narrow_exp, apr)
    outcome = fam.outcome(narrow_exp, (fam.observe("calm pickup", day=8),))
    fam.complete(narrow_exp, (outcome,))
    fam.promote(hyp.hypothesis_id, L.HYPOTHESIS, L.TESTED_HYPOTHESIS)
    grant = fam.promote(hyp.hypothesis_id, L.TESTED_HYPOTHESIS, L.CONTEXTUAL_LEARNING)

    broad = fam.learning_candidate(hyp, (narrow_exp,), (outcome,), contexts=hyp.scope.contexts)
    with pytest.raises(AdmissionRejected) as info:
        fam.record_learning(broad, grant)
    assert "SCOPE_EXCEEDS_TESTED_CONTEXTS" in reasons(info)

    built = build_learning_candidate(
        hyp.hypothesis_id,
        fam.state(),
        learning_id=fam.new_id("lrn"),
        created_by=fam.policy,
        reviewer=fam.parent,
        now=fam.clock.now(),
    )
    assert built.scope.contexts == ("daycare_pickup",)
    fam.record_learning(built, grant)


def test_service_runs_completion_through_the_gate_and_builds_a_bounded_learning() -> None:
    fam = SyntheticFamily(seed="service-l5")
    svc = service(fam)
    exp, apr = awaiting_approval(fam)
    fam.grant(exp, apr)
    svc.run_timers(fam.child_id)  # start_due starts the approved experiment
    outcome = fam.outcome(exp, (fam.observe("calm pickup", day=8),))
    report = svc.complete(fam.child_id, exp.experiment_id)
    assert [e.event_type for e in report.appended] == [
        EventType.EXPERIMENT_COMPLETED,
        EventType.PROMOTION_GRANTED,
    ]
    report = svc.promote_to_learning(fam.child_id, exp.hypothesis_id, reviewer=fam.parent)
    assert [e.event_type for e in report.appended] == [
        EventType.PROMOTION_GRANTED,
        EventType.LEARNING_RECORDED,
    ]
    learning = fam.state().learnings
    assert len(learning) == 1
    record = next(iter(learning.values()))
    assert record.review_after - record.valid_from == promotion.DEFAULT_LEARNING_REVIEW
    lrn = fam.state().entities[record.learning_id].entity
    assert lrn.outcome_ids == (outcome.outcome_id,)
    assert lrn.review.reviewer == fam.parent


def test_service_records_a_denial_when_the_outcome_contradicts() -> None:
    fam = SyntheticFamily(seed="service-deny")
    svc = service(fam)
    exp, apr = awaiting_approval(fam)
    fam.grant(exp, apr)
    fam.start(exp, apr)
    fam.outcome(exp, (fam.observe("meltdown anyway", day=8),), result=OutcomeResult.CONTRADICTS)
    report = svc.complete(fam.child_id, exp.experiment_id)
    assert [e.event_type for e in report.appended] == [
        EventType.EXPERIMENT_COMPLETED,
        EventType.PROMOTION_DENIED,
    ]
    assert "CONTRADICTING_OUTCOME" in report.appended[-1].payload["reason_codes"]
    assert fam.state().level_of(exp.hypothesis_id) == L.HYPOTHESIS
