"""Level 5 cannot silently drop relevant verified human evidence (core scenario 4, #44).

The model builds the Pattern and so chooses which observations it cites. At the
Level-5 gate, deterministic code finds every verified parent/caregiver observation
in a supporting pattern's scope (same child, overlapping context, inside the
pattern's observation span) and denies promotion unless each one is accounted
for as a member or a counter-observation of a supporting pattern. Whether the
omitted report agrees or disagrees is never judged.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from serene.domain.entities import Evidence, Observation, OutcomeResult, Pattern
from serene.domain.events import EventType, ObservationStructured, PatternProposed
from serene.domain.values import ActorRef, DerivationMethod, EpistemicLevel, VerificationStatus
from serene.ledger import AdmissionRejected
from serene.policies.promotion import (
    PromotionRequest,
    evaluate_promotion,
    unaccounted_observations,
)
from serene.ports.event_store import EventStore
from serene.testing import SyntheticFamily, build_full_ladder
from serene.testing.synthetic import DEFAULT_CONTEXTS, T0

L = EpistemicLevel
UNACCOUNTED = "UNACCOUNTED_RELEVANT_OBSERVATION"


# ------------------------------------------------------------------ helpers
def _structured(
    fam: SyntheticFamily,
    evidence: Evidence,
    statement: str,
    *,
    day: int,
    contexts: tuple[str, ...] = DEFAULT_CONTEXTS,
    observer: ActorRef | None = None,
) -> Observation:
    parents = (evidence.evidence_id,)
    observation = Observation(
        child_id=fam.child_id,
        provenance=fam._agent_provenance(parents, DerivationMethod.MODEL_EXTRACTION),
        observation_id=fam.new_id("obs"),
        evidence_ids=parents,
        observer=observer or evidence.observer,
        observed_at=T0 + timedelta(days=day),
        statement=statement,
        contexts=contexts,
    )
    event = fam.append(
        fam.draft(
            EventType.OBSERVATION_STRUCTURED,
            fam.agent,
            ObservationStructured(observation=observation),
            status=VerificationStatus.UNVERIFIED,
            derived_from=fam._events_for(parents),
        )
    )
    fam.introduced_by[observation.observation_id] = event.event_id
    return observation


def _pattern(
    fam: SyntheticFamily, members: tuple[Observation, ...], counters: tuple[Observation, ...]
) -> Pattern:
    parents = tuple(o.observation_id for o in members)
    pattern = Pattern(
        child_id=fam.child_id,
        provenance=fam._agent_provenance(parents),
        pattern_id=fam.new_id("pat"),
        observation_ids=parents,
        counter_observation_ids=tuple(o.observation_id for o in counters),
        description="Pickups are tearful",
        contexts=DEFAULT_CONTEXTS,
    )
    event = fam.append(
        fam.draft(
            EventType.PATTERN_PROPOSED,
            fam.agent,
            PatternProposed(pattern=pattern),
            status=VerificationStatus.UNVERIFIED,
            derived_from=fam._events_for(parents),
        )
    )
    fam.introduced_by[pattern.pattern_id] = event.event_id
    return pattern


def _daycare(fam: SyntheticFamily, days: range = range(2)) -> tuple[Observation, ...]:
    return tuple(
        _structured(
            fam,
            fam.report(f"Tearful at pickup, day {d + 1}", observer=fam.caregiver),
            f"Tearful at pickup, day {d + 1}",
            day=d,
        )
        for d in days
    )


def _parent(
    fam: SyntheticFamily,
    *,
    day: int = 0,
    contexts: tuple[str, ...] = DEFAULT_CONTEXTS,
    observer: ActorRef | None = None,
) -> Observation:
    statement = f"Calm and happy at pickup, day {day + 1}"
    return _structured(
        fam, fam.report(statement), statement, day=day, contexts=contexts, observer=observer
    )


def _tested(
    fam: SyntheticFamily, members: tuple[Observation, ...], counters: tuple[Observation, ...] = ()
) -> Any:
    """Pattern -> hypothesis -> supporting experiment -> TESTED_HYPOTHESIS."""
    pattern = _pattern(fam, members, counters)
    inv = fam.open_investigation("Why are daycare pickups hard?")
    hyp = fam.hypothesis(inv, (pattern,), "Abrupt transitions at pickup drive the distress")
    exp = fam.propose_experiment(hyp)
    fam.classify(exp)
    apr = fam.request_approval(exp)
    fam.grant(exp, apr)
    fam.start(exp, apr)
    r1 = fam.observe("Heads-up given before pickup, day 1", day=8)
    r2 = fam.observe("Heads-up given before pickup, day 2", day=9)
    fam.complete(exp, (fam.outcome(exp, (r1, r2), OutcomeResult.SUPPORTS),))
    fam.promote(hyp.hypothesis_id, L.HYPOTHESIS, L.TESTED_HYPOTHESIS)
    return hyp


def _to_learning(fam: SyntheticFamily, hyp: Any) -> tuple[str, ...]:
    return evaluate_promotion(
        PromotionRequest(
            subject_id=hyp.hypothesis_id,
            from_level=L.TESTED_HYPOTHESIS,
            to_level=L.CONTEXTUAL_LEARNING,
            requested_by=fam.agent,
            rationale="the model asserts the cause is established",
        ),
        fam.state(),
    ).reason_codes


# ------------------------------------------------------------------ omitted -> denied
def test_omitted_conflicting_caregiver_reports_deny_level_5() -> None:
    fam = SyntheticFamily(seed="unaccounted-omitted")
    daycare = _daycare(fam)
    parent = (_parent(fam, day=0), _parent(fam, day=1))
    hyp = _tested(fam, daycare)

    reasons = _to_learning(fam, hyp)
    assert sorted(r for r in reasons if r.startswith(UNACCOUNTED)) == sorted(
        f"{UNACCOUNTED}:{o.observation_id}" for o in parent
    )
    with pytest.raises(AdmissionRejected) as info:
        fam.promote(hyp.hypothesis_id, L.TESTED_HYPOTHESIS, L.CONTEXTUAL_LEARNING)
    assert UNACCOUNTED in {r.split(":", 1)[0] for r in info.value.reason_codes}
    assert fam.state().hypothesis_levels[hyp.hypothesis_id] == L.TESTED_HYPOTHESIS


def test_the_rule_is_level_5_only() -> None:
    """Rung 4 still records that the experiment supported the hypothesis."""
    fam = SyntheticFamily(seed="unaccounted-rung-4")
    daycare = _daycare(fam)
    _parent(fam, day=0)
    hyp = _tested(fam, daycare)
    assert fam.state().hypothesis_levels[hyp.hypothesis_id] == L.TESTED_HYPOTHESIS


def test_a_single_omitted_report_is_enough_to_deny() -> None:
    fam = SyntheticFamily(seed="unaccounted-single")
    daycare = _daycare(fam)
    first = _parent(fam, day=0)
    second = _parent(fam, day=1)
    hyp = _tested(fam, (*daycare, first))
    assert unaccounted_observations(hyp.hypothesis_id, fam.state()) == (second.observation_id,)


def test_a_mislabelled_observer_cannot_hide_a_parent_report() -> None:
    """The model writes the Observation.observer field; the raw report's kind still counts."""
    fam = SyntheticFamily(seed="unaccounted-observer")
    daycare = _daycare(fam)
    hidden = _parent(fam, day=0, observer=fam.agent)
    hyp = _tested(fam, daycare)
    assert f"{UNACCOUNTED}:{hidden.observation_id}" in _to_learning(fam, hyp)


