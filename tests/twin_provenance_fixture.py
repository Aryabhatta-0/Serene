"""The synthetic Causal Twin provenance fixture the web surface is tested with (issue #75).

It is produced by running the real kernel, not written by hand. A synthetic
family's browse investigation acquires and independently verifies an external
web capture (`run_browse_investigation`). Then, through ordinary admission:

- the external capture and a parent report are structured into observations
  and a pattern, and a narrower hypothesis is proposed from them;
- the original "abrupt transitions" hypothesis is superseded by it, with a
  recorded reason;
- the narrower hypothesis is tested by an approved experiment, promoted to a
  tested hypothesis and then to a contextual learning (level 5);
- the "hunger" hypothesis is tested, contradicted and refuted by policy.

`tests/test_twin_provenance.py` checks that the checked-in JSON is exactly what
this produces. To regenerate it:

    uv run python -m tests.twin_provenance_fixture
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from serene.causal import CausalTwin, build_causal_twin
from serene.causal.provenance import TwinProvenanceView, build_twin_provenance
from serene.domain.canonical import canonical_json
from serene.domain.entities import Hypothesis, OutcomeResult
from serene.domain.events import EventType, HypothesisRefuted, HypothesisSuperseded
from serene.domain.values import EpistemicLevel
from serene.projections.state import KernelState
from serene.testing import SyntheticFamily
from serene.testing.synthetic import T0

from .test_evidence_path import run_browse_investigation
from .test_investigation import HUNGER, TRANSITION

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "app" / "web" / "fixtures" / "synthetic-twin-provenance.json"
NARROWER = "Pickups after the posted pickup window drive the distress"


def _hypothesis(fam: SyntheticFamily, statement: str) -> Hypothesis:
    state = fam.state()
    return next(
        r.entity
        for r in state.entities.values()
        if r.kind == "hyp" and r.entity.statement == statement
    )


def _test(fam: SyntheticFamily, hyp: Hypothesis, result: OutcomeResult, day: int) -> Any:
    experiment = fam.propose_experiment(hyp)
    fam.classify(experiment)
    approval_id = fam.request_approval(experiment)
    fam.grant(experiment, approval_id)
    fam.start(experiment, approval_id)
    text = "calm" if result is OutcomeResult.SUPPORTS else "tearful despite a snack"
    r1 = fam.observe(f"Pickup during the trial was {text}", day=day)
    r2 = fam.observe(f"Second trial pickup was {text} too", day=day + 1)
    outcome = fam.outcome(experiment, (r1, r2), result=result)
    fam.complete(experiment, (outcome,))
    return experiment, outcome


def build_family() -> tuple[KernelState, datetime, dict[str, tuple[str, str]]]:
    """The fixture family's final kernel state, the projection time and the edge labels."""
    rig, _inv = run_browse_investigation(seed="twin-provenance-fixture")
    fam: SyntheticFamily = rig.family
    state = fam.state()
    (external_id,) = (
        e
        for e, r in state.entities.items()
        if r.kind == "evd" and r.entity.source.kind.value == "BROWSER"
    )
    external = state.entities[external_id]
    for entity_id, record in state.entities.items():  # entities the rig's services introduced
        fam.introduced_by.setdefault(entity_id, record.introduced_by)
    transition = _hypothesis(fam, TRANSITION)
    hunger = _hypothesis(fam, HUNGER)

    # The external capture and a parent report become a narrower explanation.
    posted = fam.structure(
        (external.entity,),
        "The daycare posts a fixed afternoon pickup window",
        observed_at=T0 + timedelta(days=10),
    )
    late = fam.observe("Picked up after the window closed and it was tearful again", day=11)
    pattern = fam.pattern((posted, late), "Tearful pickups follow pickups after the posted window")
    inv2 = fam.open_investigation("Do pickups after the posted window make it worse?")
    narrower = fam.hypothesis(inv2, (pattern,), NARROWER)
    fam.append(
        fam.draft(
            EventType.HYPOTHESIS_SUPERSEDED,
            fam.policy,
            HypothesisSuperseded(
                hypothesis_id=transition.hypothesis_id,
                superseded_by=narrower.hypothesis_id,
                reason="Narrowed to pickups after the posted pickup window",
            ),
        )
    )

    # The narrower explanation is tested and becomes a contextual learning.
    experiment, outcome = _test(fam, narrower, OutcomeResult.SUPPORTS, day=14)
    fam.promote(narrower.hypothesis_id, EpistemicLevel.HYPOTHESIS, EpistemicLevel.TESTED_HYPOTHESIS)
    grant5 = fam.promote(
        narrower.hypothesis_id,
        EpistemicLevel.TESTED_HYPOTHESIS,
        EpistemicLevel.CONTEXTUAL_LEARNING,
    )
    fam.record_learning(fam.learning_candidate(narrower, (experiment,), (outcome,)), grant5)

    # The hunger explanation is tested, contradicted and refuted by policy.
    _exp, contradicting = _test(fam, hunger, OutcomeResult.CONTRADICTS, day=20)
    fam.append(
        fam.draft(
            EventType.HYPOTHESIS_REFUTED,
            fam.policy,
            HypothesisRefuted(
                hypothesis_id=hunger.hypothesis_id,
                outcome_ids=(contradicting.outcome_id,),
                reason_codes=("CONTRADICTING_OUTCOME",),
            ),
        )
    )

    labels = {
        transition.hypothesis_id: ("abrupt_transition", "pickup_distress"),
        hunger.hypothesis_id: ("hunger_after_daycare", "pickup_distress"),
        narrower.hypothesis_id: ("late_pickup", "pickup_distress"),
    }
    return fam.state(), fam.clock.now(), labels


def build_fixture() -> tuple[CausalTwin, TwinProvenanceView]:
    state, now, labels = build_family()
    twin = build_causal_twin(state, now, labels)
    return twin, build_twin_provenance(state, now, twin)


def fixture_json(twin: CausalTwin, provenance: TwinProvenanceView) -> str:
    payload = {
        "twin": twin.model_dump(mode="json"),
        "provenance": provenance.model_dump(mode="json"),
    }
    return json.dumps(json.loads(canonical_json(payload)), indent=2) + "\n"


if __name__ == "__main__":
    FIXTURE.write_text(fixture_json(*build_fixture()), encoding="utf-8", newline="\n")
