"""Dream: consolidate recent experience into *proposed* memory patches (issue #30).

    ORIENT       collect recent experiences from the ledger
    CONSOLIDATE  choose the subjects whose memory documents may need (re)writing
    REFLECT      the Dreamer drafts a title and body per subject (may be a model)
    CHALLENGE    gather every ledger counterevidence for each draft subject
    VERIFY       fill every authority-bearing field from the ledger, never the Dreamer
    PROPOSE_PATCH  emit MEMORY_PATCH_PROPOSED with a full-context diff

Each stage is recorded as MEMORY_DREAM_STAGE_RECORDED (admission enforces order
and that every input is a real ledger entity). The pipeline holds a read-only
memory view and no committer: Dream cannot write memory. Authority comes later
and independently - the deterministic Critic reviews, the Memory Committer
commits or rejects (serene.memory.consolidation).

The Dreamer contributes words only. Subject identity is checked against the
ledger; level, status, scope, validity, sources and counterevidence are computed
by code; the directory's required level is fixed by `serene.memory.rules`.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Protocol, runtime_checkable

from pydantic import ValidationError

from serene.domain.base import new_id
from serene.domain.canonical import canonical_digest
from serene.domain.entities import LearningStatus, MemoryOperation, MemoryPatch
from serene.domain.events import (
    DomainEvent,
    DreamStage,
    EventDraft,
    EventType,
    MemoryDreamStageRecorded,
    MemoryPatchProposed,
)
from serene.domain.values import (
    ActorKind,
    ActorRef,
    DerivationMethod,
    ModelRef,
    Provenance,
    SourceKind,
    SourceRef,
    VerificationStatus,
)
from serene.ledger.service import AdmissionRejected, EventLedger
from serene.lineage.provenance import raw_sources_of
from serene.memory.critic import expected_front, subject_counterevidence
from serene.memory.diff import full_diff
from serene.memory.document import MemoryDoc, MemoryFormatError, parse, render
from serene.memory.rules import required_level_for
from serene.memory.store import MemoryReadView, ReadOnlyMemory
from serene.policies.learning import effective_status
from serene.ports.clock import Clock
from serene.projections.state import KernelState

DREAM_VERSION: Final = "dream/1"
EXPERIENCE_KINDS: Final = frozenset({"obs", "pat", "hyp", "out", "lrn"})
_PATH = re.compile(
    r"^(child|caregivers|routines|patterns|investigations|decisions|learnings)"
    r"/[a-z0-9][a-z0-9_\-]{0,63}\.md$"
)


@dataclass(frozen=True, slots=True)
class DreamDraft:
    """What a Dreamer may contribute: which subject, where, and the prose."""

    subject_id: str
    target_path: str
    title: str
    body: str


@dataclass(frozen=True, slots=True)
class DreamContext:
    child_id: str
    now: datetime
    state: KernelState
    experiences: tuple[str, ...]
    candidates: tuple[str, ...]
    memory: ReadOnlyMemory


@runtime_checkable
class Dreamer(Protocol):
    actor: ActorRef
    model: ModelRef | None

    def reflect(self, context: DreamContext) -> Sequence[DreamDraft]: ...


def _slug(text: str, subject: str) -> str:
    words = "-".join(re.findall(r"[a-z0-9]+", text.lower())[:6])[:48].strip("-")
    return f"{words}-{subject[4:12]}" if words else subject[4:12]


class TemplateDreamer:
    """Deterministic Dreamer: restates ledger statements. No model, no invention."""

    model: ModelRef | None = None

    def __init__(self, actor: ActorRef) -> None:
        if actor.kind is not ActorKind.SYSTEM:
            raise ValueError("the template dreamer speaks as SYSTEM")
        self.actor = actor

    def reflect(self, context: DreamContext) -> Sequence[DreamDraft]:
        drafts = []
        for subject in context.candidates:
            entity = context.state.entities[subject].entity
            if subject.startswith("lrn_"):
                statement = entity.statement
                drafts.append(
                    DreamDraft(
                        subject,
                        f"learnings/{_slug(statement, subject)}.md",
                        statement[:120],
                        f"{statement}\n\nApplies only in: {', '.join(entity.scope.contexts)}.\n"
                        "Review with the parent at the review date or when the context changes.",
                    )
                )
            elif subject.startswith("pat_"):
                drafts.append(
                    DreamDraft(
                        subject,
                        f"patterns/{_slug(entity.description, subject)}.md",
                        entity.description[:120],
                        f"{entity.description}\n\nA regularity across observations, not a cause.",
                    )
                )
        return drafts


@dataclass(slots=True)
class DreamReport:
    run_id: str
    stage_events: list[DomainEvent] = field(default_factory=list)
    proposed: list[str] = field(default_factory=list)
    refused: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)


class DreamPipeline:
    def __init__(
        self,
        ledger: EventLedger,
        memory: MemoryReadView,
        dreamer: Dreamer,
        clock: Clock,
        *,
        system: ActorRef,
        new_entity_id: Callable[[str], str] = new_id,
    ) -> None:
        if system.kind is not ActorKind.SYSTEM:
            raise ValueError("dream stages are recorded by SYSTEM")
        self._ledger = ledger
        self._memory = ReadOnlyMemory(memory)  # read capability only, by construction
        self._dreamer = dreamer
        self._clock = clock
        self._system = system
        self._new_id = new_entity_id

    # ------------------------------------------------------------------ helpers
    def _draft(
        self,
        state: KernelState,
        event_type: EventType,
        actor: ActorRef,
        payload: object,
        *,
        status: VerificationStatus = VerificationStatus.NOT_APPLICABLE,
        derived_from: tuple[str, ...] = (),
    ) -> EventDraft:
        assert state.child_id is not None
        return EventDraft(
            event_type=event_type,
            child_id=state.child_id,
            source=SourceRef(kind=SourceKind.KERNEL, source_id=self._new_id("src")),
            actor=actor,
            occurred_at=self._clock.now(),
            derived_from=derived_from,
            verification_status=status,
            payload=payload,  # type: ignore[arg-type]
        )

    def _stage(
        self,
        report: DreamReport,
        child_id: str,
        stage: DreamStage,
        inputs: Sequence[str],
        output: object,
        reasons: Sequence[str] = (),
    ) -> DomainEvent:
        state = self._ledger.replay_events(child_id)
        event = self._ledger.append_event(
            self._draft(
                state,
                EventType.MEMORY_DREAM_STAGE_RECORDED,
                self._system,
                MemoryDreamStageRecorded(
                    dream_run_id=report.run_id,
                    stage=stage,
                    input_ids=tuple(inputs)[:256],
                    output_digest=canonical_digest(output),
                    item_count=min(len(inputs), 256),
                    reason_codes=tuple(dict.fromkeys(reasons))[:64],
                ),
                derived_from=tuple(e.event_id for e in report.stage_events[-1:]),
            )
        )
        report.stage_events.append(event)
        return event

    # ------------------------------------------------------------------ run
    def run(self, child_id: str, *, since: datetime | None = None) -> DreamReport:
        state = self._ledger.replay_events(child_id)
        now = self._clock.now()
        run_id = canonical_digest(
            {
                "version": DREAM_VERSION,
                "child_id": child_id,
                "ledger_head": state.last_event_hash,
                "since": since,
                "dreamer": self._dreamer.actor,
                "memory_head": self._memory.head(),
            }
        )
        report = DreamReport(run_id=run_id)

        # ORIENT --------------------------------------------------------------
        experiences = tuple(
            sorted(
                eid
                for eid, rec in state.entities.items()
                if rec.kind in EXPERIENCE_KINDS
                and (
                    since is None or (rec.introduced_at is not None and rec.introduced_at >= since)
                )
            )
        )
        self._stage(report, child_id, DreamStage.ORIENT, experiences, experiences)

        # CONSOLIDATE ---------------------------------------------------------
        documented = self._documented_subjects()
        candidates: list[str] = []
        for lrn_id, record in sorted(state.learnings.items()):
            # Active learnings may be written; documented ones may need withdrawing.
            active = effective_status(record, state, now) is LearningStatus.ACTIVE
            if active or lrn_id in documented:
                candidates.append(lrn_id)
        candidates += [e for e in experiences if e.startswith("pat_")]
        self._stage(report, child_id, DreamStage.CONSOLIDATE, candidates, candidates)

        # REFLECT -------------------------------------------------------------
        context = DreamContext(child_id, now, state, experiences, tuple(candidates), self._memory)
        drafts: list[DreamDraft] = []
        dropped: list[str] = []
        for draft in self._dreamer.reflect(context):
            if draft.subject_id not in state.entities:
                dropped.append("DROPPED_UNKNOWN_SUBJECT")
            elif not _PATH.match(draft.target_path):
                dropped.append("DROPPED_INVALID_PATH")
            else:
                drafts.append(draft)
        report.dropped = dropped
        self._stage(
            report,
            child_id,
            DreamStage.REFLECT,
            [d.subject_id for d in drafts],
            [(d.subject_id, d.target_path, d.title, d.body) for d in drafts],
            dropped,
        )

        # CHALLENGE -----------------------------------------------------------
        counter = {d.subject_id: subject_counterevidence(d.subject_id, state) for d in drafts}
        self._stage(
            report,
            child_id,
            DreamStage.CHALLENGE,
            sorted(counter),
            counter,
            ["COUNTEREVIDENCE_FOUND"] if any(counter.values()) else [],
        )

        # VERIFY --------------------------------------------------------------
        documents: list[tuple[DreamDraft, MemoryDoc, str]] = []
        unfit: list[str] = []
        for draft in drafts:
            try:
                front = expected_front(draft.subject_id, draft.target_path, state, now)
                doc = MemoryDoc(front=front, title=draft.title, body=draft.body)
            except (ValidationError, KeyError, ValueError):
                unfit.append("DROPPED_UNRENDERABLE")
                continue
            documents.append((draft, doc, render(doc)))
        self._stage(
            report,
            child_id,
            DreamStage.VERIFY,
            [d.subject_id for d, _, _ in documents],
            [text for _, _, text in documents],
            unfit,
        )

        # PROPOSE_PATCH ---------------------------------------------------------
        verify_event = report.stage_events[-1].event_id
        refusals: list[str] = []
        for draft, doc, text in documents:
            state = self._ledger.replay_events(child_id)
            current = self._memory.read(draft.target_path)
            if current is not None and current.content == text:
                report.unchanged.append(draft.target_path)
                continue
            withdrawn = doc.front.status is not LearningStatus.ACTIVE
            if current is None and withdrawn:
                report.unchanged.append(draft.target_path)  # nothing to withdraw yet
                continue
            operation = (
                MemoryOperation.CREATE
                if current is None
                else (MemoryOperation.DEPRECATE if withdrawn else MemoryOperation.UPDATE)
            )
            patch = self._patch(state, draft, text, current, operation, run_id)
            try:
                self._ledger.append_event(
                    self._draft(
                        state,
                        EventType.MEMORY_PATCH_PROPOSED,
                        self._dreamer.actor,
                        MemoryPatchProposed(patch=patch),
                        status=VerificationStatus.UNVERIFIED,
                        derived_from=(state.entities[draft.subject_id].introduced_by, verify_event),
                    )
                )
                report.proposed.append(patch.patch_id)
            except AdmissionRejected as exc:
                report.refused.append((draft.target_path, exc.reason_codes))
                refusals += [f"PROPOSAL_REFUSED:{r.split(':', 1)[0]}" for r in exc.reason_codes]
        self._stage(
            report, child_id, DreamStage.PROPOSE_PATCH, report.proposed, report.proposed, refusals
        )
        return report

    def _documented_subjects(self) -> set[str]:
        subjects: set[str] = set()
        for prefix in ("learnings/", "routines/", "patterns/", "child/", "caregivers/"):
            for path in self._memory.list_paths(prefix):
                current = self._memory.read(path)
                if current is None:
                    continue
                try:
                    subjects.add(parse(current.content).front.subject)
                except MemoryFormatError:
                    continue
        return subjects

    def _patch(
        self,
        state: KernelState,
        draft: DreamDraft,
        text: str,
        current: object,
        operation: MemoryOperation,
        run_id: str,
    ) -> MemoryPatch:
        model = self._dreamer.model
        method = (
            DerivationMethod.MODEL_INFERENCE
            if model is not None
            else DerivationMethod.DETERMINISTIC_RULE
        )
        base = getattr(current, "revision", None)
        old = getattr(current, "content", None)
        assert state.child_id is not None
        return MemoryPatch(
            child_id=state.child_id,
            provenance=Provenance(
                created_by=self._dreamer.actor,
                created_at=self._clock.now(),
                method=method,
                model=model,
                derived_from=(draft.subject_id,),
                source_ids=tuple(sorted(raw_sources_of(draft.subject_id, state))),
            ),
            patch_id=self._new_id("mpt"),
            target_path=draft.target_path,
            operation=operation,
            base_revision=base,
            diff=full_diff(draft.target_path, old, text),
            rationale=f"Dream {run_id[:12]}: consolidate {draft.subject_id}",
            required_level=required_level_for(draft.target_path, operation),
        )
