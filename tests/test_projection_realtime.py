"""Projection state kept in step with the ledger, for Realtime (issue #33).

The ledger hands each admitted event and the state it produced to the read
side; Postgres keeps serene.projection_state current with a monotonic publish;
and on Supabase only projection_state, never the ledger, is in the Realtime
publication."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from serene.domain.canonical import canonical_json
from serene.domain.events import DomainEvent
from serene.ledger import AdmissionRejected
from serene.ledger.service import EventLedger
from serene.observability.telemetry import RecordingSink, SafeTelemetry
from serene.projections import replay
from serene.projections.state import KernelState
from serene.projections.views import project, rebuild_projections
from serene.testing import SyntheticFamily, build_full_ladder

from .conftest import MIGRATIONS


def _hooked(fam: SyntheticFamily, hook: object, telemetry: SafeTelemetry | None = None) -> None:
    fam.ledger = EventLedger(
        fam.store,
        fam.clock,
        telemetry=telemetry,
        new_event_id=lambda: fam.new_id("evt"),
        after_append=hook,  # type: ignore[arg-type]
    )


def test_the_hook_sees_every_admitted_event_with_the_state_it_produced() -> None:
    fam = SyntheticFamily(seed="hook-state")
    seen: list[tuple[int, str]] = []

    def hook(event: DomainEvent, state: KernelState) -> None:
        # The state handed over is exactly the replay up to and including it.
        rebuilt = replay(fam.ledger.get_events_for_child(event.child_id))
        assert canonical_json(project(state)) == canonical_json(project(rebuilt))
        assert state.last_sequence == event.sequence
        seen.append((event.sequence, event.event_hash))

    _hooked(fam, hook)
    fam.observe("tearful pickup", day=0)
    fam.observe("tearful pickup again", day=1)
    events = fam.ledger.get_events_for_child(fam.child_id)
    assert seen == [(e.sequence, e.event_hash) for e in events]


def test_a_refused_event_reaches_no_read_state() -> None:
    fam = SyntheticFamily(seed="hook-refused")
    calls: list[int] = []
    _hooked(fam, lambda event, state: calls.append(event.sequence))
    fam.open_investigation("why?")
    last = fam.ledger.get_events_for_child(fam.child_id)[-1]
    before = list(calls)
    with pytest.raises(AdmissionRejected):  # the same entity twice
        fam.append(fam.draft(last.event_type, last.actor, last.typed_payload()))
    assert calls == before


def test_a_failing_read_side_never_fails_the_append() -> None:
    fam = SyntheticFamily(seed="hook-fails")
    sink = RecordingSink()

    def broken(event: DomainEvent, state: KernelState) -> None:
        raise RuntimeError("projection store unavailable")

    _hooked(fam, broken, SafeTelemetry(sink))
    fam.observe("tearful pickup", day=0)
    assert len(fam.ledger.get_events_for_child(fam.child_id)) > 0
    failures = [a for name, a in sink.records if name == "ledger.after_append_failed"]
    assert failures and failures[0]["error_type"] == "RuntimeError"


# ------------------------------------------------------------------ Postgres
@pytest.mark.postgres
def test_projection_state_follows_the_ledger_live(pg_dsn: str) -> None:
    from serene.adapters.postgres import (
        PostgresEventStore,
        PostgresProjectionStore,
        projection_publisher,
    )

    store = PostgresEventStore(pg_dsn)
    projections = PostgresProjectionStore(pg_dsn)
    fam = SyntheticFamily(seed="pg-live", store=store)
    _hooked(fam, projection_publisher(projections))

    fam.observe("tearful pickup", day=0)
    first = projections.load(fam.child_id)
    inv = fam.open_investigation("why are pickups hard?")
    second = projections.load(fam.child_id)
    assert first["active_investigations"] == {}
    assert list(second["active_investigations"]) == [inv.investigation_id]

    import psycopg

    with psycopg.connect(pg_dsn) as conn:
        rows = conn.execute(
            "select projection, last_sequence, last_event_hash from serene.projection_state "
            "where child_id = %s",
            (fam.child_id,),
        ).fetchall()
    head = fam.ledger.get_events_for_child(fam.child_id)[-1]
    assert {r[0] for r in rows} == set(second)
    assert all((r[1], r[2]) == (head.sequence, head.event_hash) for r in rows)
    # Exactly what a full rebuild from the ledger produces.
    rebuilt = rebuild_projections(store.read_stream(fam.child_id))
    assert canonical_json(second) == canonical_json(rebuilt)


@pytest.mark.postgres
def test_publish_never_moves_read_state_backwards(pg_dsn: str) -> None:
    from serene.adapters.postgres import PostgresEventStore, PostgresProjectionStore

    store = PostgresEventStore(pg_dsn)
    projections = PostgresProjectionStore(pg_dsn)
    fam = build_full_ladder(seed="pg-monotonic", store=store)["family"]
    events = list(store.read_stream(fam.child_id))
    early, head = events[: len(events) // 2], events[-1]
    latest = rebuild_projections(events)
    projections.advance(
        fam.child_id, latest, last_sequence=head.sequence, last_event_hash=head.event_hash
    )
    stale = rebuild_projections(early)
    projections.advance(
        fam.child_id,
        stale,
        last_sequence=early[-1].sequence,
        last_event_hash=early[-1].event_hash,
    )
    assert canonical_json(projections.load(fam.child_id)) == canonical_json(latest)


@pytest.fixture
def supabase_like_dsn(pg_admin_dsn: str) -> Iterator[str]:
    """A fresh database with Supabase's Realtime publication created first."""
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    name = f"serene_rt_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(pg_admin_dsn, autocommit=True) as admin:
        admin.execute(f'create database "{name}"')
    params = conninfo_to_dict(pg_admin_dsn)
    params["dbname"] = name
    dsn = make_conninfo(**params)
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute("create publication supabase_realtime")
            for migration in MIGRATIONS:
                conn.execute(migration.read_text(encoding="utf-8"))
            # Re-running is safe (migrations are applied once, but must be idempotent here).
            conn.execute(Path(MIGRATIONS[-1]).read_text(encoding="utf-8"))
        yield dsn
    finally:
        with psycopg.connect(pg_admin_dsn, autocommit=True) as admin:
            admin.execute(f'drop database if exists "{name}" with (force)')


@pytest.mark.postgres
def test_only_projection_state_is_published_to_realtime(supabase_like_dsn: str) -> None:
    import psycopg

    with psycopg.connect(supabase_like_dsn) as conn:
        published = conn.execute(
            "select schemaname, tablename from pg_publication_tables "
            "where pubname = 'supabase_realtime'"
        ).fetchall()
    assert published == [("serene", "projection_state")]


@pytest.mark.postgres
def test_plain_postgres_has_no_realtime_publication(pg_dsn: str) -> None:
    import psycopg

    with psycopg.connect(pg_dsn) as conn:
        assert conn.execute("select count(*) from pg_publication").fetchone() == (0,)
