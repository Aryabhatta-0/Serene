"""The synthetic experiments fixture the web surface is tested with (issue #37).

It is produced by running the real kernel, not written by hand: one synthetic
family whose experiments are driven through the lifecycle service into every
phase, with every parent decision made through the web channel
(`WebApprovalChannel`), so each recorded approval is a WEB_APP decision that
passed the ledger's admission. `tests/test_experiments_view.py` checks that
the checked-in JSON is exactly what this produces. To regenerate it:

    uv run python -m tests.experiments_view_fixture
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from serene.adapters.web import WebApprovalChannel, WebApprovalCommand, WebDecision
from serene.domain.entities import Burden, Experiment, Intervention, OutcomeResult
from serene.experiments.view import ExperimentsView, build_experiments_view
from serene.policies.experiments import OUTCOME_GRACE
from serene.testing import SyntheticFamily

from .trust_helpers import C, hypothesis, intervention, service

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "app" / "web" / "fixtures" / "synthetic-experiments.json"
# The command the web app builds to approve the GREEN request awaiting a decision.
COMMAND_EXAMPLE = ROOT / "app" / "web" / "fixtures" / "approval-command.example.json"
EXAMPLE_REQUEST_ID = "example-request-0001"


@dataclass
class ExperimentsFixture:
    fam: SyntheticFamily
    web: WebApprovalChannel
    view: ExperimentsView
    awaiting_green: Experiment


def command(
    fam: SyntheticFamily, exp: Experiment, decision: WebDecision, request_id: str
) -> WebApprovalCommand:
    """What a parent who was shown this experiment's request sends."""
    record = fam.state().experiments[exp.experiment_id]
    assert record.approval_request_id is not None
    request = fam.state().approvals[record.approval_request_id]
    return WebApprovalCommand(
        approval_request_id=request.approval_request_id,
        decision=decision,
        shown_intervention_digest=request.intervention_digest,
        shown_safety_class=request.safety_class,
        request_id=request_id,
    )


def build_fixture() -> ExperimentsFixture:
    fam = SyntheticFamily(seed="experiments-fixture")
    svc = service(fam)
    web = WebApprovalChannel(fam.ledger, fam.clock, new_source_id=lambda: fam.new_id("src"))
    serial = iter(range(1, 100))

    def new(iv: Intervention | None = None) -> Experiment:
        _inv, hyp = hypothesis(fam)
        return fam.propose_experiment(hyp, iv)

    def requested(exp: Experiment) -> None:
        svc.classify(fam.child_id, exp.experiment_id)
        svc.request_approval(fam.child_id, exp.experiment_id, parent_id=fam.parent.actor_id)

    def decide(exp: Experiment, decision: WebDecision) -> None:
        result = web.decide(
            fam.parent,
            fam.child_id,
            command(fam, exp, decision, f"fixture-decision-{next(serial):04d}"),
        )
        assert result.accepted, result.reason_codes

    def start(exp: Experiment) -> None:
        apr = fam.state().experiments[exp.experiment_id].approval_request_id
        assert apr is not None
        fam.start(exp, apr)

    # Completed, and the Promotion Gate granted 3 -> 4.
    supported = new()
    requested(supported)
    decide(supported, WebDecision.APPROVE)
    start(supported)
    fam.outcome(supported, (fam.observe("calm pickup after the heads-up", day=8),))
    svc.complete(fam.child_id, supported.experiment_id)

    # Completed, and the outcome contradicted the hypothesis.
    contradicted = new(intervention(C.ENVIRONMENT, "Dim the hallway lights before leaving"))
    requested(contradicted)
    decide(contradicted, WebDecision.APPROVE)
    start(contradicted)
    fam.outcome(
        contradicted,
        (fam.observe("tearful pickup with the lights dimmed", day=8),),
        OutcomeResult.CONTRADICTS,
    )
    svc.complete(fam.child_id, contradicted.experiment_id)

    # The parent declined.
    declined = new(intervention(C.PLAY_ACTIVITY, "Bring a small toy to hand over at pickup"))
    requested(declined)
    decide(declined, WebDecision.DECLINE)

    # Nobody decided before the request expired: parked, never approved.
    parked = new(intervention(C.COMMUNICATION, "Use a picture card to show what comes next"))
    requested(parked)
    fam.clock.advance(timedelta(hours=49))
    svc.run_timers(fam.child_id)

    # Running, then past its outcome deadline with no outcome yet.
    overdue = new(intervention(days=1))
    requested(overdue)
    decide(overdue, WebDecision.APPROVE)
    start(overdue)
    fam.clock.advance(timedelta(days=1) + OUTCOME_GRACE + timedelta(hours=1))

    # Running and waiting for its outcome.
    running = new(intervention(C.ROUTINE_TIMING, "Leave daycare ten minutes earlier"))
    requested(running)
    decide(running, WebDecision.APPROVE)
    start(running)

    # Approved, not started yet.
    approved = new(intervention(C.TRANSITION_SUPPORT, "Sing the goodbye song before leaving"))
    requested(approved)
    decide(approved, WebDecision.APPROVE)

    # RED: classified and blocked. It never gets an approval request.
    red = new(
        Intervention(
            category=C.MEDICATION,
            description="Give a calming supplement before pickup",
            reversible=True,
            max_duration_days=7,
            burden=Burden.LOW,
        )
    )
    svc.classify(fam.child_id, red.experiment_id)

    # AMBER and GREEN requests awaiting the parent's decision.
    amber = new(intervention(C.SLEEP_SCHEDULE, "Move the afternoon nap thirty minutes earlier"))
    requested(amber)
    awaiting_green = new()
    requested(awaiting_green)

    # Classified but no request yet, and only proposed.
    classified = new(intervention(C.ENVIRONMENT, "Wait in the quiet room for pickup"))
    svc.classify(fam.child_id, classified.experiment_id)
    new(intervention(C.COMMUNICATION, "Talk through the evening plan at drop-off"))

    view = build_experiments_view(fam.state(), fam.clock.now())
    return ExperimentsFixture(fam, web, view, awaiting_green)


def fixture_json(view: ExperimentsView) -> str:
    return view.model_dump_json(indent=2) + "\n"


def command_example(fixture: ExperimentsFixture) -> str:
    example = command(fixture.fam, fixture.awaiting_green, WebDecision.APPROVE, EXAMPLE_REQUEST_ID)
    return json.dumps(example.model_dump(mode="json"), indent=2) + "\n"


if __name__ == "__main__":
    built = build_fixture()
    FIXTURE.write_text(fixture_json(built.view), encoding="utf-8", newline="\n")
    COMMAND_EXAMPLE.write_text(command_example(built), encoding="utf-8", newline="\n")
    print(f"wrote {FIXTURE.relative_to(ROOT)} and {COMMAND_EXAMPLE.relative_to(ROOT)}")
