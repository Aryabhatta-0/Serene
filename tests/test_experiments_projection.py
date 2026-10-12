"""Published experiment contract, deterministic replay, and parent-only RLS."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

import pytest

from serene.domain.canonical import canonical_json
from serene.experiments.view import ExperimentsView, build_experiments_view
from serene.projections.views import project, rebuild_projections
from serene.testing import SyntheticFamily

from .experiments_view_fixture import build_fixture
from .trust_helpers import awaiting_approval


def test_published_view_reuses_the_complete_privacy_filtered_contract() -> None:
    built = build_fixture()
    state = built.fam.state()
    payload = project(state)["experiments"]
    assert state.last_recorded_at is not None
    assert payload == build_experiments_view(state, state.last_recorded_at).model_dump(mode="json")
    assert ExperimentsView.model_validate_json(json.dumps(payload)).experiments
    text = json.dumps(payload)
    for private in ("chd_", "act_", "requested_of", "observer", "source_id", "evidence_ids"):
        assert private not in text
    assert canonical_json(project(state)) == canonical_json(
        rebuild_projections(built.fam.ledger.get_events_for_child(built.fam.child_id))
    )


def test_projection_time_advances_only_with_admitted_events() -> None:
    fam = SyntheticFamily(seed="projection-expiry")
    exp, _apr = awaiting_approval(fam)
    before = project(fam.state())["experiments"]
    assert before["experiments"][0]["approval"]["decision_open"]
    fam.clock.advance(timedelta(hours=49))
    assert project(fam.state())["experiments"] == before
    fam.observe("Synthetic: later routine observation", day=3)
    after = project(fam.state())["experiments"]
    assert after["experiments"][0]["experiment_id"] == exp.experiment_id
    assert not after["experiments"][0]["approval"]["decision_open"]
    assert after["as_of"] != before["as_of"]


@pytest.mark.postgres
def test_experiments_projection_is_parent_only_even_with_caregiver_experiment_scope(
    pg_dsn: str,
) -> None:
    import psycopg

    from serene.adapters.postgres import PostgresEventStore, postgres_ledger

    fam = SyntheticFamily(seed="projection-rls", store=PostgresEventStore(pg_dsn))
    fam.ledger = postgres_ledger(pg_dsn, fam.clock)
    awaiting_approval(fam)
    parent, other, caregiver = (uuid.UUID(int=i) for i in (1, 2, 3))
    with psycopg.connect(pg_dsn) as conn:
        conn.execute("insert into serene.children values (%s, 'SYNTHETIC', now())", (fam.child_id,))
        conn.execute(
            "insert into serene.child_guardians (child_id, user_id, role) "
            "values (%s, %s, 'PARENT')",
            (fam.child_id, parent),
        )
        for scope in ("experiments:read", "learnings:read"):
            conn.execute(
                "insert into serene.caregiver_grants "
                "(child_id, caregiver_id, scope, granted_by, expires_at) "
                "values (%s, %s, %s, %s, now() + interval '1 day')",
                (fam.child_id, caregiver, scope, parent),
            )
    for user, visible in ((parent, True), (other, False), (caregiver, False)):
        with psycopg.connect(pg_dsn) as conn:
            conn.execute("set local role authenticated")
            conn.execute("select set_config('request.jwt.claim.sub', %s, true)", (str(user),))
            rows = conn.execute(
                "select state from serene.projection_state where projection = 'experiments'"
            ).fetchall()
            assert bool(rows) is visible
            if visible:
                assert ExperimentsView.model_validate_json(json.dumps(rows[0][0])).experiments
