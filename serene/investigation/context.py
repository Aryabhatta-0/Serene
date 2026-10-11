"""Contextual retrieval over three separate layers (issues #11, #21).

    EXPERIENCE  what happened      raw evidence + structured observations (ledger)
    MEMORY      what we remember   memory_repo documents (MemoryRepository, read-only)
    BELIEF      what we believe    hypotheses / patterns / learnings (ledger projections)

The layers are never merged: a memory file can say anything, but it is only
ever presented as MEMORY, and belief comes exclusively from `KernelState`.
Retrieval is deterministic keyword/context-tag matching (no embeddings), so a
fixed ledger + memory snapshot always yields the same context and digest.

Only VERIFIED evidence exposes content. UNVERIFIED and REJECTED evidence is
listed by id and status only, so it can never enter trusted reasoning.
Caregiver disagreement is surfaced as separate accounts, never averaged and
never weighted.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Final

from serene.domain.canonical import canonical_digest, format_timestamp
from serene.domain.entities import Evidence, Hypothesis, Observation, Pattern
from serene.domain.events import AcquisitionMode
from serene.domain.values import VerificationStatus
from serene.evidence.micro_answer import MicroAnswerValue, decode_micro_answer
from serene.policies.investigation import active_hypotheses, requests_of
from serene.ports.memory import MemoryRepository
from serene.projections.state import KernelState, LifecycleStatus
from serene.projections.views import effective_learning_status

MEMORY_PREFIXES: Final = (
    "child/",
    "caregivers/",
    "routines/",
    "patterns/",
    "investigations/",
    "decisions/",
    "learnings/",
)
_WORD = re.compile(r"[a-z][a-z0-9]{3,}")
_STOP: Final = frozenset(
    {
        "this",
        "that",
        "with",
        "when",
        "what",
        "why",
        "they",
        "them",
        "their",
        "there",
        "have",
        "from",
        "into",
        "about",
        "were",
        "been",
        "after",
        "before",
        "again",
        "today",
        "very",
        "much",
        "does",
        "so",
    }
)


def _stem(word: str) -> str:
    """Tiny deterministic plural fold ("pickups" -> "pickup"); no NLP, no embeddings."""
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def terms_of(*texts: str) -> frozenset[str]:
    """Deterministic, lower-cased content words (>=4 chars, minus stopwords)."""
    out: set[str] = set()
    for text in texts:
        out |= {_stem(w) for w in _WORD.findall(text.casefold()) if w not in _STOP}
    return frozenset(out)


class Layer(StrEnum):
    EXPERIENCE = "EXPERIENCE"
    MEMORY = "MEMORY"
    BELIEF = "BELIEF"


class PredictionResult(StrEnum):
    CONFIRMED = "CONFIRMED"
    CONTRADICTED = "CONTRADICTED"
    UNTESTED = "UNTESTED"


@dataclass(frozen=True, slots=True)
class ExperienceItem:
    entity_id: str
    kind: str  # "evidence" | "observation"
    observer_kind: str
    observer_id: str
    occurred_at: datetime
    verification_status: VerificationStatus
    contexts: tuple[str, ...]
    content: str
    entity: Any
    layer: Layer = Layer.EXPERIENCE


@dataclass(frozen=True, slots=True)
class MemoryItem:
    path: str
    revision: str
    content_digest: str
    excerpt: str
    matched_terms: tuple[str, ...]
    layer: Layer = Layer.MEMORY


@dataclass(frozen=True, slots=True)
class BeliefItem:
    entity_id: str
    kind: str  # "pattern" | "hypothesis" | "learning"
    level: str
    status: str
    statement: str
    contexts: tuple[str, ...]
    investigation_id: str | None = None
    supporting_evidence_ids: tuple[str, ...] = ()
    counter_evidence_ids: tuple[str, ...] = ()
    competing_hypothesis_ids: tuple[str, ...] = ()
    known_confounders: tuple[str, ...] = ()
    prediction_results: tuple[tuple[str, PredictionResult], ...] = ()
    entity: Any = None
    layer: Layer = Layer.BELIEF


@dataclass(frozen=True, slots=True)
class ObserverAccount:
    observer_kind: str
    observer_id: str
    observation_id: str
    statement: str


@dataclass(frozen=True, slots=True)
class Disagreement:
    """Separate observer accounts of one occasion. No reliability, no average."""

    occasion: str
    contexts: tuple[str, ...]
    accounts: tuple[ObserverAccount, ...]
    diverges: bool


@dataclass(frozen=True, slots=True)
class InvestigationContext:
    child_id: str
    investigation_id: str | None
    question: str | None
    phase: str | None
    experience: tuple[ExperienceItem, ...]
    memory: tuple[MemoryItem, ...]
    belief: tuple[BeliefItem, ...]
    disagreements: tuple[Disagreement, ...]
    withheld: tuple[tuple[str, VerificationStatus], ...]
    requested_fields_so_far: frozenset[str] = field(default_factory=frozenset)
    digest: str = ""

    def visible_ids(self) -> frozenset[str]:
        return frozenset(
            [i.entity_id for i in self.experience] + [b.entity_id for b in self.belief]
        )

    def entity(self, entity_id: str) -> Any:
        for item in self.experience:
            if item.entity_id == entity_id:
                return item.entity
        for belief in self.belief:
            if belief.entity_id == entity_id:
                return belief.entity
        return None

    def live_hypotheses(self) -> tuple[BeliefItem, ...]:
        """Active hypotheses of this investigation not contradicted by a verified answer."""
        return tuple(
            b
            for b in self.belief
            if b.kind == "hypothesis"
            and b.status == LifecycleStatus.ACTIVE.value
            and b.investigation_id == self.investigation_id
            and PredictionResult.CONTRADICTED not in {r for _, r in b.prediction_results}
        )


class ContextRetriever:
    def __init__(
        self,
        memory: MemoryRepository | None = None,
        *,
        max_experience: int = 64,
        max_memory: int = 8,
        max_belief: int = 32,
        memory_excerpt_chars: int = 600,
    ) -> None:
        self._memory = memory
        self._max_experience = max_experience
        self._max_memory = max_memory
        self._max_belief = max_belief
        self._excerpt = memory_excerpt_chars

    # ------------------------------------------------------------------ public
    def retrieve(
        self,
        state: KernelState,
        *,
        child_id: str,
        investigation_id: str | None = None,
        focus_ids: Iterable[str] = (),
        now: datetime,
    ) -> InvestigationContext:
        focus = frozenset(focus_ids)
        question = None
        phase = None
        if investigation_id is not None and investigation_id in state.entities:
            question = state.entities[investigation_id].entity.question
            phase = state.investigation_phases[investigation_id].value
        belief = self._belief(state, investigation_id, now)
        terms = terms_of(question or "", *(b.statement for b in belief)) | frozenset(
            t for b in belief for t in b.contexts
        )
        experience, withheld = self._experience(state, terms, focus)
        memory = self._memory_items(terms)
        disagreements = disagreements_in(experience)
        already_requested = frozenset(
            f
            for record in (requests_of(investigation_id, state) if investigation_id else [])
            for f in record.request.requested_fields
        )
        context = InvestigationContext(
            child_id=child_id,
            investigation_id=investigation_id,
            question=question,
            phase=phase,
            experience=experience,
            memory=memory,
            belief=belief,
            disagreements=disagreements,
            withheld=withheld,
            requested_fields_so_far=already_requested,
        )
        return _with_digest(context)

    # ------------------------------------------------------------------ layers
    def _experience(
        self, state: KernelState, terms: frozenset[str], focus: frozenset[str]
    ) -> tuple[tuple[ExperienceItem, ...], tuple[tuple[str, VerificationStatus], ...]]:
        scored: list[tuple[int, ExperienceItem]] = []
        withheld: list[tuple[str, VerificationStatus]] = []
        for entity_id, record in state.entities.items():
            entity = record.entity
            if isinstance(entity, Evidence):
                if record.verification_status is not VerificationStatus.VERIFIED:
                    withheld.append((entity_id, record.verification_status))
                    continue
                item = ExperienceItem(
                    entity_id=entity_id,
                    kind="evidence",
                    observer_kind=entity.observer.kind.value,
                    observer_id=entity.observer.actor_id,
                    occurred_at=entity.captured_at,
                    verification_status=record.verification_status,
                    contexts=(),
                    content=entity.content,
                    entity=entity,
                )
                text = entity.content
            elif isinstance(entity, Observation) and record.status is LifecycleStatus.ACTIVE:
                item = ExperienceItem(
                    entity_id=entity_id,
                    kind="observation",
                    observer_kind=entity.observer.kind.value,
                    observer_id=entity.observer.actor_id,
                    occurred_at=entity.observed_at,
                    verification_status=record.verification_status,
                    contexts=entity.contexts,
                    content=entity.statement,
                    entity=entity,
                )
                text = entity.statement
            else:
                continue
            score = len(terms & (terms_of(text) | set(item.contexts)))
            if entity_id in focus:
                score += 1_000
            scored.append((score, item))
        scored.sort(key=lambda s: (-s[0], -s[1].occurred_at.timestamp(), s[1].entity_id))
        chosen = [item for _, item in scored[: self._max_experience]]
        chosen.sort(key=lambda i: (i.occurred_at, i.entity_id))
        return tuple(chosen), tuple(sorted(withheld))

    def _memory_items(self, terms: frozenset[str]) -> tuple[MemoryItem, ...]:
        if self._memory is None:
            return ()
        scored: list[tuple[int, MemoryItem]] = []
        for prefix in MEMORY_PREFIXES:
            for path in sorted(self._memory.list_paths(prefix)):
                document = self._memory.read(path)
                if document is None:
                    continue
                matched = tuple(sorted(terms & terms_of(document.content)))
                if not matched:
                    continue
                scored.append(
                    (
                        len(matched),
                        MemoryItem(
                            path=document.path,
                            revision=document.revision,
                            content_digest=document.content_digest,
                            excerpt=document.content[: self._excerpt],
                            matched_terms=matched,
                        ),
                    )
                )
        scored.sort(key=lambda s: (-s[0], s[1].path))
        return tuple(item for _, item in scored[: self._max_memory])

    def _belief(
        self, state: KernelState, investigation_id: str | None, now: datetime
    ) -> tuple[BeliefItem, ...]:
        predictions = prediction_results(state, investigation_id)
        items: list[BeliefItem] = []
        for entity_id, record in sorted(state.entities.items()):
            entity = record.entity
            if isinstance(entity, Hypothesis):
                level = state.hypothesis_levels[entity_id]
                items.append(
                    BeliefItem(
                        entity_id=entity_id,
                        kind="hypothesis",
                        level=level.name,
                        status=record.status.value,
                        statement=entity.statement,
                        contexts=entity.scope.contexts,
                        investigation_id=entity.investigation_id,
                        supporting_evidence_ids=entity.supporting_evidence_ids,
                        counter_evidence_ids=entity.counter_evidence_ids,
                        competing_hypothesis_ids=_competitors(entity, state),
                        known_confounders=entity.known_confounders,
                        prediction_results=tuple(sorted(predictions.get(entity_id, {}).items())),
                        entity=entity,
                    )
                )
            elif isinstance(entity, Pattern) and record.status is LifecycleStatus.ACTIVE:
                items.append(
                    BeliefItem(
                        entity_id=entity_id,
                        kind="pattern",
                        level=record.level.name if record.level is not None else "PATTERN",
                        status=record.status.value,
                        statement=entity.description,
                        contexts=entity.contexts,
                        entity=entity,
                    )
                )
        for learning_id, learning in sorted(state.learnings.items()):
            entity = state.entities[learning_id].entity
            items.append(
                BeliefItem(
                    entity_id=learning_id,
                    kind="learning",
                    level="CONTEXTUAL_LEARNING",
                    status=effective_learning_status(learning, now).value,
                    statement=entity.statement,
                    contexts=learning.contexts,
                    entity=entity,
                )
            )
        # Keep this investigation's hypotheses first; bound the rest deterministically.
        items.sort(
            key=lambda b: (
                0 if b.investigation_id == investigation_id and investigation_id else 1,
                b.kind,
                b.entity_id,
            )
        )
        return tuple(items[: self._max_belief])


def _competitors(hypothesis: Hypothesis, state: KernelState) -> tuple[str, ...]:
    """Declared competitors plus every other hypothesis of the same investigation."""
    siblings = set(state.investigation_hypotheses.get(hypothesis.investigation_id, []))
    siblings |= set(hypothesis.competing_hypothesis_ids)
    siblings.discard(hypothesis.hypothesis_id)
    return tuple(sorted(siblings))


def prediction_results(
    state: KernelState, investigation_id: str | None
) -> dict[str, dict[str, PredictionResult]]:
    """Compare each verified micro-answer with what every hypothesis predicted."""
    if investigation_id is None:
        return {}
    out: dict[str, dict[str, PredictionResult]] = {}
    for record in requests_of(investigation_id, state):
        if record.request.acquisition_mode is not AcquisitionMode.ASK_PARENT:
            continue
        for evidence_id in record.evidence_ids:
            if state.verification_of(evidence_id) is not VerificationStatus.VERIFIED:
                continue
            answer = decode_micro_answer(state.entities[evidence_id].entity.content)
            if answer is None:
                continue
            for prediction in record.request.predictions:
                if answer.answer is MicroAnswerValue.UNSURE:
                    result = PredictionResult.UNTESTED
                elif answer.answer.value == prediction.expected.value:
                    result = PredictionResult.CONFIRMED
                else:
                    result = PredictionResult.CONTRADICTED
                out.setdefault(prediction.hypothesis_id, {})[record.request.request_id] = result
    return out


def _normalize(statement: str) -> str:
    return " ".join(statement.casefold().split())


def disagreements_in(experience: Iterable[ExperienceItem]) -> tuple[Disagreement, ...]:
    """Group observations of the same day and context by observer (issue #21)."""
    groups: dict[tuple[str, str], list[ExperienceItem]] = {}
    for item in experience:
        if item.kind != "observation":
            continue
        day = format_timestamp(item.occurred_at)[:10]
        for tag in item.contexts or ("unspecified",):
            groups.setdefault((day, tag), []).append(item)
    seen: set[tuple[str, ...]] = set()
    out: list[Disagreement] = []
    for (day, _tag), items in sorted(groups.items()):
        observers = {i.observer_id for i in items}
        if len(observers) < 2:
            continue
        ids = tuple(sorted(i.entity_id for i in items))
        if ids in seen:
            continue
        seen.add(ids)
        accounts = tuple(
            ObserverAccount(
                observer_kind=i.observer_kind,
                observer_id=i.observer_id,
                observation_id=i.entity_id,
                statement=i.content,
            )
            for i in sorted(items, key=lambda i: (i.observer_id, i.entity_id))
        )
        shared = sorted(set.intersection(*(set(i.contexts) for i in items))) if items else []
        out.append(
            Disagreement(
                occasion=day,
                contexts=tuple(shared),
                accounts=accounts,
                diverges=len({_normalize(a.statement) for a in accounts}) > 1,
            )
        )
    return tuple(out)


def _with_digest(context: InvestigationContext) -> InvestigationContext:
    snapshot = {
        "child_id": context.child_id,
        "investigation_id": context.investigation_id,
        "phase": context.phase,
        "experience": [[i.entity_id, i.verification_status.value] for i in context.experience],
        "memory": [[m.path, m.revision, m.content_digest] for m in context.memory],
        "belief": [[b.entity_id, b.level, b.status] for b in context.belief],
        "withheld": [[e, s.value] for e, s in context.withheld],
        "disagreements": [[a.observation_id for a in d.accounts] for d in context.disagreements],
    }
    return InvestigationContext(
        child_id=context.child_id,
        investigation_id=context.investigation_id,
        question=context.question,
        phase=context.phase,
        experience=context.experience,
        memory=context.memory,
        belief=context.belief,
        disagreements=context.disagreements,
        withheld=context.withheld,
        requested_fields_so_far=context.requested_fields_so_far,
        digest=canonical_digest(snapshot),
    )


def live_hypothesis_ids(state: KernelState, investigation_id: str) -> list[str]:
    """Active hypotheses minus those a verified micro-answer contradicted."""
    contradicted = {
        hyp
        for hyp, results in prediction_results(state, investigation_id).items()
        if PredictionResult.CONTRADICTED in results.values()
    }
    return [h for h in active_hypotheses(investigation_id, state) if h not in contradicted]
