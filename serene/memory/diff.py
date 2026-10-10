"""Full-context unified diffs for memory patches.

The diff grammar is part of the authority contract the ledger's admission
re-checks, so it lives in `serene.policies.memory_format`; this module
re-exports it for the memory feature layer and the Git adapter.
"""

from __future__ import annotations

from serene.policies.memory_format import (
    DEV_NULL,
    DiffFormatError,
    ParsedDiff,
    full_diff,
    parse_full_diff,
)

__all__ = ["DEV_NULL", "DiffFormatError", "ParsedDiff", "full_diff", "parse_full_diff"]
