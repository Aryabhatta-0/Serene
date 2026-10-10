"""N-of-1 lifecycle: happy path, timers, WAITING_FOR_OUTCOME timeout, structural
requirements and reconstruction from the ledger (issues #24, #25, #26)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from serene.domain.entities import Burden
from serene.domain.events import EventType, ExperimentOutcomeTimedOut, ExperimentProposed
from serene.domain.values import EpistemicLevel, VerificationStatus
from serene.experiments import lifecycle
from serene.experiments.lifecycle import ExperimentPhase, experiment_phase
from serene.ledger import AdmissionRejected
from serene.policies.experiments import OUTCOME_GRACE, outcome_due_at, requirement_violations
from serene.projections import replay
from serene.testing import SyntheticFamily

from .trust_helpers import C, ctx, event_types, hypothesis, intervention, reasons, service

E = EventType


def _proposed(fam: SyntheticFamily, **overrides: object) -> object:
    _inv, hyp = hypothesis(fam)
    exp = fam.propose_experiment(hyp)
    if not overrides:
        return exp
    forged = exp.model_copy(update={"experiment_id": fam.new_id("exp"), **overrides})
    event = fam.append(
        fam.draft(
            E.EXPERIMENT_PROPOSED,
            fam.agent,
            ExperimentProposed(experiment=forged),
            status=VerificationStatus.UNVERIFIED,
            derived_from=fam._events_for((hyp.hypothesis_id,)),
        )
    )
    fam.introduced_by[forged.experiment_id] = event.event_id
    return forged


def test_green_happy_path_end_to_end_is_reconstructable_from_the_ledger() -> None:
    fam = SyntheticFamily(seed="lifecycle-happy")
    svc = service(fam)
    exp = _proposed(fam)
    exp_id = exp.experiment_id  # type: ignore[attr-defined]
    assert [e.event_type for e in svc.classify(fam.child_id, exp_id).appended] == [
        E.EXPERIMENT_CLASSIFIED
    ]
    report = svc.request_approval(fam.child_id, exp_id, parent_id=fam.parent.actor_id)
    apr = report.appended[0].payload["approval_request_id"]
    assert report.appended[0].payload["safety_class"] == "GREEN"

    # Time travel: the single nudge fires at half the window, never twice.
    assert svc.run_timers(fam.child_id).appended == []
    fam.clock.advance(timedelta(hours=25))
    assert [e.event_type for e in svc.run_timers(fam.child_id).appended] == [E.APPROVAL_NUDGED]
    assert svc.run_timers(fam.child_id).appended == []

    fam.grant(exp, apr)  # type: ignore[arg-type]
    started = svc.run_timers(fam.child_id).appended
    assert [e.event_type for e in started] == [E.EXPERIMENT_STARTED]
    record = fam.state().experiments[exp_id]
    assert experiment_phase(record, fam.clock.now()) is ExperimentPhase.WAITING_FOR_OUTCOME

    fam.outcome(exp, (fam.observe("calm pickup after heads-up", day=8),))  # type: ignore[arg-type]
    done = svc.complete(fam.child_id, exp_id)
    assert [e.event_type for e in done.appended] == [E.EXPERIMENT_COMPLETED, E.PROMOTION_GRANTED]
    assert fam.state().level_of(exp.hypothesis_id) is EpistemicLevel.TESTED_HYPOTHESIS  # type: ignore[attr-defined]

    events = fam.ledger.get_events_for_child(fam.child_id)
    lifecycle_types = [
        e.event_type
        for e in events
        if e.event_type.name.startswith(("EXPERIMENT", "APPROVAL", "PROMOTION", "OUTCOME"))
    ]
    assert lifecycle_types == [
        E.EXPERIMENT_PROPOSED,
        E.EXPERIMENT_CLASSIFIED,
        E.APPROVAL_REQUESTED,
        E.APPROVAL_NUDGED,
        E.APPROVAL_GRANTED,
        E.EXPERIMENT_STARTED,
        E.OUTCOME_REPORTED,
        E.EXPERIMENT_COMPLETED,
        E.PROMOTION_GRANTED,
    ]
    rebuilt = replay(events)
    assert rebuilt.experiments[exp_id].status.value == "COMPLETED"
    assert rebuilt.approvals[apr].consumed_by is not None
    # Every lifecycle event points back to the experiment proposal.
    proposal = fam.introduced_by[exp_id]
    for event in events:
        if event.event_type in {
            E.EXPERIMENT_CLASSIFIED,
            E.APPROVAL_REQUESTED,
            E.EXPERIMENT_STARTED,
        }:
            assert proposal in event.derived_from


def test_approval_timeout_parks_and_never_approves() -> None:
    fam = SyntheticFamily(seed="lifecycle-park")
    svc = service(fam)
    exp = _proposed(fam)
    exp_id = exp.experiment_id  # type: ignore[attr-defined]
    svc.classify(fam.child_id, exp_id)
    apr = (
        svc.request_approval(fam.child_id, exp_id, parent_id=fam.parent.actor_id)
        .appended[0]
        .payload["approval_request_id"]
    )
    fam.clock.advance(timedelta(hours=49))
    types = [e.event_type for e in svc.run_timers(fam.child_id).appended]
    assert types == [E.APPROVAL_TIMED_OUT]  # past the nudge window too: no late nudge
    state = fam.state()
    assert state.approvals[apr].state.value == "PARKED_UNRESOLVED"
    assert (
        experiment_phase(state.experiments[exp_id], fam.clock.now())
        is ExperimentPhase.PARKED_UNRESOLVED
    )
    with pytest.raises(AdmissionRejected):
        fam.grant(exp, apr)  # type: ignore[arg-type]
    assert svc.run_timers(fam.child_id).appended == []


def _started(fam: SyntheticFamily, days: int = 7) -> tuple[object, str]:
    exp = _proposed(fam, intervention=intervention(days=days)) if days != 7 else _proposed(fam)
    fam.classify(exp)  # type: ignore[arg-type]
    apr = fam.request_approval(exp)  # type: ignore[arg-type]
    fam.grant(exp, apr)  # type: ignore[arg-type]
    fam.start(exp, apr)  # type: ignore[arg-type]
    return exp, apr


def test_waiting_for_outcome_times_out_instead_of_hanging_forever() -> None:
    fam = SyntheticFamily(seed="lifecycle-outcome-timeout")
    svc = service(fam)
    exp, _apr = _started(fam)
    exp_id = exp.experiment_id  # type: ignore[attr-defined]
    record = fam.state().experiments[exp_id]
    due = outcome_due_at(record)
    assert due == record.started_at + timedelta(days=7) + OUTCOME_GRACE  # type: ignore[operator]

    forged = fam.draft(
        E.EXPERIMENT_OUTCOME_TIMED_OUT,
        fam.policy,
        ExperimentOutcomeTimedOut(experiment_id=exp_id, outcome_due_at=due, policy_version="x"),  # type: ignore[arg-type]
    )
    with pytest.raises(AdmissionRejected, match="NOT_YET_DUE"):
        fam.append(forged)
    assert lifecycle.timeout_due(fam.state(), fam.clock.now(), ctx(fam)) == []

    fam.clock.advance(timedelta(days=10))
    assert (
        experiment_phase(fam.state().experiments[exp_id], fam.clock.now())
        is ExperimentPhase.OUTCOME_OVERDUE
    )
    # A late report after the window closed is refused rather than silently accepted.
    with pytest.raises(AdmissionRejected) as info:
        fam.outcome(exp, (fam.observe("calm pickup, finally", day=20),))  # type: ignore[arg-type]
    assert "OUTCOME_WINDOW_CLOSED" in reasons(info)

    appended = svc.run_timers(fam.child_id).appended
    assert [e.event_type for e in appended] == [E.EXPERIMENT_OUTCOME_TIMED_OUT]
    record = fam.state().experiments[exp_id]
    assert record.status.value == "ABANDONED" and record.outcome_timed_out
    with pytest.raises(AdmissionRejected, match="NOT_WAITING_FOR_OUTCOME"):
        fam.append(forged)


def test_deadline_with_reported_outcomes_completes_and_goes_to_the_gate() -> None:
    fam = SyntheticFamily(seed="lifecycle-deadline-complete")
    svc = service(fam)
    exp, _apr = _started(fam)
    fam.outcome(exp, (fam.observe("calm pickup", day=8),))  # type: ignore[arg-type]
    exp_id = exp.experiment_id  # type: ignore[attr-defined]
    due = outcome_due_at(fam.state().experiments[exp_id])
    forged = fam.draft(
        E.EXPERIMENT_OUTCOME_TIMED_OUT,
        fam.policy,
        ExperimentOutcomeTimedOut(experiment_id=exp_id, outcome_due_at=due, policy_version="x"),  # type: ignore[arg-type]
    )
    fam.clock.advance(timedelta(days=11))
    with pytest.raises(AdmissionRejected, match="OUTCOMES_REPORTED_COMPLETE_INSTEAD"):
        fam.append(forged)
    assert [e.event_type for e in svc.run_timers(fam.child_id).appended] == [E.EXPERIMENT_COMPLETED]


# ------------------------------------------------------------------ requirements (#26)
@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"comparison": "n/a"}, "MISSING_COMPARISON"),
        ({"outcome_measure": "TBD"}, "MISSING_OUTCOME_MEASURE"),
        ({"comparison": "parent-reported calm pickup (yes/no)"}, "INDISTINCT_SPECIFICATION"),
    ],
)
def test_unfit_experiments_are_blocked_with_an_explicit_reason(
    overrides: dict[str, str], code: str
) -> None:
    fam = SyntheticFamily(seed=f"req-{code}")
    svc = service(fam)
    exp = _proposed(fam, **overrides)
    report = svc.classify(fam.child_id, exp.experiment_id)  # type: ignore[attr-defined]
    assert [e.event_type for e in report.appended] == [
        E.EXPERIMENT_CLASSIFIED,
        E.EXPERIMENT_BLOCKED,
    ]
    assert code in report.appended[-1].payload["reason_codes"]
    assert (
        svc.request_approval(
            fam.child_id, exp.experiment_id, parent_id=fam.parent.actor_id
        ).appended
        == []
    )  # type: ignore[attr-defined]


def test_scope_broader_than_the_hypothesis_is_rejected_at_the_approval_gate() -> None:
    fam = SyntheticFamily(seed="req-scope")
    _inv, hyp = hypothesis(fam)
    exp = fam.propose_experiment(hyp)
    broad = exp.model_copy(
        update={
            "experiment_id": fam.new_id("exp"),
            "scope": exp.scope.model_copy(update={"contexts": (*exp.scope.contexts, "bedtime")}),
        }
    )
    assert "SCOPE_EXCEEDS_HYPOTHESIS" in requirement_violations(broad, fam.state())
    event = fam.append(
        fam.draft(
            E.EXPERIMENT_PROPOSED,
            fam.agent,
            ExperimentProposed(experiment=broad),
            status=VerificationStatus.UNVERIFIED,
            derived_from=fam._events_for((hyp.hypothesis_id,)),
        )
    )
    fam.introduced_by[broad.experiment_id] = event.event_id
    fam.classify(broad)  # a POLICY actor that skips the BLOCKED step...
    with pytest.raises(AdmissionRejected) as info:
        fam.request_approval(broad)  # ...still cannot request approval
    assert "EXPERIMENT_REQUIREMENTS_UNMET" in reasons(info)


def test_complete_experiment_with_reversible_low_burden_intervention_passes(
    family: SyntheticFamily,
) -> None:
    exp = _proposed(family)
    assert requirement_violations(exp, family.state()) == []  # type: ignore[arg-type]


def test_amber_lifecycle_never_nudges_and_waits_longer() -> None:
    fam = SyntheticFamily(seed="lifecycle-amber")
    svc = service(fam)
    exp = _proposed(
        fam,
        intervention=intervention(
            C.MEAL_TIMING, "Offer the snack before leaving daycare", burden=Burden.LOW
        ),
    )
    svc.classify(fam.child_id, exp.experiment_id)  # type: ignore[attr-defined]
    report = svc.request_approval(fam.child_id, exp.experiment_id, parent_id=fam.parent.actor_id)  # type: ignore[attr-defined]
    assert report.appended[0].payload["safety_class"] == "AMBER"
    fam.clock.advance(timedelta(hours=60))
    assert svc.run_timers(fam.child_id).appended == []
    fam.clock.advance(timedelta(hours=13))
    assert [e.event_type for e in svc.run_timers(fam.child_id).appended] == [E.APPROVAL_TIMED_OUT]
    assert E.APPROVAL_NUDGED not in event_types(fam)


def test_timeout_of_an_abandoned_experiments_request_keeps_it_abandoned() -> None:
    from serene.domain.events import ExperimentAbandoned

    fam = SyntheticFamily(seed="lifecycle-abandon-timeout")
    svc = service(fam)
    exp = _proposed(fam)
    exp_id = exp.experiment_id  # type: ignore[attr-defined]
    svc.classify(fam.child_id, exp_id)
    svc.request_approval(fam.child_id, exp_id, parent_id=fam.parent.actor_id)
    fam.append(
        fam.draft(
            E.EXPERIMENT_ABANDONED,
            fam.parent,
            ExperimentAbandoned(experiment_id=exp_id, reason_codes=("PARENT_DECLINED",)),
            source=fam.source(),
        )
    )
    fam.clock.advance(timedelta(hours=49))
    assert [e.event_type for e in svc.run_timers(fam.child_id).appended] == [E.APPROVAL_TIMED_OUT]
    assert fam.state().experiments[exp_id].status.value == "ABANDONED"
