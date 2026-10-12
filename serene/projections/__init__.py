"""Rebuildable read-side projections derived from the immutable event ledger.

Projections are never the source of truth. They can be deleted and rebuilt by
deterministic replay; replaying the same ledger yields byte-identical state.

`state` is the low-level fold and is imported eagerly. The views sit above the
policies (the `investigations` view reads `serene.policies.investigation`, which
reads `state`), so they load on first attribute access; importing
`serene.projections.state` must never pull the views in.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from serene.projections.state import KernelState, apply_event, replay

if TYPE_CHECKING:
    from serene.projections.views import (
        PROJECTIONS,
        effective_learning_status,
        project,
        projection_digest,
        rebuild_projections,
    )

_VIEW_EXPORTS = frozenset(
    {
        "PROJECTIONS",
        "effective_learning_status",
        "project",
        "projection_digest",
        "rebuild_projections",
    }
)

__all__ = [
    "PROJECTIONS",
    "KernelState",
    "apply_event",
    "effective_learning_status",
    "project",
    "projection_digest",
    "rebuild_projections",
    "replay",
]


def __getattr__(name: str) -> Any:
    if name in _VIEW_EXPORTS:
        return getattr(importlib.import_module("serene.projections.views"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
