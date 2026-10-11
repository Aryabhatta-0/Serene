"""Read view of consolidated memory and Dream runs for the review surface (issue #36).

`build_memory_dream_view` is a pure function of `KernelState` and a read-only
memory view. It carries no authority: it reports what the ledger already
decided (proposed, reviewed, committed or rejected) and what `memory_repo`
currently holds, so a parent can see what Dreaming proposed and why anything
was refused.

Privacy: the view holds typed entity ids, memory text and machine reason codes
only. There is no child id, no actor id (only the actor's *kind*), and no
evidence content; a memory's provenance is its lineage down to raw-evidence ids.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal, Self

from pydantic import Field, model_validator

from serene.domain.base import (
    EntityId,
    KernelModel,
    MemoryPatchId,
    ReasonCode,
    Sha256Hex,
    ShortText,
    Tag,
    UtcDatetime,
    id_prefix,
)
from serene.domain.entities import LearningStatus, MemoryOperation, MemoryPatch, MemoryPath
from serene.domain.events import DreamStage, MemoryCheck
from serene.domain.values import (
    ActorKind,
    DerivationMethod,
    EpistemicLevel,
    ModelRef,
    VerificationStatus,
)
from serene.lineage.provenance import trace_lineage
from serene.memory.document import DIRECTORY_KIND, MemoryFormatError, MemoryKind, parse
from serene.memory.store import MemoryReadView
from serene.projections.state import KernelState

VIEW_VERSION: Final = "memory-dream-view/1"
_GitSha = str  # 40-hex commit id; checked by the git adapter, carried as text here


class PatchStatus(StrEnum):
    PROPOSED = "PROPOSED"  # awaiting the committer
    COMMITTED = "COMMITTED"
    REJECTED = "REJECTED"


class LineageNodeView(KernelModel):
    entity_id: EntityId
    level: EpistemicLevel | None
    verification_status: VerificationStatus
    parents: tuple[EntityId, ...]


class LineageView(KernelModel):
    """`trace_lineage` of one subject: every node down to raw evidence, and any gaps."""

    root: EntityId
    nodes: tuple[LineageNodeView, ...]
    raw_evidence: tuple[EntityId, ...]
    missing: tuple[EntityId, ...]


class PatchOrigin(KernelModel):
    """A patch's provenance without the actor id."""

    actor_kind: ActorKind
    method: DerivationMethod
    model: ModelRef | None
    created_at: UtcDatetime
    derived_from: tuple[EntityId, ...]
    source_ids: tuple[EntityId, ...]


class PatchReviewView(KernelModel):
    passed: bool
    checks_passed: tuple[MemoryCheck, ...]
    reason_codes: tuple[ReasonCode, ...] = Field(min_length=1)
    recorded_at: UtcDatetime | None


class PatchView(KernelModel):
    patch_id: MemoryPatchId
    target_path: MemoryPath
    operation: MemoryOperation
    required_level: EpistemicLevel
    rationale: ShortText
    diff: str = Field(min_length=1, max_length=20000)
    origin: PatchOrigin
    status: PatchStatus
    dream_run_id: Sha256Hex | None
    review: PatchReviewView | None
    decided_at: UtcDatetime | None
    rejection_reasons: tuple[ReasonCode, ...]
    commit_sha: _GitSha | None

    @model_validator(mode="after")
    def _decision_is_explained(self) -> Self:
        if self.status is PatchStatus.REJECTED and not self.rejection_reasons:
            raise ValueError("a rejected patch must carry its rejection reasons")
        if self.status is not PatchStatus.REJECTED and self.rejection_reasons:
            raise ValueError("only a rejected patch carries rejection reasons")
        if (self.status is PatchStatus.COMMITTED) != (self.commit_sha is not None):
            raise ValueError("a commit sha is present exactly when the patch is committed")
        if (self.status is PatchStatus.PROPOSED) != (self.decided_at is None):
            raise ValueError("a decided patch has a decision time; a pending one does not")
        return self


class DreamStageView(KernelModel):
    stage: DreamStage
    recorded_at: UtcDatetime
    item_count: int = Field(ge=0, le=256)
    reason_codes: tuple[ReasonCode, ...]


class DreamRunView(KernelModel):
    run_id: Sha256Hex
    started_at: UtcDatetime
    stages: tuple[DreamStageView, ...] = Field(min_length=1)
    complete: bool
    proposed: tuple[MemoryPatchId, ...]


class MemoryItemView(KernelModel):
    path: ShortText
    kind: MemoryKind
    title: ShortText
    body: str = Field(min_length=1, max_length=4000)
    subject: EntityId
    level: EpistemicLevel | None
    status: LearningStatus
    scope: tuple[Tag, ...]
    valid_from: UtcDatetime | None
    review_after: UtcDatetime | None
    sources: tuple[EntityId, ...] = Field(min_length=1)
    counterevidence: tuple[EntityId, ...]
    revision: _GitSha
    written_by: MemoryPatchId | None
    lineage: LineageView


class UnreadableMemory(KernelModel):
    """A file in memory_repo that does not parse. Shown, never repaired or hidden."""

    path: ShortText
    revision: _GitSha


