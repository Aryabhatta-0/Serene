"""ObservabilitySink port. Telemetry is advisory and must never affect correctness."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

AttributeValue = str | int | bool


@runtime_checkable
class ObservabilitySink(Protocol):
    def emit(self, name: str, attributes: Mapping[str, AttributeValue]) -> None:
        """Record one span/event. Callers pass only already-redacted attributes."""
        ...
