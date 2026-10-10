"""Causal Twin domain model: derived relationship state, validation, observational vs
experimental support (issue #27)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from serene.causal import RelationshipStatus, SupportKind, build_causal_twin, build_edge
from serene.domain.canonical import canonical_digest
from serene.domain.entities import OutcomeResult
from serene.domain.events import EventType, HypothesisRefuted
from serene.domain.values import EpistemicLevel
from serene.projections import replay
from serene.testing import SyntheticFamily

from .trust_helpers import awaiting_approval, hypothesis


def test_full_ladder_edge_is_supported_by_experiment_with_full_provenance(
    ladder: dict[str, Any],
) -> None:
    fam = ladder["family"]
    twin = build_causal_twin(
        fam.state(),
        fam.clock.now(),
        labels={ladder["hypothesis"].hypothesis_id: ("pickup_warning", "pickup_distress")},
    )
    edge = twin.edge(ladder["hypothesis"].hypothesis_id)
    assert edge.status is RelationshipStatus.SUPPORTED
    assert edge.epistemic_level is EpistemicLevel.CONTEXTUAL_LEARNING
    assert edge.experimentally_supported
    assert {s.kind for s in edge.support} == {SupportKind.OBSERVATIONAL, SupportKind.EXPERIMENTAL}
    assert edge.experiments == (ladder["experiment"].experiment_id,)
    assert edge.validity is not None and edge.learning_status is not None
    assert set(edge.raw_evidence) >= {e for o in ladder["observations"] for e in o.evidence_ids}
    assert edge.confounders == ("variable nap length",)
    assert twin.variables == ("pickup_distress", "pickup_warning")
    assert not any("confidence" in name or "score" in name for name in type(edge).model_fields)


def test_untested_hypothesis_is_only_an_observational_candidate(family: SyntheticFamily) -> None:
    _inv, hyp = hypothesis(family)
    edge = build_edge(hyp.hypothesis_id, family.state(), family.clock.now())
    assert edge.status is RelationshipStatus.CANDIDATE
    assert {s.kind for s in edge.support} == {SupportKind.OBSERVATIONAL}
    assert not edge.experimentally_supported


def test_observational_support_cannot_be_declared_supported(family: SyntheticFamily) -> None:
    _inv, hyp = hypothesis(family)
    edge = build_edge(hyp.hypothesis_id, family.state(), family.clock.now())
    with pytest.raises(ValidationError, match="observational support alone"):
        type(edge).model_validate(
            {
                **edge.model_dump(),
                "status": RelationshipStatus.SUPPORTED,
                "epistemic_level": EpistemicLevel.TESTED_HYPOTHESIS,
            }
        )


def test_edge_without_provenance_is_rejected(family: SyntheticFamily) -> None:
    _inv, hyp = hypothesis(family)
    edge = build_edge(hyp.hypothesis_id, family.state(), family.clock.now())
    with pytest.raises(ValidationError):
        type(edge).model_validate({**edge.model_dump(), "raw_evidence": ()})
    stripped = edge.provenance.model_copy(update={"derived_from": (), "source_ids": ()})
    with pytest.raises(ValidationError, match="lineage provenance"):
        type(edge).model_validate({**edge.model_dump(), "provenance": stripped.model_dump()})


def test_contradiction_contests_then_refutation_refutes(family: SyntheticFamily) -> None:
    exp, apr = awaiting_approval(family)
    family.grant(exp, apr)
    family.start(exp, apr)
    outcome = family.outcome(
        exp, (family.observe("meltdown despite heads-up", day=8),), result=OutcomeResult.CONTRADICTS
    )
    edge = build_edge(exp.hypothesis_id, family.state(), family.clock.now())
    assert edge.status is RelationshipStatus.CANDIDATE
    assert edge.contradicting_outcomes == (outcome.outcome_id,)
    family.append(
        family.draft(
            EventType.HYPOTHESIS_REFUTED,
            family.policy,
            HypothesisRefuted(
                hypothesis_id=exp.hypothesis_id,
                outcome_ids=(outcome.outcome_id,),
                reason_codes=("CONTRADICTING_OUTCOME",),
            ),
        )
    )
    assert (
        build_edge(exp.hypothesis_id, family.state(), family.clock.now()).status
        is RelationshipStatus.REFUTED
    )


def test_stale_learning_downgrades_a_supported_edge(ladder: dict[str, Any]) -> None:
    fam = ladder["family"]
    hyp_id = ladder["hypothesis"].hypothesis_id
    later = fam.clock.now() + timedelta(days=120)
    edge = build_edge(hyp_id, fam.state(), later)
    assert edge.learning_status is not None and edge.learning_status.value == "STALE"
    assert edge.status is RelationshipStatus.CANDIDATE


def test_twin_is_a_deterministic_function_of_the_ledger(ladder: dict[str, Any]) -> None:
    fam = ladder["family"]
    events = fam.ledger.get_events_for_child(fam.child_id)
    now = fam.clock.now()
    first = canonical_digest(build_causal_twin(replay(events), now))
    second = canonical_digest(build_causal_twin(replay(list(events)), now))
    assert first == second
