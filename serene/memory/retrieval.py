"""Verified, read-only memory access for contextual retrieval (branch A reads here).

Reads fail closed if memory_repo does not match the ledger (audit findings).
A learning document is surfaced only while the ledger says the learning is
*effectively* ACTIVE right now; the document's own status text is never trusted
on its own, so a stale learning is never presented as active (issue #20), and
memory is never used as belief state (issue #29).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from serene.domain.entities import LearningStatus
from serene.memory.committer import MemoryIntegrityError, audit
from serene.memory.document import MemoryDoc, MemoryFormatError, parse
from serene.memory.store import MemoryStore
from serene.policies.learning import effective_status
from serene.ports.memory import MemoryDocument
from serene.projections.state import KernelState


@dataclass(frozen=True, slots=True)
class RetrievedLearning:
    path: str
    revision: str
    doc: MemoryDoc


def read_verified(store: MemoryStore, state: KernelState, path: str) -> MemoryDocument | None:
    findings = audit(store, state)
    if findings:
        raise MemoryIntegrityError(findings)
    return store.read(path)


def active_learnings(
    store: MemoryStore, state: KernelState, now: datetime
) -> list[RetrievedLearning]:
    findings = audit(store, state)
    if findings:
        raise MemoryIntegrityError(findings)
    out: list[RetrievedLearning] = []
    for prefix in ("learnings/", "routines/"):
        for path in store.list_paths(prefix):
            current = store.read(path)
            if current is None:
                continue
            try:
                doc = parse(current.content)
            except MemoryFormatError:
                continue
            record = state.learnings.get(doc.front.subject)
            if record is None or doc.front.status is not LearningStatus.ACTIVE:
                continue
            if effective_status(record, state, now) is not LearningStatus.ACTIVE:
                continue
            if doc.front.review_after != record.review_after:
                continue
            out.append(RetrievedLearning(path, current.revision, doc))
    return out
