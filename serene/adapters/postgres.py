"""Postgres / Supabase adapters for the EventStore port and projection storage.

Requires the `postgres` extra (psycopg 3). The schema lives in
`supabase/migrations/`. The adapter stores exactly what the kernel sealed; it
never computes hashes and never issues UPDATE/DELETE against the ledger.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import psycopg
from psycopg import errors
from psycopg.types.json import Jsonb

from serene.domain.canonical import canonical_json, format_timestamp, to_canonical_data
from serene.domain.events import GENESIS_HASH, DomainEvent
from serene.ports.event_store import ConcurrencyConflict

_COLUMNS = (
    "event_id, child_id, sequence, event_type, schema_version, hash_version, source, actor, "
    "occurred_at, recorded_at, derived_from, verification_status, payload, prev_event_hash, "
    "payload_hash, event_hash"
)


class LedgerWriteRefused(RuntimeError):
    """The database refused an append (chain linkage, vocabulary or append-only guard)."""


def _row_to_event(row: Sequence[Any]) -> DomainEvent:
    data = dict(zip([c.strip() for c in _COLUMNS.split(",")], row, strict=True))
    data["occurred_at"] = format_timestamp(data["occurred_at"])
    data["recorded_at"] = format_timestamp(data["recorded_at"])
    data["derived_from"] = list(data["derived_from"])
    return DomainEvent.model_validate_json(json.dumps(data, ensure_ascii=False))


class PostgresEventStore:
    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def _connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self._conninfo)

    def append(self, event: DomainEvent, *, expected_prev_hash: str) -> None:
        source = to_canonical_data(event.source)
        actor = to_canonical_data(event.actor)
        try:
            with self._connect() as conn, conn.transaction():
                conn.execute(
                    "select pg_advisory_xact_lock(hashtextextended(%s, 0))", (event.child_id,)
                )
                row = conn.execute(
                    "select event_hash from serene.domain_events where child_id = %s "
                    "order by sequence desc limit 1",
                    (event.child_id,),
                ).fetchone()
                head = row[0] if row else GENESIS_HASH
                if head != expected_prev_hash:
                    raise ConcurrencyConflict(f"stream head moved for {event.child_id}")
                conn.execute(
                    f"insert into serene.domain_events ({_COLUMNS}) values "  # noqa: S608
                    "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        event.event_id,
                        event.child_id,
                        event.sequence,
                        event.event_type.value,
                        event.schema_version,
                        event.hash_version,
                        Jsonb(source),
                        Jsonb(actor),
                        event.occurred_at,
                        event.recorded_at,
                        list(event.derived_from),
                        event.verification_status.value,
                        Jsonb(event.payload),
                        event.prev_event_hash,
                        event.payload_hash,
                        event.event_hash,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise ConcurrencyConflict(str(exc)) from exc
        except (errors.CheckViolation, errors.ForeignKeyViolation) as exc:
            raise LedgerWriteRefused(str(exc)) from exc

    def read_stream(self, child_id: str) -> Sequence[DomainEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                f"select {_COLUMNS} from serene.domain_events "  # noqa: S608
                "where child_id = %s order by sequence",
                (child_id,),
            ).fetchall()
        return tuple(_row_to_event(r) for r in rows)


class PostgresProjectionStore:
    """Disposable projection rows. Safe to delete at any time and rebuild by replay."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def replace(
        self,
        child_id: str,
        projections: dict[str, dict[str, Any]],
        *,
        last_sequence: int,
        last_event_hash: str,
    ) -> None:
        with psycopg.connect(self._conninfo) as conn, conn.transaction():
            conn.execute("delete from serene.projection_state where child_id = %s", (child_id,))
            for name, state in sorted(projections.items()):
                conn.execute(
                    "insert into serene.projection_state "
                    "(child_id, projection, state, last_sequence, last_event_hash) "
                    "values (%s, %s, %s, %s, %s)",
                    (child_id, name, Jsonb(state), last_sequence, last_event_hash),
                )

    def load(self, child_id: str) -> dict[str, dict[str, Any]]:
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                "select projection, state from serene.projection_state where child_id = %s",
                (child_id,),
            ).fetchall()
        # Round-trip through canonical JSON so jsonb key ordering cannot matter.
        return {name: json.loads(canonical_json(state)) for name, state in rows}

    def delete(self, child_id: str) -> None:
        with psycopg.connect(self._conninfo) as conn, conn.transaction():
            conn.execute("delete from serene.projection_state where child_id = %s", (child_id,))
