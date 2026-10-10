"""The memory store contract used by the single-writer Memory Committer.

`MemoryRepository` (serene.ports.memory) stays the frozen, read-mostly port that
branch A reads through. The committer additionally needs a *two-phase* write so
the ledger and Git can never disagree: it prepares a commit object without
moving the branch, records MEMORY_PATCH_COMMITTED with that exact SHA, and only
then publishes (compare-and-set) the branch head. If the ledger refuses, the
prepared object is never published and memory is unchanged.

Dream and every other proposer receive a `ReadOnlyMemory` view, which has no
write method at all.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Protocol, runtime_checkable

from serene.domain.entities import MemoryPatch
from serene.ports.memory import CommitAuthorization, MemoryDocument

COMMITTER_NAME: Final = "Serene Memory Committer"
COMMITTER_EMAIL: Final = "memory-committer@example.org"
INIT_TRAILER: Final = "Serene-Init"


class MemoryConflict(RuntimeError):
    """The repository no longer matches the patch's base (stale base / pre-image)."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class StaleHead(RuntimeError):
    """The branch head moved between prepare and publish; nothing was published."""


@dataclass(frozen=True, slots=True)
class PreparedCommit:
    commit_sha: str
    parent_sha: str
    tree_sha: str
    path: str
    post_digest: str


@dataclass(frozen=True, slots=True)
class CommitRecord:
    sha: str
    parent: str | None
    author_email: str
    trailers: Mapping[str, str] = field(default_factory=dict)


@runtime_checkable
class MemoryReadView(Protocol):
    def read(self, path: str) -> MemoryDocument | None: ...

    def list_paths(self, prefix: str) -> Sequence[str]: ...

    def head(self) -> str: ...


@runtime_checkable
class MemoryStore(MemoryReadView, Protocol):
    def prepare_commit(
        self,
        patch: MemoryPatch,
        authorization: CommitAuthorization,
        *,
        trailers: Mapping[str, str],
        committed_at: datetime,
    ) -> PreparedCommit: ...

    def publish(self, prepared: PreparedCommit) -> None: ...

    def history(self) -> Sequence[CommitRecord]: ...

    def worktree_clean(self) -> bool: ...

    def has_commit(self, sha: str) -> bool: ...


class ReadOnlyMemory:
    """Read capability only. Handed to Dream, the Critic's callers and branch A retrieval."""

    __slots__ = ("_store",)

    def __init__(self, store: MemoryReadView) -> None:
        self._store = store

    def read(self, path: str) -> MemoryDocument | None:
        return self._store.read(path)

    def list_paths(self, prefix: str) -> Sequence[str]:
        return self._store.list_paths(prefix)

    def head(self) -> str:
        return self._store.head()
