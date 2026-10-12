"""The production ledger keeps projection_state live, and the read side can be rebuilt (#87).

`postgres_ledger` is how every production entry point builds its ledger: each
admitted append is followed by a monotonic projection publish. A publish that
fails never undoes the append, and `backfill_projections` repairs read state
from a verified replay without ever writing the ledger.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from serene.domain.canonical import canonical_json
from serene.observability.telemetry import RecordingSink, SafeTelemetry
from serene.projections.views import rebuild_projections
from serene.testing import SyntheticFamily, build_full_ladder

ROOT = Path(__file__).resolve().parents[1]
# Every process that appends to the production ledger.
ENTRY_POINTS = (ROOT / "app" / "telegram" / "webhook_server.py",)


def _calls(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        ast.unparse(node.func).rsplit(".", 1)[-1]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }


@pytest.mark.parametrize("entry", ENTRY_POINTS, ids=lambda p: p.parent.name)
def test_every_production_entry_point_builds_the_publishing_ledger(entry: Path) -> None:
    calls = _calls(entry)
    assert "postgres_ledger" in calls
    # A bare EventLedger / PostgresEventStore here would append without publishing.
    assert "EventLedger" not in calls
    assert "PostgresEventStore" not in calls


def _rows(dsn: str, child_id: str) -> list[tuple[str, int, str]]:
    import psycopg

    with psycopg.connect(dsn) as conn:
        return conn.execute(
            "select projection, last_sequence, last_event_hash from serene.projection_state "
            "where child_id = %s order by projection",
            (child_id,),
        ).fetchall()


@pytest.mark.postgres
def test_the_production_ledger_publishes_every_admitted_append(pg_dsn: str) -> None:
    from serene.adapters.postgres import (
        PostgresEventStore,
        PostgresProjectionStore,
        postgres_ledger,
    )

    fam = SyntheticFamily(seed="prod-live", store=PostgresEventStore(pg_dsn))
    fam.ledger = postgres_ledger(pg_dsn, fam.clock)
    fam.observe("tearful pickup", day=0)
    inv = fam.open_investigation("why are pickups hard?")

    head = fam.ledger.get_events_for_child(fam.child_id)[-1]
    rows = _rows(pg_dsn, fam.child_id)
    assert rows and all((r[1], r[2]) == (head.sequence, head.event_hash) for r in rows)
    live = PostgresProjectionStore(pg_dsn).load(fam.child_id)
    assert list(live["active_investigations"]) == [inv.investigation_id]
    assert inv.investigation_id in live["investigations"]
    rebuilt = rebuild_projections(PostgresEventStore(pg_dsn).read_stream(fam.child_id))
    assert canonical_json(live) == canonical_json(rebuilt)


@pytest.mark.postgres
def test_a_failed_publish_keeps_the_append_and_a_backfill_repairs_it(pg_dsn: str) -> None:
    import psycopg

    from serene.adapters.postgres import (
        PostgresEventStore,
        PostgresProjectionStore,
        backfill_projections,
        postgres_ledger,
    )

    sink = RecordingSink()
    fam = SyntheticFamily(seed="prod-fails", store=PostgresEventStore(pg_dsn))
    fam.ledger = postgres_ledger(pg_dsn, fam.clock, telemetry=SafeTelemetry(sink))
    fam.observe("tearful pickup", day=0)
    with psycopg.connect(pg_dsn, autocommit=True) as conn:  # the read side goes away
        conn.execute("alter table serene.projection_state rename to projection_state_away")
    fam.open_investigation("why are pickups hard?")
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        conn.execute("alter table serene.projection_state_away rename to projection_state")

    events = PostgresEventStore(pg_dsn).read_stream(fam.child_id)
    assert events[-1].event_type.value == "INVESTIGATION_OPENED"  # admitted and kept
    assert any(name == "ledger.after_append_failed" for name, _ in sink.records)
    assert all(r[1] < events[-1].sequence for r in _rows(pg_dsn, fam.child_id))  # lagging

    result = backfill_projections(pg_dsn)
    assert (result.written, result.refused) == (1, 0)
    assert all(r[1] == events[-1].sequence for r in _rows(pg_dsn, fam.child_id))
    assert canonical_json(PostgresProjectionStore(pg_dsn).load(fam.child_id)) == canonical_json(
        rebuild_projections(events)
    )


@pytest.mark.postgres
def test_backfill_publishes_an_existing_ledger_and_is_idempotent(pg_dsn: str) -> None:
    from serene.adapters.postgres import (
        PostgresEventStore,
        PostgresProjectionStore,
        backfill_projections,
    )

    store = PostgresEventStore(pg_dsn)
    a = build_full_ladder(seed="backfill-a", store=store)["family"]  # appended without publishing
    b = build_full_ladder(seed="backfill-b", store=store)["family"]
    assert _rows(pg_dsn, a.child_id) == []

    for replace in (False, False, True):
        result = backfill_projections(pg_dsn, replace=replace)
        assert (result.written, result.empty, result.refused) == (2, 0, 0)
        for fam in (a, b):
            assert canonical_json(PostgresProjectionStore(pg_dsn).load(fam.child_id)) == (
                canonical_json(rebuild_projections(store.read_stream(fam.child_id)))
            )

    only = backfill_projections(pg_dsn, [a.child_id, "chd_" + "0" * 32])
    assert (only.written, only.empty, only.refused) == (1, 1, 0)


@pytest.mark.postgres
def test_backfill_refuses_a_child_whose_chain_does_not_verify(pg_dsn: str) -> None:
    import psycopg

    from serene.adapters.postgres import PostgresEventStore, backfill_projections

    store = PostgresEventStore(pg_dsn)
    fam = build_full_ladder(seed="backfill-tampered", store=store)["family"]
    with psycopg.connect(pg_dsn, autocommit=True) as conn:  # an attacker with superuser
        conn.execute("alter table serene.domain_events disable trigger user")
        conn.execute(
            "update serene.domain_events set payload = jsonb_set(payload, "
            "'{evidence,content}', '\"rewritten history\"') where child_id = %s and sequence = 1",
            (fam.child_id,),
        )
        conn.execute("alter table serene.domain_events enable trigger user")

    result = backfill_projections(pg_dsn)
    assert (result.written, result.refused) == (0, 1)
    assert _rows(pg_dsn, fam.child_id) == []  # nothing derived from a broken chain
