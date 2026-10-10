"""Learning validity, review and staleness: time travel, drift, contradiction and the
"stale is never surfaced as ACTIVE" rule (issue #20)."""

from __future__ import annotations

import itertools
from datetime import timedelta
from typing import Any

import pytest

from serene.domain.entities import LearningStatus, OutcomeResult
from serene.domain.events import EventType, LearningStatusChanged
from serene.experiments import lifecycle
from serene.ledger import AdmissionRejected
from serene.policies.learning import (
    LEARNING_TRANSITIONS,
    STALE_AFTER,
    check_status_change,
    effective_status,
    surfaceable_learnings,
)
from serene.projections.views import effective_learning_status
from serene.testing import SyntheticFamily, build_full_ladder

from .trust_helpers import ctx, observe_with_contexts, service

S = LearningStatus


def _ladder(seed: str) -> tuple[SyntheticFamily, str, dict[str, Any]]:
    ladder = build_full_ladder(seed=seed)
    fam = ladder["family"]
    return fam, ladder["learning"].learning_id, ladder


def _status(fam: SyntheticFamily, lrn: str) -> LearningStatus:
    return fam.state().learnings[lrn].status


def test_learnings_carry_valid_from_and_review_after() -> None:
    fam, lrn, ladder = _ladder("validity-fields")
    record = fam.state().learnings[lrn]
    assert record.valid_from == ladder["learning"].validity.valid_from
    assert record.review_after == ladder["learning"].validity.review_after
    assert record.valid_from < record.review_after


def test_time_travel_across_review_after_then_stale() -> None:
    fam, lrn, _ = _ladder("validity-time")
    svc = service(fam)
    record = fam.state().learnings[lrn]
    assert [r.learning_id for r in surfaceable_learnings(fam.state(), fam.clock.now())] == [lrn]

    fam.clock.advance(record.review_after - fam.clock.now())  # exactly at review_after
    state = fam.state()
    assert state.learnings[lrn].status is S.ACTIVE  # ledger not yet updated...
    assert effective_status(state.learnings[lrn], state, fam.clock.now()) is S.NEEDS_REVIEW
    assert effective_learning_status(state.learnings[lrn], fam.clock.now()) is S.NEEDS_REVIEW
    assert surfaceable_learnings(state, fam.clock.now()) == []  # ...but it is never surfaced

    report = svc.run_timers(fam.child_id)
    assert [e.payload["to_status"] for e in report.appended] == ["NEEDS_REVIEW"]
    assert report.appended[0].payload["reason_codes"] == ["REVIEW_DUE"]
    assert svc.run_timers(fam.child_id).appended == []  # idempotent

    fam.clock.advance(STALE_AFTER)
    report = svc.run_timers(fam.child_id)
    assert [e.payload["to_status"] for e in report.appended] == ["STALE"]
    assert _status(fam, lrn) is S.STALE
    assert surfaceable_learnings(fam.state(), fam.clock.now()) == []


def test_context_drift_triggers_retest() -> None:
    fam, _lrn, _ = _ladder("validity-drift")
    observe_with_contexts(
        fam, "New nanny does pickups now", ("daycare_pickup", "new_caregiver"), day=20
    )
    report = service(fam).run_timers(fam.child_id)
    assert [e.payload["to_status"] for e in report.appended] == ["NEEDS_RETEST"]
    assert report.appended[0].payload["reason_codes"] == ["CONTEXT_DRIFT:new_caregiver"]
    assert surfaceable_learnings(fam.state(), fam.clock.now()) == []


def test_drift_outside_the_learning_scope_is_not_meaningful() -> None:
    fam, lrn, _ = _ladder("validity-drift-elsewhere")
    observe_with_contexts(
        fam, "New swim teacher on Saturdays", ("swim_class", "new_caregiver"), day=20
    )
    assert service(fam).run_timers(fam.child_id).appended == []
    assert _status(fam, lrn) is S.ACTIVE


def _contradict(fam: SyntheticFamily, ladder: dict[str, Any], result: OutcomeResult) -> Any:
    exp = fam.propose_experiment(ladder["hypothesis"])
    fam.classify(exp)
    apr = fam.request_approval(exp)
    fam.grant(exp, apr)
    fam.start(exp, apr)
    outcome = fam.outcome(exp, (fam.observe("retest pickup", day=30),), result=result)
    return exp, outcome


