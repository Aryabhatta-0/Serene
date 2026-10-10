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


def test_the_five_initial_projections_exist() -> None:
    assert set(PROJECTIONS) == {
        "current_child_state",
        "active_investigations",
        "active_hypotheses",
        "pending_approvals",
        "active_learnings",
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
    assert changed == {"active_investigations", "current_child_state"}


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
    blob = canonical_json(ladder["family"].ledger.projections(ladder["family"].child_id))
    assert b"crying" not in blob and b"meltdown" not in blob
