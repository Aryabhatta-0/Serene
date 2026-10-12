"""Explicit Git input for production Memory/Dream publication and backfill."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from serene.adapters.git_memory import GitError, GitMemoryRepository
from serene.projections.memory import (
    MemoryPublicationError,
    MemorySnapshot,
    SnapshotRead,
    memory_dream,
)
from serene.projections.state import KernelState
from serene.projections.views import project


def configured_snapshot(child_id: str, revision: str) -> SnapshotRead:
    """Backend-only repo root, one repository per child; never shared HEAD."""
    root = os.environ.get("SERENE_MEMORY_REPO_PATH")
    if not root or not re.fullmatch(r"chd_[0-9a-f]{32}", child_id):
        raise MemoryPublicationError("MEMORY_REPOSITORY_UNAVAILABLE")
    try:
        return GitMemoryRepository(Path(root) / child_id).at_revision(revision)
    except GitError as exc:
        raise MemoryPublicationError("MEMORY_REVISION_UNAVAILABLE") from exc


def publishable_projections(
    state: KernelState, snapshot: MemorySnapshot = configured_snapshot
) -> dict[str, dict[str, Any]]:
    projections = project(state)
    if state.memory_patches or state.dream_stages:
        projections["memory_dream"] = memory_dream(state, snapshot)
    return projections
