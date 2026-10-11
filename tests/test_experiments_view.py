"""Experiments read view (issue #37): intervention, risk, reversibility, approval,
lifecycle phase, outcomes and promotion result, as the ledger recorded them."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from serene.domain.events import SafetyClass
from serene.experiments.lifecycle import ExperimentPhase
from serene.experiments.view import ApprovalView, ExperimentsView, build_experiments_view
from serene.projections.state import replay

from .experiments_view_fixture import (
    FIXTURE,
    ExperimentsFixture,
    build_fixture,
    fixture_json,
)


@pytest.fixture(scope="module")
def built() -> ExperimentsFixture:
    return build_fixture()


def _by_phase(view: ExperimentsView) -> dict[ExperimentPhase, list[object]]:
    out: dict[ExperimentPhase, list[object]] = {}
    for e in view.experiments:
        out.setdefault(e.phase, []).append(e)
    return out


def test_the_web_fixture_is_exactly_what_the_kernel_produces(built: ExperimentsFixture) -> None:
    assert FIXTURE.read_text(encoding="utf-8") == fixture_json(built.view), (
        "regenerate with: uv run python -m tests.experiments_view_fixture"
    )
    assert ExperimentsView.model_validate_json(FIXTURE.read_text(encoding="utf-8")) == built.view


def test_every_lifecycle_phase_is_represented(built: ExperimentsFixture) -> None:
    assert set(_by_phase(built.view)) == set(ExperimentPhase)


def test_every_experiment_carries_the_fields_the_surface_shows(built: ExperimentsFixture) -> None:
    for e in built.view.experiments:
        assert e.intervention.description and e.intervention.category
        assert isinstance(e.intervention.reversible, bool)
        assert e.phase in ExperimentPhase
        if e.phase is not ExperimentPhase.PROPOSED:
            assert e.safety_class is not None and e.classification_reasons
    completed = [e for e in built.view.experiments if e.phase is ExperimentPhase.COMPLETED]
    assert {e.promotion.granted for e in completed if e.promotion} == {True, False}
    assert all(e.outcomes for e in completed)


def test_red_is_blocked_with_reasons_and_never_open_for_a_decision(
    built: ExperimentsFixture,
) -> None:
    (red,) = [e for e in built.view.experiments if e.safety_class is SafetyClass.RED]
    assert red.phase is ExperimentPhase.BLOCKED
    assert "RED_FAIL_CLOSED" in red.blocked_reasons
    assert red.approval is None
    open_ids = [
        e.experiment_id
        for e in built.view.experiments
        if e.approval is not None and e.approval.decision_open
    ]
    assert open_ids and all(
        e.safety_class is not SafetyClass.RED
        for e in built.view.experiments
        if e.experiment_id in open_ids
    )
    data = json.loads(built.view.model_dump_json())
    approval = next(e["approval"] for e in data["experiments"] if e["approval"])
    approval |= {"safety_class": "RED", "decision_open": True}
    with pytest.raises(ValidationError, match="RED request can never be open"):
        ApprovalView.model_validate_json(json.dumps(approval))


def test_decisions_record_their_channel_and_time(built: ExperimentsFixture) -> None:
    decided = [
        e.approval
        for e in built.view.experiments
        if e.approval is not None and e.approval.state.value in {"GRANTED", "REJECTED"}
    ]
    assert decided and all(a.decided_via == "WEB_APP" and a.decided_at for a in decided)


def test_the_view_holds_no_child_or_actor_identifiers(built: ExperimentsFixture) -> None:
    text = fixture_json(built.view)
    assert "chd_" not in text and "act_" not in text
    assert "requested_of" not in text and "child_id" not in text


def test_the_view_is_rebuilt_from_the_ledger_alone(built: ExperimentsFixture) -> None:
    fam = built.fam
    rebuilt = build_experiments_view(
        replay(fam.ledger.get_events_for_child(fam.child_id)), fam.clock.now()
    )
    assert rebuilt == built.view
