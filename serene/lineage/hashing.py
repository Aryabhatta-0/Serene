"""Hash-chain sealing for ledger events (issue #4).

payload_hash = sha256(canonical_json(payload))
event_hash   = sha256(canonical_json(header)), where header covers every
               envelope field plus payload_hash and prev_event_hash.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from serene.domain.canonical import canonical_digest, format_timestamp, to_canonical_data
from serene.domain.events import HASH_VERSION, DomainEvent, EventDraft


def _header(
    *,
    event_id: str,
    child_id: str,
    sequence: int,
    event_type: str,
    schema_version: int,
    hash_version: int,
    source: Any,
    actor: Any,
    occurred_at: datetime,
    recorded_at: datetime,
    derived_from: tuple[str, ...],
    verification_status: str,
    payload_hash: str,
    prev_event_hash: str,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "child_id": child_id,
        "sequence": sequence,
        "event_type": event_type,
        "schema_version": schema_version,
        "hash_version": hash_version,
        "source": source,
        "actor": actor,
        "occurred_at": format_timestamp(occurred_at),
        "recorded_at": format_timestamp(recorded_at),
        "derived_from": list(derived_from),
        "verification_status": verification_status,
        "payload_hash": payload_hash,
        "prev_event_hash": prev_event_hash,
    }


def compute_payload_hash(payload: Any) -> str:
    return canonical_digest(payload)


def compute_event_hash(event: DomainEvent) -> str:
    """Recompute an event's hash from its stored fields (ignores the stored event_hash)."""
    return canonical_digest(
        _header(
            event_id=event.event_id,
            child_id=event.child_id,
            sequence=event.sequence,
            event_type=event.event_type.value,
            schema_version=event.schema_version,
            hash_version=event.hash_version,
            source=event.source,
            actor=event.actor,
            occurred_at=event.occurred_at,
            recorded_at=event.recorded_at,
            derived_from=event.derived_from,
            verification_status=event.verification_status.value,
            payload_hash=event.payload_hash,
            prev_event_hash=event.prev_event_hash,
        )
    )


def seal_event(
    draft: EventDraft,
    *,
    event_id: str,
    sequence: int,
    recorded_at: datetime,
    prev_event_hash: str,
) -> DomainEvent:
    payload = to_canonical_data(draft.payload)
    payload_hash = compute_payload_hash(payload)
    header = _header(
        event_id=event_id,
        child_id=draft.child_id,
        sequence=sequence,
        event_type=draft.event_type.value,
        schema_version=draft.payload.schema_version,
        hash_version=HASH_VERSION,
        source=draft.source,
        actor=draft.actor,
        occurred_at=draft.occurred_at,
        recorded_at=recorded_at,
        derived_from=draft.derived_from,
        verification_status=draft.verification_status.value,
        payload_hash=payload_hash,
        prev_event_hash=prev_event_hash,
    )
    return DomainEvent(
        event_id=event_id,
        child_id=draft.child_id,
        sequence=sequence,
        event_type=draft.event_type,
        schema_version=draft.payload.schema_version,
        hash_version=HASH_VERSION,
        source=draft.source,
        actor=draft.actor,
        occurred_at=draft.occurred_at,
        recorded_at=recorded_at,
        derived_from=draft.derived_from,
        verification_status=draft.verification_status,
        payload=payload,
        prev_event_hash=prev_event_hash,
        payload_hash=payload_hash,
        event_hash=canonical_digest(header),
    )
