"""End-to-end verification of a child's event stream (issue #4)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from serene.domain.events import EVENT_TAXONOMY, GENESIS_HASH, DomainEvent
from serene.lineage.hashing import compute_event_hash, compute_payload_hash


@dataclass(frozen=True, slots=True)
class ChainVerification:
    ok: bool
    checked: int
    failure_index: int | None = None
    reason: str | None = None


class LedgerIntegrityError(RuntimeError):
    def __init__(self, result: ChainVerification) -> None:
        super().__init__(f"hash chain broken at index {result.failure_index}: {result.reason}")
        self.result = result


def verify_hash_chain(events: Sequence[DomainEvent]) -> ChainVerification:
    """Validate ordering, linkage, payload/event hashes and ancestry of one stream."""
    seen: set[str] = set()
    prev_hash = GENESIS_HASH
    child_id = events[0].child_id if events else None

    def fail(index: int, reason: str) -> ChainVerification:
        return ChainVerification(ok=False, checked=index, failure_index=index, reason=reason)

    for index, event in enumerate(events):
        if event.child_id != child_id:
            return fail(index, "CHILD_MISMATCH")
        if event.sequence != index + 1:
            return fail(index, "SEQUENCE_GAP")
        if event.event_id in seen:
            return fail(index, "DUPLICATE_EVENT_ID")
        if event.prev_event_hash != prev_hash:
            return fail(index, "PREV_HASH_MISMATCH")
        if compute_payload_hash(event.payload) != event.payload_hash:
            return fail(index, "PAYLOAD_HASH_MISMATCH")
        if compute_event_hash(event) != event.event_hash:
            return fail(index, "EVENT_HASH_MISMATCH")
        if any(parent not in seen for parent in event.derived_from):
            return fail(index, "UNKNOWN_ANCESTOR")
        try:
            event.typed_payload()
        except ValueError:
            return fail(index, "PAYLOAD_SCHEMA_INVALID")
        if (
            event.schema_version
            != EVENT_TAXONOMY[event.event_type].payload.model_fields["schema_version"].default
        ):
            return fail(index, "SCHEMA_VERSION_MISMATCH")
        seen.add(event.event_id)
        prev_hash = event.event_hash
    return ChainVerification(ok=True, checked=len(events))
