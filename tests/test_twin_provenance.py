"""Causal Twin provenance projection for the web (issue #75).

The fixture is kernel output (tests/twin_provenance_fixture.py): a refuted, a
superseded and a level-5 edge, with external web evidence on the chain.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from serene.causal import CausalTwin, RelationshipStatus, build_causal_twin
from serene.causal.provenance import (
    EvidenceOrigin,
    NodeKind,
    TwinProvenanceView,
    build_twin_provenance,
)
from serene.domain.entities import LearningStatus, OutcomeResult
from serene.domain.values import EpistemicLevel, SourceKind
from serene.lineage.provenance import trace_lineage
from serene.projections.state import KernelState, LifecycleStatus
from serene.testing import build_full_ladder

from .investigation_support import CAREGIVER_TG, PARENT_TG
from .twin_provenance_fixture import FIXTURE, NARROWER, build_family, fixture_json

FAMILY_ID = re.compile(r"\b(?:chd|act|src)_[0-9a-f]{32}\b")


@pytest.fixture(scope="module")
def family() -> tuple[KernelState, datetime, dict[str, tuple[str, str]]]:
    return build_family()


@pytest.fixture(scope="module")
def state(family: Any) -> KernelState:
    return family[0]


@pytest.fixture(scope="module")
def now(family: Any) -> datetime:
    return family[1]


@pytest.fixture(scope="module")
def built(family: Any) -> tuple[CausalTwin, TwinProvenanceView]:
    state, now, labels = family
    twin = build_causal_twin(state, now, labels)
    return twin, build_twin_provenance(state, now, twin)


@pytest.fixture(scope="module")
def view(built: Any) -> TwinProvenanceView:
    return built[1]


def _edge(view: TwinProvenanceView, status: RelationshipStatus) -> Any:
    (edge,) = (e for e in view.edges if e.status is status)
    return edge


def test_the_web_fixture_is_exactly_what_the_kernel_produces(built: Any) -> None:
    assert FIXTURE.read_text(encoding="utf-8") == fixture_json(*built), (
        "regenerate with: uv run python -m tests.twin_provenance_fixture"
    )


def test_projection_round_trips_through_json(view: TwinProvenanceView) -> None:
    assert TwinProvenanceView.model_validate_json(view.model_dump_json()) == view
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))["provenance"]
    assert TwinProvenanceView.model_validate_json(json.dumps(payload)) == view


def test_fixture_covers_every_edge_state(view: TwinProvenanceView) -> None:
    assert {e.status for e in view.edges} == {
        RelationshipStatus.SUPPORTED,
        RelationshipStatus.SUPERSEDED,
        RelationshipStatus.REFUTED,
    }


def test_every_edge_resolves_to_raw_evidence_or_reports_its_gaps(
    view: TwinProvenanceView,
) -> None:
    nodes = {n.entity_id: n for n in view.nodes}
    for edge in view.edges:
        assert edge.lineage.complete and not edge.lineage.missing
        assert edge.lineage.raw_evidence
        for evd in edge.lineage.raw_evidence:
            assert nodes[evd].kind is NodeKind.EVIDENCE
        for cited in edge.cited_ids():
            node = nodes[cited]
            assert node.raw_evidence or node.missing, cited
            assert set(node.raw_evidence) <= set(nodes)
    assert view.missing == ()


def test_every_trace_lineage_node_is_present_with_parents_and_status(
    view: TwinProvenanceView, state: KernelState
) -> None:
    nodes = {n.entity_id: n for n in view.nodes}
    for edge in view.edges:
        trace = trace_lineage(edge.edge_id, state)
        assert {s.entity_id for s in edge.lineage.steps} == {n.entity_id for n in trace.nodes}
        assert edge.lineage.raw_evidence == trace.raw_evidence
        for traced in trace.nodes:
            node = nodes[traced.entity_id]
            assert node.parents == traced.parents
            assert node.verification_status is traced.verification_status
            assert node.epistemic_level == traced.level
        depths = [s.depth for s in edge.lineage.steps]
        assert depths == sorted(depths) and depths[0] == 0
        assert edge.lineage.steps[0].entity_id == edge.edge_id
        # Intermediate rungs, not just the endpoints.
        kinds = {nodes[s.entity_id].kind for s in edge.lineage.steps}
        assert {NodeKind.PATTERN, NodeKind.OBSERVATION, NodeKind.EVIDENCE} <= kinds


def test_external_evidence_is_identifiable(view: TwinProvenanceView) -> None:
    nodes = {n.entity_id: n for n in view.nodes}
    external = [n for n in view.nodes if n.evidence is not None and n.evidence.external]
    assert len(external) == 1
    (capture,) = external
    assert capture.evidence is not None
    assert capture.evidence.source_kind is SourceKind.BROWSER
    assert capture.evidence.evidence_kind.value == "BROWSER_CAPTURE"
    assert capture.evidence.source_host == "example.org"
    assert capture.evidence.checks_passed  # independently verified
    assert capture.evidence_origin is EvidenceOrigin.EXTERNAL
    narrower = _edge(view, RelationshipStatus.SUPPORTED)
    assert narrower.relationship == NARROWER
    origins = {nodes[s.entity_id].evidence_origin for s in narrower.support}
    assert {EvidenceOrigin.EXTERNAL, EvidenceOrigin.FAMILY} <= origins
    family = [n for n in view.nodes if n.evidence is not None and not n.evidence.external]
    assert family and all(n.evidence and n.evidence.source_host is None for n in family)


def test_outcome_to_experiment_links_and_statuses(
    view: TwinProvenanceView, state: KernelState
) -> None:
    seen = 0
    for edge in view.edges:
        for exp in edge.experiments:
            record = state.experiments[exp.experiment_id]
            assert record.experiment.hypothesis_id == edge.edge_id
            assert exp.status is record.status
            assert [o.outcome_id for o in exp.outcomes] == record.outcome_ids
            for outcome in exp.outcomes:
                entity = state.entities[outcome.outcome_id].entity
                assert outcome.experiment_id == entity.experiment_id == exp.experiment_id
                assert outcome.result is entity.result
                seen += 1
    assert seen == 2
    refuted = _edge(view, RelationshipStatus.REFUTED)
    (outcome,) = refuted.experiments[0].outcomes
    assert outcome.result is OutcomeResult.CONTRADICTS


def test_node_statuses_match_the_ledger(view: TwinProvenanceView, state: KernelState) -> None:
    for node in view.nodes:
        record = state.entities[node.entity_id]
        assert node.verification_status is record.verification_status
        assert node.lifecycle is record.status
        assert node.superseded_by == record.superseded_by
        assert node.epistemic_level == record.level


def test_superseded_and_refuted_edges_keep_their_reasons(view: TwinProvenanceView) -> None:
    supported = _edge(view, RelationshipStatus.SUPPORTED)
    superseded = _edge(view, RelationshipStatus.SUPERSEDED)
    assert superseded.lifecycle is LifecycleStatus.SUPERSEDED
    assert superseded.supersession.superseded_by == supported.edge_id
    assert superseded.supersession.reason == "Narrowed to pickups after the posted pickup window"
    refuted = _edge(view, RelationshipStatus.REFUTED)
    assert refuted.refutation is not None
    assert refuted.refutation.reason_codes == ("CONTRADICTING_OUTCOME",)
    assert refuted.refutation.outcome_ids == (refuted.experiments[0].outcomes[0].outcome_id,)
    assert {c.entity_id for c in refuted.counterevidence if c.contradicting_outcome} == set(
        refuted.refutation.outcome_ids
    )
    assert supported.refutation is None and supported.supersession.superseded_by is None


def test_level_five_edge_carries_scope_validity_and_review(
    view: TwinProvenanceView, state: KernelState
) -> None:
    edge = _edge(view, RelationshipStatus.SUPPORTED)
    assert edge.epistemic_level is EpistemicLevel.CONTEXTUAL_LEARNING
    learning = edge.learning
    assert learning is not None and edge.validity is not None
    record = state.learnings[learning.learning_id]
    assert learning.scope_contexts == edge.scope_contexts
    assert (learning.valid_from, learning.review_after) == (record.valid_from, record.review_after)
    assert (edge.validity.valid_from, edge.validity.review_after) == (
        record.valid_from,
        record.review_after,
    )
    assert learning.effective_status is LearningStatus.ACTIVE and not learning.review_due
    assert learning.retest_triggers and learning.reviewer_kind.value == "PARENT"
    assert learning.experiment_ids == tuple(e.experiment_id for e in edge.experiments)
    assert learning.confounders == edge.confounders
    for other in view.edges:
        if other is not edge:
            assert other.learning is None


def test_review_due_is_shown_once_the_review_date_passes() -> None:
    ladder = build_full_ladder(seed="twin-provenance-review")
    fam = ladder["family"]
    later = fam.clock.now() + timedelta(days=75)
    (edge,) = build_twin_provenance(fam.state(), later).edges
    assert edge.learning is not None and edge.learning.review_due
    assert edge.learning.effective_status is not LearningStatus.ACTIVE
    assert edge.learning.recorded_status is LearningStatus.ACTIVE


FORBIDDEN_KEYS = frozenset(
    {
        "actor_id",
        "child_id",
        "source_id",
        "observer",
        "reported_by",
        "created_by",
        "reviewer",
        "telegram_user_id",
        "chat_id",
        "user_id",
        "auth_user_id",
        "access_token",
        "refresh_token",
        "uri",
        "content",
    }
)


def _walk(value: Any) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            yield ("key", key)
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)
    else:
        yield ("value", value)


def test_projection_carries_no_family_identifiers_or_raw_content(
    view: TwinProvenanceView, state: KernelState
) -> None:
    for payload in (
        view.model_dump(mode="json"),
        json.loads(FIXTURE.read_text(encoding="utf-8"))["provenance"],
    ):
        text = json.dumps(payload)
        assert not FAMILY_ID.findall(text)
        assert state.child_id is not None and state.child_id not in text
        items = list(_walk(payload))
        assert not {k for kind, k in items if kind == "key"} & FORBIDDEN_KEYS
        values = [v for kind, v in items if kind == "value"]
        assert PARENT_TG not in values and CAREGIVER_TG not in values  # Telegram user ids
        for record in state.entities.values():
            if record.kind == "evd" and record.entity.source.uri:
                assert record.entity.source.uri not in text  # only the public host
    # A raw-evidence node is named by kind and channel, never by its content. (The
    # synthetic family's observations restate their report, so the statement of a
    # derived observation may match; the evidence node itself never does.)
    derived = {n.summary for n in view.nodes if n.kind is not NodeKind.EVIDENCE}
    for node in view.nodes:
        if node.kind is NodeKind.EVIDENCE:
            content = state.entities[node.entity_id].entity.content
            assert content not in node.summary
            assert content not in view.model_dump_json() or content[:200] in derived


def test_a_missing_cited_node_is_reported_not_dropped(
    built: Any, state: KernelState, now: datetime
) -> None:
    twin, _ = built
    edge = next(e for e in twin.edges if e.status is RelationshipStatus.SUPPORTED)
    gap = next(s.entity_id for s in edge.support if s.entity_id.startswith("obs_"))
    broken = state.clone()
    del broken.entities[gap]
    projected = build_twin_provenance(broken, now, twin)
    (missing,) = (m for m in projected.missing if m.entity_id == gap)
    assert edge.edge_id in missing.referenced_by
    assert gap not in {n.entity_id for n in projected.nodes}
    affected = next(e for e in projected.edges if e.edge_id == edge.edge_id)
    assert not affected.lineage.complete
    assert gap in {m.entity_id for m in affected.lineage.missing}
    assert TwinProvenanceView.model_validate_json(projected.model_dump_json()) == projected


def test_a_missing_intermediate_node_breaks_completeness(
    built: Any, state: KernelState, now: datetime
) -> None:
    twin, _ = built
    edge = next(e for e in twin.edges if e.status is RelationshipStatus.REFUTED)
    broken = state.clone()
    pattern = broken.entities[edge.edge_id].entity.pattern_ids[0]
    del broken.entities[pattern]
    projected = build_twin_provenance(broken, now, twin)
    lineage = next(e for e in projected.edges if e.edge_id == edge.edge_id).lineage
    assert not lineage.complete
    assert [m.entity_id for m in lineage.missing] == [pattern]
    assert lineage.missing[0].referenced_by == (edge.edge_id,)
    assert pattern in {m.entity_id for m in projected.missing}


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda e: e.update(refutation=None), "refut"),
        (lambda e: e.update(learning=None), "level-5"),
        (lambda e: e["supersession"].update(reason=None), "supersession reason"),
    ],
)
def test_illegal_edge_states_are_unrepresentable(
    view: TwinProvenanceView, mutate: Any, match: str
) -> None:
    payload = view.model_dump(mode="json")
    target = {
        "refut": RelationshipStatus.REFUTED,
        "level-5": RelationshipStatus.SUPPORTED,
        "supersession reason": RelationshipStatus.SUPERSEDED,
    }[match]
    edge = next(e for e in payload["edges"] if e["status"] == target.value)
    mutate(edge)
    with pytest.raises(ValidationError, match=match):
        TwinProvenanceView.model_validate_json(json.dumps(payload))


def test_an_outcome_cannot_be_listed_under_another_experiment(view: TwinProvenanceView) -> None:
    payload = view.model_dump(mode="json")
    exps = [x for e in payload["edges"] for x in e["experiments"]]
    exps[0]["outcomes"].append({**exps[1]["outcomes"][0]})
    with pytest.raises(ValidationError, match="its own outcomes"):
        TwinProvenanceView.model_validate_json(json.dumps(payload))


def test_every_provenance_link_must_resolve(view: TwinProvenanceView) -> None:
    payload = view.model_dump(mode="json")
    dropped = payload["edges"][0]["lineage"]["steps"][1]["entity_id"]
    payload["nodes"] = [n for n in payload["nodes"] if n["entity_id"] != dropped]
    with pytest.raises(ValidationError, match="unresolved provenance ids"):
        TwinProvenanceView.model_validate_json(json.dumps(payload))


def test_projection_is_a_deterministic_function_of_the_ledger(built: Any) -> None:
    state, now, labels = build_family()
    twin = build_causal_twin(state, now, labels)
    assert fixture_json(twin, build_twin_provenance(state, now, twin)) == fixture_json(*built)
