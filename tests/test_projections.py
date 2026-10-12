"""Projections are disposable read state rebuilt by deterministic replay (issue #6)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from serene.domain.canonical import canonical_json
from serene.projections import (
    PROJECTIONS,
    apply_event,
    effective_learning_status,
    project,
    projection_digest,
    rebuild_projections,
)
from serene.projections.state import KernelState
from serene.testing import SyntheticFamily


def _events(fam: SyntheticFamily) -> list[Any]:
    return list(fam.ledger.get_events_for_child(fam.child_id))


def test_the_initial_projections_and_the_investigation_view_exist() -> None:
    assert set(PROJECTIONS) == {
        "current_child_state",
        "active_investigations",
        "active_hypotheses",
        "pending_approvals",
        "active_learnings",
        "investigations",  # issue #35
        "experiments",  # issues #37/#84
        "causal_twin",  # the Causal Twin surface (#75)
    }


def test_replay_twice_is_byte_identical(ladder: dict[str, Any]) -> None:
    events = _events(ladder["family"])
    assert canonical_json(rebuild_projections(events)) == canonical_json(
        rebuild_projections(events)
    )


def test_delete_and_rebuild_converges(ladder: dict[str, Any]) -> None:
    fam = ladder["family"]
    live = fam.ledger.projections(fam.child_id)
    del live  # "delete" the read model entirely
    rebuilt = rebuild_projections(_events(fam))
    assert projection_digest(rebuilt) == projection_digest(fam.ledger.projections(fam.child_id))


def test_incremental_equals_full_replay(ladder: dict[str, Any]) -> None:
    events = _events(ladder["family"])
    state = KernelState()
    for event in events:
        apply_event(state, event)
    assert project(state) == rebuild_projections(events)


def test_a_new_event_changes_exactly_the_expected_projection(family: SyntheticFamily) -> None:
    family.observe("Fussy at pickup", day=0)
    before = family.ledger.projections(family.child_id)
    family.open_investigation("Why is pickup hard?")
    after = family.ledger.projections(family.child_id)
    changed = {name for name in PROJECTIONS if before[name] != after[name]}
    assert changed == {"active_investigations", "current_child_state", "investigations"}


def test_the_experiments_projection_is_the_view_as_of_the_head_event(
    family: SyntheticFamily,
) -> None:
    from serene.experiments.view import build_experiments_view

    o1 = family.observe("tearful pickup", day=0)
    assert family.ledger.projections(family.child_id)["experiments"] == {}  # nothing proposed
    o2 = family.observe("tearful pickup again", day=1)
    pattern = family.pattern((o1, o2), "pickups are tearful")
    inv = family.open_investigation("why?")
    exp = family.propose_experiment(family.hypothesis(inv, (pattern,), "abrupt transitions"))
    family.classify(exp)
    family.request_approval(exp)
    state = family.state()
    head = family.ledger.get_events_for_child(family.child_id)[-1]
    assert state.last_recorded_at == head.recorded_at
    projected = family.ledger.projections(family.child_id)["experiments"]
    expected = build_experiments_view(state, head.recorded_at).model_dump(mode="json")
    assert projected == expected
    assert [e["phase"] for e in projected["experiments"]] == ["AWAITING_APPROVAL"]
    assert projected["experiments"][0]["approval"]["decision_open"] is True


def test_pending_approvals_track_the_lifecycle(family: SyntheticFamily) -> None:
    o1 = family.observe("tearful pickup", day=0)
    o2 = family.observe("tearful pickup again", day=1)
    pattern = family.pattern((o1, o2), "pickups are tearful")
    inv = family.open_investigation("why?")
    hyp = family.hypothesis(inv, (pattern,), "abrupt transitions")
    exp = family.propose_experiment(hyp)
    family.classify(exp)
    apr = family.request_approval(exp)
    assert apr in family.ledger.projections(family.child_id)["pending_approvals"]
    family.grant(exp, apr)
    assert family.ledger.projections(family.child_id)["pending_approvals"] == {}


def test_stale_learning_is_never_presented_as_active(ladder: dict[str, Any]) -> None:
    fam = ladder["family"]
    record = fam.state().learnings[ladder["learning"].learning_id]
    assert effective_learning_status(record, fam.clock.now()).value == "ACTIVE"
    later = record.review_after + timedelta(seconds=1)
    assert effective_learning_status(record, later).value == "NEEDS_REVIEW"


def test_projections_do_not_copy_raw_report_text(ladder: dict[str, Any]) -> None:
    projections = ladder["family"].ledger.projections(ladder["family"].child_id)
    blob = canonical_json({k: v for k, v in projections.items() if k != "causal_twin"})
    assert b"crying" not in blob and b"meltdown" not in blob
    # The Causal Twin shows each observation's derived statement (#75,
    # docs/privacy.md). The synthetic family's observations restate their
    # report word for word, so report text may appear there, and only there:
    # never on a raw-evidence node, which is named by its kind and channel.
    twin = projections["causal_twin"]
    for node in twin["provenance"]["nodes"]:
        text = canonical_json(node)
        if node["kind"] == "OBSERVATION":
            text = canonical_json({k: v for k, v in node.items() if k != "summary"})
        assert b"crying" not in text and b"meltdown" not in text
    rest = {k: v for k, v in twin.items() if k != "provenance"} | {
        "provenance": {k: v for k, v in twin["provenance"].items() if k != "nodes"}
    }
    assert b"crying" not in canonical_json(rest) and b"meltdown" not in canonical_json(rest)
