"""CostModel port: the cfo.ai integration seam (issue #55).

Costs are integer micro-USD to stay exact and canonicalizable. `None` means
"unknown", which ranks after every known estimate.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CostModel(Protocol):
    def estimate_cost_micro_usd(self, option_id: str) -> int | None: ...
