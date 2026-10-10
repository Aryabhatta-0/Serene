"""The ledger against a real PostgreSQL with the Supabase migration applied (issues #3-#6)."""

from __future__ import annotations

import pytest

pytest.importorskip("psycopg")

import psycopg

from serene.adapters.postgres import (
    LedgerWriteRefused,
    PostgresEventStore,
    PostgresProjectionStore,
)
from serene.domain.canonical import canonical_json
from serene.lineage.chain import verify_hash_chain
from serene.ports.event_store import ConcurrencyConflict
from serene.projections import rebuild_projections
from serene.testing import build_full_ladder

pytestmark = pytest.mark.postgres


def test_full_ladder_round_trips_through_postgres(pg_dsn: str) -> None:
    store = PostgresEventStore(pg_dsn)
    ladder = build_full_ladder(seed="pg", store=store)
    fam = ladder["family"]
    reference = build_full_ladder(seed="pg")["family"]

    stored = list(store.read_stream(fam.child_id))
    expected = list(reference.store.read_stream(reference.child_id))
    assert stored == expected  # byte-for-byte identical events after the DB round trip
    assert verify_hash_chain(stored).ok
    assert fam.ledger.verify_hash_chain(fam.child_id).ok


def test_update_delete_truncate_are_refused_by_the_database(pg_dsn: str) -> None:
    store = PostgresEventStore(pg_dsn)
    fam = build_full_ladder(seed="pg-immut", store=store)["family"]
    for statement in (
        "update serene.domain_events set payload = '{}'::jsonb",
        "delete from serene.domain_events",
        "truncate serene.domain_events",
    ):
        with psycopg.connect(pg_dsn) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(statement)
    assert verify_hash_chain(store.read_stream(fam.child_id)).ok


def test_database_refuses_an_event_that_does_not_extend_the_head(pg_dsn: str) -> None:
    store = PostgresEventStore(pg_dsn)
    fam = build_full_ladder(seed="pg-link", store=store)["family"]
    events = list(store.read_stream(fam.child_id))
    last = events[-1]
    forged = last.model_copy(
        update={
            "event_id": fam.new_id("evt"),
            "sequence": last.sequence + 1,
            "prev_event_hash": events[0].event_hash,  # fork from an old head
            "event_hash": "e" * 64,
        }
    )
    with pytest.raises(LedgerWriteRefused):
        store.append(forged, expected_prev_hash=last.event_hash)
    with pytest.raises(ConcurrencyConflict):
        store.append(forged, expected_prev_hash=events[0].event_hash)


def test_out_of_band_tampering_is_detected_by_verification(pg_dsn: str) -> None:
    """Even a superuser that bypasses triggers cannot rewrite history undetected."""
    store = PostgresEventStore(pg_dsn)
    fam = build_full_ladder(seed="pg-tamper", store=store)["family"]
    with psycopg.connect(pg_dsn) as conn:
        conn.execute("set session_replication_role = replica")  # disables triggers
        conn.execute(
            "update serene.domain_events set payload = jsonb_set(payload, "
            "'{evidence,content}', '\"rewritten\"') where sequence = 1 and child_id = %s",
            (fam.child_id,),
        )
    result = verify_hash_chain(store.read_stream(fam.child_id))
    assert (result.ok, result.failure_index, result.reason) == (
        False,
        0,
        "PAYLOAD_HASH_MISMATCH",
    )


def test_projection_rows_can_be_deleted_and_rebuilt_identically(pg_dsn: str) -> None:
    store = PostgresEventStore(pg_dsn)
    projections = PostgresProjectionStore(pg_dsn)
    fam = build_full_ladder(seed="pg-proj", store=store)["family"]
    events = list(store.read_stream(fam.child_id))
    head = events[-1]

    original = rebuild_projections(events)
    projections.replace(
        fam.child_id, original, last_sequence=head.sequence, last_event_hash=head.event_hash
    )
    assert canonical_json(projections.load(fam.child_id)) == canonical_json(original)

    projections.delete(fam.child_id)
    assert projections.load(fam.child_id) == {}
    rebuilt = rebuild_projections(store.read_stream(fam.child_id))
    projections.replace(
        fam.child_id, rebuilt, last_sequence=head.sequence, last_event_hash=head.event_hash
    )
    assert canonical_json(projections.load(fam.child_id)) == canonical_json(original)
