"""Postgres / Supabase adapters for the EventStore port and projection storage.

Requires the `postgres` extra (psycopg 3). The schema lives in
`supabase/migrations/`. The adapter stores exactly what the kernel sealed; it
never computes hashes and never issues UPDATE/DELETE against the ledger.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg
from psycopg import errors
from psycopg.types.json import Jsonb

from serene.domain.canonical import canonical_json, format_timestamp, to_canonical_data
from serene.domain.events import GENESIS_HASH, DomainEvent
from serene.ledger.service import AfterAppend, EventLedger
from serene.lineage.chain import LedgerIntegrityError
from serene.observability.telemetry import SafeTelemetry
from serene.ports.clock import Clock
from serene.ports.event_store import ConcurrencyConflict
from serene.projections.state import KernelState
from serene.projections.views import project

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
                    raise ConcurrencyConflict("STREAM_HEAD_MOVED")
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
        except errors.UniqueViolation:
            raise ConcurrencyConflict("LEDGER_UNIQUE_CONFLICT") from None
        except (errors.CheckViolation, errors.ForeignKeyViolation):
            raise LedgerWriteRefused("LEDGER_WRITE_REFUSED") from None

    def read_stream(self, child_id: str) -> Sequence[DomainEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                f"select {_COLUMNS} from serene.domain_events "  # noqa: S608
                "where child_id = %s order by sequence",
                (child_id,),
            ).fetchall()
        return tuple(_row_to_event(r) for r in rows)

    def child_ids(self) -> tuple[str, ...]:
        """Every child with at least one event (operator backfill only)."""
        with self._connect() as conn:
            rows = conn.execute(
                "select distinct child_id from serene.domain_events order by child_id"
            ).fetchall()
        return tuple(r[0] for r in rows)


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

    def advance(
        self,
        child_id: str,
        projections: dict[str, dict[str, Any]],
        *,
        last_sequence: int,
        last_event_hash: str,
    ) -> None:
        """Bring the rows up to `last_sequence` in place (issue #33).

        Unlike `replace`, this never deletes a projection that still exists, so a
        Realtime subscriber sees one update per changed row and no transient gap.
        It is monotonic: a row already at a later sequence is left alone, so a
        late or repeated publish can never move the read state backwards.
        """
        with psycopg.connect(self._conninfo) as conn, conn.transaction():
            for name, state in sorted(projections.items()):
                conn.execute(
                    "insert into serene.projection_state "
                    "(child_id, projection, state, last_sequence, last_event_hash) "
                    "values (%s, %s, %s, %s, %s) "
                    "on conflict (child_id, projection) do update set "
                    "state = excluded.state, last_sequence = excluded.last_sequence, "
                    "last_event_hash = excluded.last_event_hash, rebuilt_at = now() "
                    "where serene.projection_state.last_sequence < excluded.last_sequence",
                    (child_id, name, Jsonb(state), last_sequence, last_event_hash),
                )
            conn.execute(
                "delete from serene.projection_state "
                "where child_id = %s and not (projection = any(%s)) and last_sequence <= %s",
                (child_id, sorted(projections), last_sequence),
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


def projection_publisher(store: PostgresProjectionStore) -> AfterAppend:
    """An `EventLedger(after_append=...)` hook that keeps projection_state in step."""

    def advance(event: DomainEvent, state: KernelState) -> None:
        store.advance(
            event.child_id,
            project(state),
            last_sequence=event.sequence,
            last_event_hash=event.event_hash,
        )

    return advance


def postgres_ledger(
    conninfo: str, clock: Clock, *, telemetry: SafeTelemetry | None = None
) -> EventLedger:
    """The production ledger (issue #87): Postgres, with projection_state kept live.

    Every admitted append is followed by a monotonic projection publish, so the
    web app's Realtime subscription (#33) sees it. A publish failure is reported
    and never undoes the append; `backfill_projections` repairs the read side.
    """
    return EventLedger(
        PostgresEventStore(conninfo),
        clock,
        telemetry=telemetry,
        after_append=projection_publisher(PostgresProjectionStore(conninfo)),
    )


@dataclass(frozen=True, slots=True)
class BackfillResult:
    written: int  # children whose projection rows were (re)published
    empty: int  # children with no events: nothing to publish
    refused: int  # children whose hash chain does not verify: left untouched


def backfill_projections(
    conninfo: str,
    child_ids: Iterable[str] | None = None,
    *,
    replace: bool = False,
) -> BackfillResult:
    """Rebuild projection_state from a verified replay of each child's ledger.

    The default publishes with `advance`, which is monotonic and idempotent:
    safe while the kernel is running, and it never moves read state backwards.
    `replace=True` deletes and rewrites each child's rows; use it only after a
    projection definition changed, with the kernel quiet. A child whose chain
    does not verify is refused and left as it is. The ledger is only read.
    """
    events = PostgresEventStore(conninfo)
    store = PostgresProjectionStore(conninfo)
    written = empty = refused = 0
    for child_id in events.child_ids() if child_ids is None else child_ids:
        stream = list(events.read_stream(child_id))
        if not stream:
            empty += 1
            continue
        try:
            state = EventLedger(events, _NoClock()).replay_events(child_id)
        except LedgerIntegrityError:
            refused += 1
            continue
        publish = store.replace if replace else store.advance
        publish(
            child_id,
            project(state),
            last_sequence=state.last_sequence,
            last_event_hash=state.last_event_hash,
        )
        written += 1
    return BackfillResult(written, empty, refused)


class _NoClock:
    """Backfill only replays; it never appends, so it never asks the time."""

    def now(self) -> datetime:
        raise RuntimeError("backfill does not append")
