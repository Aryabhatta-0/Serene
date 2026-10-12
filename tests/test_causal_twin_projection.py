"""The `causal_twin` read projection: the web's privacy-safe Causal Twin.

It is the kernel twin and its complete provenance projection (#75) without
child, actor or source ids, published to `serene.projection_state` like every
other projection and readable by the child's parents only.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from serene.causal import RelationshipStatus, build_causal_twin
from serene.causal.provenance import build_twin_provenance
from serene.causal.web import WebCausalTwin, build_web_twin, node_id, private_identifiers
from serene.domain.canonical import canonical_json
from serene.domain.entities import OutcomeResult
from serene.domain.events import EventType, HypothesisRefuted
from serene.projections.state import KernelState
from serene.projections.views import project, rebuild_projections
from serene.testing import SyntheticFamily

from .investigation_support import CAREGIVER_TG, PARENT_TG
from .twin_provenance_fixture import (
    WEB_FIXTURE,
    build_family,
    build_web_fixture,
    web_fixture_json,
)

PRIVATE_ID = re.compile(r"\b(?:chd|act|src)_[0-9a-f]{32}\b")
PRIVATE_KEYS = {"child_id", "actor_id", "source_id", "user_id", "created_by", "uri", "content"}


@pytest.fixture(scope="module")
def family() -> tuple[KernelState, datetime, dict[str, tuple[str, str]]]:
    return build_family()


@pytest.fixture(scope="module")
def state(family: Any) -> KernelState:
    return family[0]


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


def _values(value: Any) -> set[Any]:
    if isinstance(value, dict):
        return {x for v in value.values() for x in _values(v)}
    if isinstance(value, list):
        return {x for v in value for x in _values(v)}
    return {value}


def _actor_ids(state: KernelState) -> set[str]:
    return {r.entity.provenance.created_by.actor_id for r in state.entities.values()}


def test_the_web_fixture_is_exactly_what_the_kernel_produces() -> None:
    assert WEB_FIXTURE.read_text(encoding="utf-8") == web_fixture_json(build_web_fixture())


def test_the_published_row_is_the_web_twin_as_of_the_head_event(state: KernelState) -> None:
    assert state.last_recorded_at is not None
    payload = project(state)["causal_twin"]
    assert payload == build_web_twin(state, state.last_recorded_at).model_dump(mode="json")
    assert WebCausalTwin.model_validate_json(json.dumps(payload)).edges
    # A pure function of the ledger state: rebuilding the family gives the same bytes.
    again, _, _ = build_family()
    assert canonical_json(project(again)["causal_twin"]) == canonical_json(payload)


def test_projection_contains_no_child_actor_or_source_identifier(state: KernelState) -> None:
    assert state.last_recorded_at is not None
    for payload in (
        project(state)["causal_twin"],
        json.loads(WEB_FIXTURE.read_text(encoding="utf-8")),
    ):
        text = json.dumps(payload)
        assert private_identifiers(payload) == []
        assert not PRIVATE_ID.findall(text)
        assert not _keys(payload) & PRIVATE_KEYS
        assert state.child_id is not None and state.child_id not in text
        for actor_id in _actor_ids(state):
            assert actor_id not in text
        assert not _values(payload) & {PARENT_TG, CAREGIVER_TG}  # Telegram user ids
        for record in state.entities.values():
            if record.kind == "evd" and record.entity.source.uri:
                assert record.entity.source.uri not in text
    # The canonical kernel twin it is built from does carry them: the projection removed them.
    internal = build_causal_twin(state, state.last_recorded_at).model_dump_json()
    assert state.child_id in internal and PRIVATE_ID.search(internal)


def test_the_builder_refuses_to_return_an_identifier() -> None:
    child = f"chd_{'1' * 32}"
    assert private_identifiers({"edges": [{"note": child}]}) == [child]
    assert private_identifiers({"origin": {"actor_id": "x"}}) == ["key:actor_id"]


def test_every_projected_edge_maps_to_its_complete_provenance(family: Any) -> None:
    state, now, labels = family
    view = build_web_twin(state, now, labels)
    twin = build_causal_twin(state, now, labels)
    complete = build_twin_provenance(state, now, twin)
    # The provenance part is the #75 projection, unchanged.
    assert view.provenance == complete
    assert [e.edge_id for e in view.edges] == [e.edge_id for e in twin.edges]
    nodes = {n.entity_id for n in view.provenance.nodes} | {
        m.entity_id for m in view.provenance.missing
    }
    detail = {e.edge_id: e for e in view.provenance.edges}
    for edge, kernel in zip(view.edges, twin.edges, strict=True):
        p = detail[edge.edge_id]
        assert (edge.status, edge.epistemic_level) == (kernel.status, kernel.epistemic_level)
        assert edge.raw_evidence == kernel.raw_evidence == p.lineage.raw_evidence
        assert edge.counterevidence == kernel.counterevidence
        assert edge.experiments == tuple(x.experiment_id for x in p.experiments)
        assert p.cited_ids() <= nodes  # every link the panel follows lands
        assert edge.origin.actor_kind is kernel.provenance.created_by.kind
        assert (edge.from_node, edge.to_node) == (node_id(kernel.cause), node_id(kernel.effect))  # type: ignore[arg-type]
    by_status = {e.status: detail[e.edge_id] for e in view.edges}
    refuted = by_status[RelationshipStatus.REFUTED]
    assert refuted.refutation is not None and refuted.refutation.outcome_ids
    assert any(c.contradicting_outcome for c in refuted.counterevidence)
    assert any(
        o.result is OutcomeResult.CONTRADICTS for x in refuted.experiments for o in x.outcomes
    )
    replaced = by_status[RelationshipStatus.SUPERSEDED]
    assert replaced.supersession.superseded_by and replaced.supersession.reason
    supported = by_status[RelationshipStatus.SUPPORTED]
    assert supported.learning is not None and supported.validity is not None
    assert {n.label for n in view.nodes} == {v for pair in labels.values() for v in pair}


def test_production_edges_are_unplaced_until_variables_are_named(state: KernelState) -> None:
    payload = project(state)["causal_twin"]
    assert payload["nodes"] == []
    assert all(e["from_node"] is None and e["to_node"] is None for e in payload["edges"])


def test_a_twin_that_disagrees_with_its_provenance_is_unrepresentable(family: Any) -> None:
    state, now, labels = family
    data = build_web_twin(state, now, labels).model_dump(mode="json")
    tampered = json.loads(json.dumps(data))
    edge = next(e for e in tampered["edges"] if e["status"] == "REFUTED")
    edge["status"] = "CANDIDATE"
    with pytest.raises(ValidationError, match="differs from its provenance"):
        WebCausalTwin.model_validate_json(json.dumps(tampered))
    dropped = json.loads(json.dumps(data))
    dropped["provenance"]["edges"] = dropped["provenance"]["edges"][1:]
    with pytest.raises(ValidationError):
        WebCausalTwin.model_validate_json(json.dumps(dropped))
    dangling = json.loads(json.dumps(data))
    dangling["edges"][0]["from_node"] = node_id("never_named")
    with pytest.raises(ValidationError, match="exactly the variables"):
        WebCausalTwin.model_validate_json(json.dumps(dangling))
    moved = json.loads(json.dumps(data))
    moved["provenance"]["ledger_head"] = "0" * 64
    with pytest.raises(ValidationError, match="another ledger position"):
        WebCausalTwin.model_validate_json(json.dumps(moved))


def test_the_row_is_empty_until_a_hypothesis_and_republishes_on_every_append() -> None:
    fam = SyntheticFamily(seed="causal-twin-projection")
    o1 = fam.observe("Synthetic: tearful pickup", day=0)
    assert fam.ledger.projections(fam.child_id)["causal_twin"] == {}
    o2 = fam.observe("Synthetic: tearful pickup again", day=1)
    pattern = fam.pattern((o1, o2), "Synthetic: pickups are tearful")
    inv = fam.open_investigation("Synthetic: why are pickups hard?")
    assert fam.ledger.projections(fam.child_id)["causal_twin"] == {}
    first = fam.hypothesis(inv, (pattern,), "Synthetic: abrupt transitions")
    one = fam.ledger.projections(fam.child_id)["causal_twin"]
    assert [e["edge_id"] for e in one["edges"]] == [first.hypothesis_id]
    assert one["edges"][0]["status"] == "CANDIDATE"
    second = fam.hypothesis(inv, (pattern,), "Synthetic: hunger after daycare")
    two = fam.ledger.projections(fam.child_id)["causal_twin"]
    assert {e["edge_id"] for e in two["edges"]} == {first.hypothesis_id, second.hypothesis_id}
    assert two["ledger_head"] != one["ledger_head"]

    # Tested, contradicted, refuted: each admitted step republishes the verdict.
    exp = fam.propose_experiment(second)
    fam.classify(exp)
    apr = fam.request_approval(exp)
    fam.grant(exp, apr)
    fam.start(exp, apr)
    r1 = fam.observe("Synthetic: tearful despite a snack", day=3)
    r2 = fam.observe("Synthetic: tearful despite a snack again", day=4)
    outcome = fam.outcome(exp, (r1, r2), result=OutcomeResult.CONTRADICTS)
    fam.complete(exp, (outcome,))
    fam.append(
        fam.draft(
            EventType.HYPOTHESIS_REFUTED,
            fam.policy,
            HypothesisRefuted(
                hypothesis_id=second.hypothesis_id,
                outcome_ids=(outcome.outcome_id,),
                reason_codes=("CONTRADICTING_OUTCOME",),
            ),
        )
    )
    after = fam.ledger.projections(fam.child_id)["causal_twin"]
    verdict = {e["edge_id"]: e["status"] for e in after["edges"]}
    assert verdict == {first.hypothesis_id: "CANDIDATE", second.hypothesis_id: "REFUTED"}
    refuted = next(e for e in after["provenance"]["edges"] if e["edge_id"] == second.hypothesis_id)
    assert refuted["refutation"]["outcome_ids"] == [outcome.outcome_id]
    assert private_identifiers(after) == []
    events = fam.ledger.get_events_for_child(fam.child_id)
    assert after == rebuild_projections(events)["causal_twin"]


@pytest.mark.postgres
def test_causal_twin_rls_parent_only_and_live_republish(pg_dsn: str) -> None:
    import psycopg

    from serene.adapters.postgres import PostgresEventStore, postgres_ledger

    def family(seed: str) -> SyntheticFamily:
        fam = SyntheticFamily(seed=seed, store=PostgresEventStore(pg_dsn))
        fam.ledger = postgres_ledger(pg_dsn, fam.clock)
        o1 = fam.observe("Synthetic: tearful pickup", day=0)
        o2 = fam.observe("Synthetic: tearful pickup again", day=1)
        inv = fam.open_investigation("Synthetic: why?")
        fam.hypothesis(inv, (fam.pattern((o1, o2), "Synthetic: tearful pickups"),), "Synthetic: A")
        return fam

    mine, theirs = family("twin-rls-mine"), family("twin-rls-theirs")
    parent, other_parent, caregiver = (uuid.UUID(int=i) for i in (11, 12, 13))
    with psycopg.connect(pg_dsn) as conn:
        for fam, guardian in ((mine, parent), (theirs, other_parent)):
            conn.execute(
                "insert into serene.children values (%s, 'SYNTHETIC', now())", (fam.child_id,)
            )
            conn.execute(
                "insert into serene.child_guardians (child_id, user_id, role) "
                "values (%s, %s, 'PARENT')",
                (fam.child_id, guardian),
            )
        # Every caregiver scope there is, on the parent's child.
        for scope in ("observations:read", "experiments:read", "learnings:read"):
            conn.execute(
                "insert into serene.caregiver_grants "
                "(child_id, caregiver_id, scope, granted_by, expires_at) "
                "values (%s, %s, %s, %s, now() + interval '1 day')",
                (mine.child_id, caregiver, scope, parent),
            )

    def read(user: uuid.UUID) -> list[tuple[str, str, Any, int]]:
        with psycopg.connect(pg_dsn) as conn:
            conn.execute("set local role authenticated")
            conn.execute("select set_config('request.jwt.claim.sub', %s, true)", (str(user),))
            return conn.execute(
                "select child_id, projection, state, last_sequence from serene.projection_state"
            ).fetchall()

    def twins(user: uuid.UUID) -> dict[str, Any]:
        return {c: s for c, p, s, _ in read(user) if p == "causal_twin"}

    assert set(twins(parent)) == {mine.child_id}
    assert set(twins(other_parent)) == {theirs.child_id}
    assert twins(caregiver) == {}
    assert {p for _c, p, _s, _n in read(caregiver)} == {"active_learnings"}
    published = twins(parent)[mine.child_id]
    assert WebCausalTwin.model_validate_json(json.dumps(published)).edges
    assert private_identifiers(published) == []

    # A live append through the production ledger republishes the parent's row.
    before = {c: n for c, p, _s, n in read(parent) if p == "causal_twin"}[mine.child_id]
    inv = mine.open_investigation("Synthetic: anything else?")
    o3 = mine.observe("Synthetic: calm pickup", day=2)
    o4 = mine.observe("Synthetic: calm pickup again", day=3)
    added = mine.hypothesis(
        inv, (mine.pattern((o3, o4), "Synthetic: calm pickups"),), "Synthetic: B"
    )
    rows = {c: (s, n) for c, p, s, n in read(parent) if p == "causal_twin"}
    state, sequence = rows[mine.child_id]
    assert sequence > before
    assert added.hypothesis_id in {e["edge_id"] for e in state["edges"]}
    assert state == project(mine.state())["causal_twin"]
    assert added.hypothesis_id not in json.dumps(twins(other_parent))
    assert twins(caregiver) == {}
    # End users cannot write projection state, and nobody reads the ledger through it.
    with psycopg.connect(pg_dsn) as conn:
        conn.execute("set local role authenticated")
        conn.execute("select set_config('request.jwt.claim.sub', %s, true)", (str(parent),))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "update serene.projection_state set state = '{}' where projection = 'causal_twin'"
            )