class MemoryDreamView(KernelModel):
    version: Literal["memory-dream-view/1"] = VIEW_VERSION
    ledger_head: Sha256Hex
    memory_head: _GitSha
    memories: tuple[MemoryItemView, ...]
    unreadable: tuple[UnreadableMemory, ...]
    dream_runs: tuple[DreamRunView, ...]
    patches: tuple[PatchView, ...]

    @model_validator(mode="after")
    def _references_resolve(self) -> Self:
        patches = {p.patch_id: p for p in self.patches}
        for item in self.memories:
            if item.written_by is not None and (
                item.written_by not in patches
                or patches[item.written_by].status is not PatchStatus.COMMITTED
            ):
                raise ValueError(f"memory {item.path} names a patch that was not committed")
            if item.written_by is not None and patches[item.written_by].commit_sha != item.revision:
                raise ValueError(f"memory {item.path} names a patch that did not write it")
        for run in self.dream_runs:
            for patch_id in run.proposed:
                if patch_id not in patches:
                    raise ValueError(f"dream run proposes unknown patch {patch_id}")
        return self


def _lineage(subject: str, state: KernelState) -> LineageView:
    trace = trace_lineage(subject, state)
    return LineageView(
        root=trace.root,
        nodes=tuple(
            LineageNodeView(
                entity_id=n.entity_id,
                level=n.level,
                verification_status=n.verification_status,
                parents=n.parents,
            )
            for n in trace.nodes
        ),
        raw_evidence=trace.raw_evidence,
        missing=trace.missing,
    )


def _runs(
    state: KernelState, position: dict[str, int]
) -> tuple[tuple[DreamRunView, ...], dict[str, str]]:
    ordered: list[tuple[int, DreamRunView]] = []
    proposed_by: dict[str, str] = {}
    for run_id, records in state.dream_stages.items():
        proposed: tuple[str, ...] = ()
        for record in records:
            if record.stage is DreamStage.PROPOSE_PATCH:
                proposed = tuple(i for i in record.input_ids if id_prefix(i) == "mpt")
        for patch_id in proposed:
            proposed_by[patch_id] = run_id
        ordered.append(
            (
                position[records[0].event_id],
                DreamRunView(
                    run_id=run_id,
                    started_at=records[0].recorded_at,
                    stages=tuple(
                        DreamStageView(
                            stage=r.stage,
                            recorded_at=r.recorded_at,
                            item_count=r.item_count,
                            reason_codes=r.reason_codes,
                        )
                        for r in records
                    ),
                    complete=records[-1].stage is DreamStage.PROPOSE_PATCH,
                    proposed=proposed,
                ),
            )
        )
    ordered.sort(key=lambda pair: pair[0], reverse=True)  # newest first, in ledger order
    return tuple(run for _, run in ordered), proposed_by


def _patch(patch: MemoryPatch, state: KernelState, run_id: str | None) -> PatchView:
    patch_id = patch.patch_id
    review = state.memory_reviews.get(patch_id)
    decision = state.memory_decisions.get(patch_id)
    status = PatchStatus(state.memory_patches[patch_id])
    prov = patch.provenance
    return PatchView(
        patch_id=patch_id,
        target_path=patch.target_path,
        operation=patch.operation,
        required_level=patch.required_level,
        rationale=patch.rationale,
        diff=patch.diff,
        origin=PatchOrigin(
            actor_kind=prov.created_by.kind,
            method=prov.method,
            model=prov.model,
            created_at=prov.created_at,
            derived_from=prov.derived_from,
            source_ids=prov.source_ids,
        ),
        status=status,
        dream_run_id=run_id,
        review=(
            None
            if review is None
            else PatchReviewView(
                passed=review.passed,
                checks_passed=tuple(MemoryCheck(c) for c in review.checks_passed),
                reason_codes=review.reason_codes,
                recorded_at=review.recorded_at,
            )
        ),
        decided_at=None if decision is None else decision.recorded_at,
        rejection_reasons=(
            decision.reason_codes if decision is not None and not decision.committed else ()
        ),
        commit_sha=state.memory_commits.get(patch_id),
    )


def build_memory_dream_view(state: KernelState, memory: MemoryReadView) -> MemoryDreamView:
    # Ledger order, not timestamps: events recorded in the same instant stay ordered.
    position = {event_id: i for i, event_id in enumerate(state.event_ids)}
    runs, proposed_by = _runs(state, position)
    patch_records = sorted(
        (r for r in state.entities.values() if r.kind == "mpt"),
        key=lambda r: position[r.introduced_by],
    )
    patches = tuple(_patch(r.entity, state, proposed_by.get(r.entity_id)) for r in patch_records)

    written_by = {sha: patch_id for patch_id, sha in state.memory_commits.items()}
    memories: list[MemoryItemView] = []
    unreadable: list[UnreadableMemory] = []
    paths = sorted(p for d in DIRECTORY_KIND for p in memory.list_paths(f"{d}/"))
    for path in paths:
        document = memory.read(path)
        if document is None:
            continue
        try:
            doc = parse(document.content)
        except MemoryFormatError:
            unreadable.append(UnreadableMemory(path=path, revision=document.revision))
            continue
        front = doc.front
        memories.append(
            MemoryItemView(
                path=path,
                kind=front.kind,
                title=doc.title,
                body=doc.body,
                subject=front.subject,
                level=front.level,
                status=front.status,
                scope=front.scope,
                valid_from=front.valid_from,
                review_after=front.review_after,
                sources=front.sources,
                counterevidence=front.counterevidence,
                revision=document.revision,
                written_by=written_by.get(document.revision),
                lineage=_lineage(front.subject, state),
            )
        )
    return MemoryDreamView(
        ledger_head=state.last_event_hash,
        memory_head=memory.head(),
        memories=tuple(memories),
        unreadable=tuple(unreadable),
        dream_runs=runs,
        patches=patches,
    )
