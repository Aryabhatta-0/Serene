"""Memory publication: a pure ledger review plus an explicitly pinned Git input.

The Git input is the last MEMORY_PATCH_COMMITTED SHA in ledger order. Before
the first commit, the document set is explicitly empty (zero SHA sentinel).
An unavailable commit refuses the entire publish; existing rows stay intact.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from serene.domain.canonical import canonical_json
from serene.ports.memory import MemoryDocument
from serene.projections.state import KernelState


class SnapshotRead(Protocol):
    def head(self) -> str: ...

    def read(self, path: str) -> MemoryDocument | None: ...

    def list_paths(self, prefix: str) -> Sequence[str]: ...


MemorySnapshot = Callable[[str, str], SnapshotRead]
EMPTY_REVISION = "0" * 40


class EmptyMemory:
    def head(self) -> str:
        return EMPTY_REVISION

    def read(self, path: str) -> MemoryDocument | None:
        return None

    def list_paths(self, prefix: str) -> Sequence[str]:
        return ()


def memory_revision(state: KernelState) -> str | None:
    # Dict insertion order is the replay's commit-event order, never wall time.
    return next(reversed(state.memory_commits.values()), None)


# Derived text can itself contain identifiers or credentials. Refuse, never
# silently redact a diff or reason (which would misrepresent the review).
_PRIVATE = re.compile(
    r"(?:chd_|act_|person_|parent_|caregiver_)[A-Za-z0-9_-]+"
    r"|(?:sk-|gh[pousr]_|github_pat_|AKIA|ASIA|xox[baprs]-)[A-Za-z0-9_-]{8,}"
    r"|eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_.-]+"
    r"|\d{8,10}:AA[A-Za-z0-9_-]+"
    r"|(?:chat_id|channel_id|private_channel|password|credential|api_key|access_token)"
    r"|(?:Bearer\s+|postgres(?:ql)?://|-----BEGIN .*PRIVATE KEY)"
    r"|(?:t\.me/|discord\.com/channels/|slack\.com/archives/)",
    re.IGNORECASE,
)


class MemoryPublicationError(RuntimeError):
    """Code-only error: never includes document text or identifiers."""


def privacy_checked(payload: dict[str, Any]) -> dict[str, Any]:
    if _PRIVATE.search(canonical_json(payload).decode("utf-8")):
        raise MemoryPublicationError("MEMORY_PRIVATE_PAYLOAD")
    return payload


def memory_review(state: KernelState) -> dict[str, Any]:
    """Ledger-only view. No Git reads, including on historical replay."""
    if not state.memory_patches and not state.dream_stages:
        return {}
    from serene.memory.view import build_memory_dream_view

    view = build_memory_dream_view(state, EmptyMemory()).model_dump(mode="json")
    view["memory_head"] = memory_revision(state) or EMPTY_REVISION
    return privacy_checked(view)


def memory_dream(state: KernelState, snapshot: MemorySnapshot) -> dict[str, Any]:
    from serene.memory.view import build_memory_dream_view

    review = memory_review(state)
    if not review:
        return {}
    revision = memory_revision(state)
    if revision is None:
        return review
    assert state.child_id is not None
    memory = snapshot(state.child_id, revision)
    if memory.head() != revision:
        raise MemoryPublicationError("MEMORY_REVISION_MISMATCH")
    view = build_memory_dream_view(state, memory).model_dump(mode="json")
    # Document bytes stay pinned. Learning lifecycle is the replayable ledger's
    # current status, evaluated at ledger time rather than the rebuild clock.
    from serene.projections.views import effective_learning_status

    for item in view["memories"]:
        learning = state.learnings.get(item["subject"])
        if learning is not None and state.last_recorded_at is not None:
            item["status"] = effective_learning_status(learning, state.last_recorded_at).value
    return privacy_checked(view)