def test_contradiction_triggers_retest_and_reactivation_needs_a_successful_retest() -> None:
    fam, lrn, ladder = _ladder("validity-contradiction")
    svc = service(fam)
    exp, outcome = _contradict(fam, ladder, OutcomeResult.CONTRADICTS)
    fam.complete(exp, (outcome,))
    report = svc.run_timers(fam.child_id)
    assert [e.payload["reason_codes"] for e in report.appended] == [["CONTRADICTING_OUTCOME"]]
    assert _status(fam, lrn) is S.NEEDS_RETEST

    reactivate = fam.draft(
        EventType.LEARNING_STATUS_CHANGED,
        fam.policy,
        LearningStatusChanged(
            learning_id=lrn,
            from_status=S.NEEDS_RETEST,
            to_status=S.ACTIVE,
            reason_codes=("RETESTED",),
        ),
    )
    with pytest.raises(AdmissionRejected, match="REACTIVATION_NOT_JUSTIFIED:NO_SUCCESSFUL_RETEST"):
        fam.append(reactivate)

    retest, ok = _contradict(fam, ladder, OutcomeResult.SUPPORTS)
    fam.complete(retest, (ok,))
    fam.append(reactivate)
    assert _status(fam, lrn) is S.ACTIVE
    assert [r.learning_id for r in surfaceable_learnings(fam.state(), fam.clock.now())] == [lrn]


def test_refuted_hypothesis_deprecates_the_learning_terminally() -> None:
    from serene.domain.events import HypothesisRefuted

    fam, lrn, ladder = _ladder("validity-refuted")
    _exp, outcome = _contradict(fam, ladder, OutcomeResult.CONTRADICTS)
    fam.append(
        fam.draft(
            EventType.HYPOTHESIS_REFUTED,
            fam.policy,
            HypothesisRefuted(
                hypothesis_id=ladder["hypothesis"].hypothesis_id,
                outcome_ids=(outcome.outcome_id,),
                reason_codes=("CONTRADICTING_OUTCOME",),
            ),
        )
    )
    report = service(fam).run_timers(fam.child_id)
    assert report.appended[-1].payload["to_status"] == "DEPRECATED"
    assert _status(fam, lrn) is S.DEPRECATED
    assert (
        lifecycle.learning_validity_due(
            fam.state(), fam.clock.now() + timedelta(days=999), ctx(fam)
        )
        == []
    )


@pytest.mark.parametrize(("frm", "to"), list(itertools.product(S, S)))
def test_every_status_transition_is_decided_by_the_table(frm: S, to: S) -> None:
    fam, lrn, _ = _ladder("validity-table")
    state = fam.state()
    state.learnings[lrn].status = frm
    payload = LearningStatusChanged(
        learning_id=lrn, from_status=frm, to_status=to, reason_codes=("X",)
    )
    decision = check_status_change(payload, state, fam.clock.now())
    if to not in LEARNING_TRANSITIONS[frm]:
        assert decision.reason_codes == (f"ILLEGAL_TRANSITION:{frm.value}_TO_{to.value}",)
    elif to is not S.ACTIVE:
        assert decision.allowed  # lowering trust is always admissible
    else:
        # Raising trust without a recorded retest is refused from NEEDS_RETEST only.
        assert decision.allowed is (frm is not S.NEEDS_RETEST)


def test_reactivation_past_review_after_is_refused() -> None:
    fam, lrn, _ = _ladder("validity-reactivate-late")
    svc = service(fam)
    fam.clock.advance(timedelta(days=61))
    svc.run_timers(fam.child_id)
    assert _status(fam, lrn) is S.NEEDS_REVIEW
    draft = fam.draft(
        EventType.LEARNING_STATUS_CHANGED,
        fam.policy,
        LearningStatusChanged(
            learning_id=lrn,
            from_status=S.NEEDS_REVIEW,
            to_status=S.ACTIVE,
            reason_codes=("LOOKS_FINE",),
        ),
    )
    with pytest.raises(AdmissionRejected, match="REACTIVATION_NOT_JUSTIFIED:REVIEW_DUE"):
        fam.append(draft)
