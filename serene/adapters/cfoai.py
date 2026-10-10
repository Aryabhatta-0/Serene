"""cfo.ai integration seam (issue #55).

cfo.ai is a hosted financial-modelling product reached over a remote MCP
server (https://api.cfo.ai/mcp, browser sign-in). Serene's later use is narrow:
unit economics for evidence acquisition, consulted *only* to break ties between
options that `serene.policies.acquisition` already ranks equal on safety,
evidence quality and information value.

At runtime the kernel never calls cfo.ai. Engineers maintain the economics model
in cfo.ai (via the MCP server registered in `.mcp.json`) and export per-option
unit costs into a reviewed table; `TableCostModel` serves that table.
"""

from __future__ import annotations

from collections.abc import Mapping


class TableCostModel:
    """`CostModel` backed by a reviewed, exported cost table (integer micro-USD)."""

    def __init__(self, costs: Mapping[str, int]) -> None:
        for option_id, cost in costs.items():
            if cost < 0:
                raise ValueError(f"negative cost for {option_id}")
        self._costs = dict(costs)

    def estimate_cost_micro_usd(self, option_id: str) -> int | None:
        return self._costs.get(option_id)
