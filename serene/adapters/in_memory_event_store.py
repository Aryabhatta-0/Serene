"""In-process EventStore for tests, eval and local tooling. Append-only by construction."""

from __future__ import annotations

import threading
from collections.abc import Sequence

from serene.domain.events import GENESIS_HASH, DomainEvent
from serene.ports.event_store import ConcurrencyConflict


class InMemoryEventStore:
    def __init__(self) -> None:
        self._streams: dict[str, list[DomainEvent]] = {}
        self._lock = threading.Lock()

    def append(self, event: DomainEvent, *, expected_prev_hash: str) -> None:
        with self._lock:
            stream = self._streams.setdefault(event.child_id, [])
            head = stream[-1].event_hash if stream else GENESIS_HASH
            if head != expected_prev_hash or event.prev_event_hash != head:
                raise ConcurrencyConflict(f"stream head moved for {event.child_id}")
            if event.sequence != len(stream) + 1:
                raise ConcurrencyConflict("sequence does not extend the stream")
            stream.append(event)

    def read_stream(self, child_id: str) -> Sequence[DomainEvent]:
        with self._lock:
            return tuple(self._streams.get(child_id, ()))
