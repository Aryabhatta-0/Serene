"""MemoryRepository port: Git + Markdown durable memory (issues #28, #32).

Reads are open to the kernel; writes happen only through `commit`, which the
single-writer Memory Committer calls with a ledger-backed authorization.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from serene.domain.base import EventId, KernelModel, MemoryPatchId, Sha256Hex
from serene.domain.entities import MemoryPatch, MemoryPath


class MemoryDocument(KernelModel):
    path: MemoryPath
    revision: str
    content: str
    content_digest: Sha256Hex


class CommitAuthorization(KernelModel):
    """Issued from ledger state (MEMORY_PATCH_PROPOSED + gate decision), never by a model."""

    patch_id: MemoryPatchId
    proposal_event_id: EventId
    ledger_head: Sha256Hex


class CommitReceipt(KernelModel):
    patch_id: MemoryPatchId
    commit_sha: str


@runtime_checkable
class MemoryRepository(Protocol):
    def read(self, path: str) -> MemoryDocument | None: ...

    def list_paths(self, prefix: str) -> Sequence[str]: ...

    def commit(self, patch: MemoryPatch, authorization: CommitAuthorization) -> CommitReceipt: ...
