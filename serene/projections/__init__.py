"""Rebuildable read-side projections derived from the immutable event ledger.

Projections are never the source of truth. They can be deleted and rebuilt by
deterministic replay; replaying the same ledger yields byte-identical state.
"""

from serene.projections.state import KernelState, apply_event, replay
from serene.projections.views import (
    PROJECTIONS,
    effective_learning_status,
    project,
    projection_digest,
    rebuild_projections,
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