def test_a_report_arriving_after_the_grant_still_blocks_the_learning() -> None:
    """check_learning re-runs the rule against the ledger at recording time."""
    fam = SyntheticFamily(seed="unaccounted-late")
    daycare = _daycare(fam)
    hyp = _tested(fam, daycare)
    grant5 = fam.promote(hyp.hypothesis_id, L.TESTED_HYPOTHESIS, L.CONTEXTUAL_LEARNING)
    late = _parent(fam, day=1)
    state = fam.state()
    (record,) = (
        r for r in state.experiments.values() if r.experiment.hypothesis_id == hyp.hypothesis_id
    )
    learning = fam.learning_candidate(
        hyp,
        (record.experiment,),
        tuple(state.entities[o].entity for o in record.outcome_ids),
    )
    with pytest.raises(AdmissionRejected) as info:
        fam.record_learning(learning, grant5)
    assert f"{UNACCOUNTED}:{late.observation_id}" in info.value.reason_codes
    assert not fam.state().learnings


# ------------------------------------------------------------------ accounted -> normal gate
def test_reports_cited_as_counter_observations_let_the_normal_gate_continue() -> None:
    fam = SyntheticFamily(seed="unaccounted-countered")
    daycare = _daycare(fam)
    parent = (_parent(fam, day=0), _parent(fam, day=1))
    hyp = _tested(fam, daycare, counters=parent)

    assert unaccounted_observations(hyp.hypothesis_id, fam.state()) == ()
    assert _to_learning(fam, hyp) == ("ALLOWED",)
    fam.promote(hyp.hypothesis_id, L.TESTED_HYPOTHESIS, L.CONTEXTUAL_LEARNING)
    assert fam.state().hypothesis_levels[hyp.hypothesis_id] == L.CONTEXTUAL_LEARNING


