"""EventStore port: append-only persistence for hash-chained domain events.

Implementations store and return events exactly; they never compute hashes,
never update or delete, and reject an append whose expected head is stale
(compare-and-set), so two writers cannot fork a child's chain.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from serene.domain.events import DomainEvent


class ConcurrencyConflict(RuntimeError):
    """The stream head moved since the caller read it; re-read and re-decide."""


@runtime_checkable
class EventStore(Protocol):
    def append(self, event: DomainEvent, *, expected_prev_hash: str) -> None:
        """Atomically append iff the stream head equals `expected_prev_hash`."""
        ...

    def read_stream(self, child_id: str) -> Sequence[DomainEvent]:
        """All events for one child, ordered by sequence."""
        ...
