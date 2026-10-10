"""The immutable event ledger service (issues #3, #4, #5).

    append_event          validate -> admit -> seal -> compare-and-set append
    verify_hash_chain     end-to-end tamper detection for one child
    get_events_for_child  verified read of a child's stream
    replay_events         verified rebuild of kernel state / projections

Changed understanding is recorded by appending a new event; history is never
mutated. A stream whose chain does not verify accepts no further appends.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from serene.domain.base import new_id
from serene.domain.events import EVENT_TAXONOMY, DomainEvent, EventDraft
from serene.lineage.chain import ChainVerification, LedgerIntegrityError, verify_hash_chain
from serene.lineage.hashing import seal_event
from serene.observability.telemetry import SafeTelemetry
from serene.policies.admission import admission_violations
from serene.ports.clock import Clock
from serene.ports.event_store import EventStore
from serene.projections.state import KernelState, replay
from serene.projections.views import project


class AdmissionRejected(ValueError):
    """The draft was refused. Nothing was written."""

    def __init__(self, reason_codes: list[str]) -> None:
        super().__init__(", ".join(reason_codes))
        self.reason_codes = tuple(reason_codes)


def envelope_violations(draft: EventDraft) -> list[str]:
    """Stateless checks: closed taxonomy, payload schema, actor and status permissions."""
    spec = EVENT_TAXONOMY.get(draft.event_type)
    if spec is None:
        return ["UNKNOWN_EVENT_TYPE"]
    reasons: list[str] = []
    if type(draft.payload) is not spec.payload:
        reasons.append("PAYLOAD_SCHEMA_MISMATCH")
    if draft.actor.kind not in spec.actors:
        reasons.append(f"ACTOR_NOT_PERMITTED:{draft.actor.kind.value}")
    if draft.verification_status not in spec.statuses:
        reasons.append(f"STATUS_NOT_PERMITTED:{draft.verification_status.value}")
    for name in type(draft.payload).model_fields:
        nested_child = getattr(getattr(draft.payload, name), "child_id", None)
        if nested_child is not None and nested_child != draft.child_id:
            reasons.append("CHILD_MISMATCH")
    return reasons


class EventLedger:
    def __init__(
        self,
        store: EventStore,
        clock: Clock,
        *,
        telemetry: SafeTelemetry | None = None,
        new_event_id: Callable[[], str] = lambda: new_id("evt"),
    ) -> None:
        self._store = store
        self._clock = clock
        self._telemetry = telemetry or SafeTelemetry()
        self._new_event_id = new_event_id

    # ------------------------------------------------------------------ reads
    def verify_hash_chain(self, child_id: str) -> ChainVerification:
        result = verify_hash_chain(self._store.read_stream(child_id))
        self._telemetry.emit(
            "ledger.verify",
            {
                "child_id": child_id,
                "chain_ok": result.ok,
                "count": result.checked,
                "failure_index": -1 if result.failure_index is None else result.failure_index,
                "reason_codes": result.reason or "",
            },
        )
        return result

    def get_events_for_child(self, child_id: str) -> list[DomainEvent]:
        events = list(self._store.read_stream(child_id))
        result = verify_hash_chain(events)
        if not result.ok:
            raise LedgerIntegrityError(result)
        return events

    def replay_events(self, child_id: str) -> KernelState:
        return replay(self.get_events_for_child(child_id))

    def projections(self, child_id: str) -> dict[str, dict[str, Any]]:
        return project(self.replay_events(child_id))

    # ------------------------------------------------------------------ write
    def append_event(self, draft: EventDraft) -> DomainEvent:
        reasons = envelope_violations(draft)
        if reasons:
            self._reject(draft, reasons)

        state = self.replay_events(draft.child_id)  # raises on a tampered stream
        reasons = [f"UNKNOWN_ANCESTOR:{e}" for e in draft.derived_from if e not in state.event_ids]
        now = self._clock.now()
        reasons += admission_violations(draft, state, now)
        if reasons:
            self._reject(draft, reasons)

        event = seal_event(
            draft,
            event_id=self._new_event_id(),
            sequence=state.last_sequence + 1,
            recorded_at=now,
            prev_event_hash=state.last_event_hash,
        )
        self._store.append(event, expected_prev_hash=state.last_event_hash)
        self._telemetry.emit(
            "ledger.append",
            {
                "child_id": event.child_id,
                "event_type": event.event_type.value,
                "event_id": event.event_id,
                "sequence": event.sequence,
                "actor_kind": event.actor.kind.value,
                "source_kind": event.source.kind.value,
                "verification_status": event.verification_status.value,
                "decision": "ADMITTED",
            },
        )
        return event

    def _reject(self, draft: EventDraft, reasons: list[str]) -> None:
        self._telemetry.emit(
            "ledger.reject",
            {
                "child_id": draft.child_id,
                "event_type": draft.event_type.value,
                "actor_kind": draft.actor.kind.value,
                "decision": "REJECTED",
                "reason_codes": tuple(r.split(":", 1)[0] for r in reasons),
            },
        )
        raise AdmissionRejected(reasons)