def test_reports_cited_as_members_are_accounted_for() -> None:
    fam = SyntheticFamily(seed="unaccounted-members")
    daycare = _daycare(fam)
    parent = (_parent(fam, day=0), _parent(fam, day=1))
    hyp = _tested(fam, (*daycare, *parent))
    assert unaccounted_observations(hyp.hypothesis_id, fam.state()) == ()


def test_valid_full_ladder_is_unaffected() -> None:
    ladder = build_full_ladder(seed="unaccounted-valid")
    fam = ladder["family"]
    assert unaccounted_observations(ladder["hypothesis"].hypothesis_id, fam.state()) == ()
    assert len(fam.state().learnings) == 1


# ------------------------------------------------------------------ out of scope -> irrelevant
def test_another_childs_reports_are_irrelevant() -> None:
    store: EventStore = SyntheticFamily(seed="unaccounted-shared").store
    fam = SyntheticFamily(seed="unaccounted-child-a", store=store)
    sibling = SyntheticFamily(seed="unaccounted-child-b", store=store)
    daycare = _daycare(fam)
    _parent(sibling, day=0)
    _parent(sibling, day=1)
    hyp = _tested(fam, daycare)
    assert _to_learning(fam, hyp) == ("ALLOWED",)


def test_a_foreign_child_observation_in_state_is_ignored() -> None:
    """Defence in depth: the child filter holds even if a foreign record reached the state."""
    fam = SyntheticFamily(seed="unaccounted-foreign")
    daycare = _daycare(fam)
    parent = _parent(fam, day=0)
    hyp = _tested(fam, daycare)
    state = fam.state()
    record = state.entities[parent.observation_id]
    record.entity = record.entity.model_copy(update={"child_id": fam.new_id("chd")})
    assert unaccounted_observations(hyp.hypothesis_id, state) == ()


def test_a_report_about_an_unrelated_context_does_not_block() -> None:
    fam = SyntheticFamily(seed="unaccounted-context")
    daycare = _daycare(fam)
    _parent(fam, day=0, contexts=("bedtime",))
    hyp = _tested(fam, daycare)
    assert _to_learning(fam, hyp) == ("ALLOWED",)


def test_a_report_outside_the_pattern_time_span_does_not_block() -> None:
    fam = SyntheticFamily(seed="unaccounted-time")
    daycare = _daycare(fam)
    _parent(fam, day=5)
    hyp = _tested(fam, daycare)
    assert _to_learning(fam, hyp) == ("ALLOWED",)


def test_a_report_with_no_declared_context_is_in_scope() -> None:
    """Fail closed: missing context metadata cannot make a same-day report disappear."""
    fam = SyntheticFamily(seed="unaccounted-no-context")
    daycare = _daycare(fam)
    bare = _parent(fam, day=1, contexts=())
    hyp = _tested(fam, daycare)
    assert unaccounted_observations(hyp.hypothesis_id, fam.state()) == (bare.observation_id,)


def test_the_rule_is_deterministic() -> None:
    def run() -> tuple[str, ...]:
        fam = SyntheticFamily(seed="unaccounted-determinism")
        daycare = _daycare(fam)
        _parent(fam, day=0)
        return _to_learning(fam, _tested(fam, daycare))

    assert len({run() for _ in range(3)}) == 1
