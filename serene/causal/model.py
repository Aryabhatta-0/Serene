"""Deterministic Causal Twin: candidate / supported / refuted relationship state (issue #27).

One edge per hypothesis. An edge's *state* is never proposed: it is derived
from the ledger by `build_causal_twin`, and the model validators make illegal
states unrepresentable (e.g. SUPPORTED without experimental support, any edge
without raw-evidence provenance). There are deliberately no numeric
confidence or effect-size fields: level 4 means "an approved, bounded N-of-1
experiment supported this in this scope", nothing more (docs/epistemic-model.md).

Belief lives here and in investigation state; it is rebuilt from the ledger
only and never read from, or written to, memory_repo (issue #29).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from serene.domain.base import (
    ChildId,
    EntityId,
    EvidenceId,
    ExperimentId,
    HypothesisId,
    KernelModel,
    Sha256Hex,
    ShortText,
    Tag,
)
from serene.domain.entities import LearningStatus, OutcomeResult, ValidityWindow
from serene.domain.values import EpistemicLevel, Provenance, Scope
from serene.lineage.provenance import trace_lineage
from serene.policies.learning import effective_status
from serene.policies.promotion import counterevidence_for, tested_experiments
from serene.projections.state import KernelState, LifecycleStatus

TWIN_VERSION = "causal-twin/1"


class RelationshipStatus(StrEnum):
    CANDIDATE = "CANDIDATE"  # proposed / observational / contested: not established
    SUPPORTED = "SUPPORTED"  # tested by an approved experiment, nothing contradicts it
    REFUTED = "REFUTED"  # refuted by policy on a contradicting outcome
    SUPERSEDED = "SUPERSEDED"  # replaced by a better-formed hypothesis


class SupportKind(StrEnum):
    OBSERVATIONAL = "OBSERVATIONAL"  # observations / evidence: co-occurrence, not cause
    EXPERIMENTAL = "EXPERIMENTAL"  # SUPPORTS outcome of an approved, completed experiment


class SupportItem(KernelModel):
    entity_id: EntityId
    kind: SupportKind


_TRUSTED_VALIDITY = frozenset({LearningStatus.ACTIVE, LearningStatus.NEEDS_REVIEW})


class CausalEdge(KernelModel):
    edge_id: HypothesisId
    child_id: ChildId
    relationship: ShortText
    cause: Tag | None = None
    effect: Tag | None = None
    status: RelationshipStatus
    epistemic_level: EpistemicLevel
    support: tuple[SupportItem, ...] = Field(default=(), max_length=512)
    counterevidence: tuple[EntityId, ...] = Field(default=(), max_length=512)
    contradicting_outcomes: tuple[EntityId, ...] = Field(default=(), max_length=128)
    confounders: tuple[ShortText, ...] = Field(default=(), max_length=16)
    alternative_explanations: tuple[ShortText, ...] = Field(default=(), max_length=16)
    competing_edges: tuple[HypothesisId, ...] = Field(default=(), max_length=32)
    experiments: tuple[ExperimentId, ...] = Field(default=(), max_length=64)
    scope: Scope
    validity: ValidityWindow | None = None
    learning_status: LearningStatus | None = None
    provenance: Provenance
    raw_evidence: tuple[EvidenceId, ...] = Field(min_length=1, max_length=512)

    @property
    def experimentally_supported(self) -> bool:
        return any(s.kind is SupportKind.EXPERIMENTAL for s in self.support)

    @model_validator(mode="after")
    def _state_is_consistent(self) -> Self:
        if self.scope.child_id != self.child_id:
            raise ValueError("edge scope must belong to the same child")
        if not self.provenance.derived_from or not self.provenance.source_ids:
            raise ValueError("an edge requires lineage provenance")
        if self.status is RelationshipStatus.SUPPORTED:
            if not self.experimentally_supported:
                raise ValueError("observational support alone cannot make an edge SUPPORTED")
            if self.epistemic_level < EpistemicLevel.TESTED_HYPOTHESIS:
                raise ValueError("a SUPPORTED edge must be at least a tested hypothesis")
            if self.contradicting_outcomes:
                raise ValueError("a contradicted edge cannot be SUPPORTED")
            if self.learning_status is not None and self.learning_status not in _TRUSTED_VALIDITY:
                raise ValueError("a stale or retest-pending learning cannot back a SUPPORTED edge")
        if self.status is RelationshipStatus.REFUTED and not self.contradicting_outcomes:
            raise ValueError("a REFUTED edge must cite the contradicting outcome")
        if self.epistemic_level is EpistemicLevel.CONTEXTUAL_LEARNING and self.validity is None:
            raise ValueError("a level-5 edge carries its validity window")
        if set(self.contradicting_outcomes) - set(self.counterevidence):
            raise ValueError("contradicting outcomes are part of the counterevidence")
        return self


class CausalTwin(KernelModel):
    twin_version: str = TWIN_VERSION
    child_id: ChildId
    ledger_head: Sha256Hex
    edges: tuple[CausalEdge, ...] = Field(default=(), max_length=1024)

    @property
    def variables(self) -> tuple[str, ...]:
        names = {v for e in self.edges for v in (e.cause, e.effect) if v is not None}
        return tuple(sorted(names))

    def edge(self, hypothesis_id: str) -> CausalEdge:
        return next(e for e in self.edges if e.edge_id == hypothesis_id)


def _status(
    lifecycle: LifecycleStatus,
    level: EpistemicLevel,
    contradicted: bool,
    experimental: bool,
    learning_status: LearningStatus | None,
) -> RelationshipStatus:
    if lifecycle is LifecycleStatus.REFUTED and contradicted:
        return RelationshipStatus.REFUTED
    if lifecycle is LifecycleStatus.SUPERSEDED:
        return RelationshipStatus.SUPERSEDED
    trusted = learning_status is None or learning_status in _TRUSTED_VALIDITY
    if level >= EpistemicLevel.TESTED_HYPOTHESIS and experimental and not contradicted and trusted:
        return RelationshipStatus.SUPPORTED
    return RelationshipStatus.CANDIDATE


def build_edge(
    hypothesis_id: str,
    state: KernelState,
    now: datetime,
    *,
    cause: str | None = None,
    effect: str | None = None,
) -> CausalEdge:
    record = state.entities[hypothesis_id]
    hyp = record.entity
    level = state.hypothesis_levels[hypothesis_id]
    counter = counterevidence_for(hypothesis_id, state)

    observational: set[str] = set(hyp.supporting_evidence_ids)
    for pattern_id in hyp.pattern_ids:
        pattern = state.entities.get(pattern_id)
        if pattern is not None:
            observational |= set(pattern.entity.observation_ids)
    experimental = sorted(
        outcome_id
        for exp_id in tested_experiments(hypothesis_id, state)
        for outcome_id in state.experiments[exp_id].outcome_ids
        if state.entities[outcome_id].entity.result is OutcomeResult.SUPPORTS
    )
    support = tuple(
        [SupportItem(entity_id=o, kind=SupportKind.OBSERVATIONAL) for o in sorted(observational)]
        + [SupportItem(entity_id=o, kind=SupportKind.EXPERIMENTAL) for o in experimental]
    )

    learning = next(
        (
            lr
            for _, lr in sorted(state.learnings.items())
            if lr.hypothesis_id == hypothesis_id and lr.superseded_by is None
        ),
        None,
    )
    learning_status = None if learning is None else effective_status(learning, state, now)
    validity = (
        None
        if learning is None
        else ValidityWindow(valid_from=learning.valid_from, review_after=learning.review_after)
    )
    experiments = tuple(
        sorted(
            e for e, r in state.experiments.items() if r.experiment.hypothesis_id == hypothesis_id
        )
    )
    rivals = set(hyp.competing_hypothesis_ids) | set(
        state.investigation_hypotheses.get(hyp.investigation_id, [])
    )
    rivals.discard(hypothesis_id)
    return CausalEdge(
        edge_id=hypothesis_id,
        child_id=hyp.child_id,
        relationship=hyp.statement,
        cause=cause,
        effect=effect,
        status=_status(
            record.status,
            level,
            bool(counter.contradicting_outcomes),
            bool(experimental),
            learning_status,
        ),
        epistemic_level=level,
        support=support,
        counterevidence=counter.all_ids,
        contradicting_outcomes=counter.contradicting_outcomes,
        confounders=hyp.known_confounders,
        alternative_explanations=hyp.alternative_explanations,
        competing_edges=tuple(sorted(rivals)),
        experiments=experiments,
        scope=hyp.scope,
        validity=validity,
        learning_status=learning_status,
        provenance=hyp.provenance,
        raw_evidence=trace_lineage(hypothesis_id, state).raw_evidence,
    )


def build_causal_twin(
    state: KernelState,
    now: datetime,
    labels: Mapping[str, tuple[str, str]] | None = None,
) -> CausalTwin:
    """Rebuild the twin from ledger state. `labels` name variables and carry no authority."""
    if state.child_id is None:
        raise ValueError("cannot build a twin for an empty stream")
    labels = labels or {}
    edges = []
    for hypothesis_id in sorted(state.hypothesis_levels):
        cause, effect = labels.get(hypothesis_id, (None, None))
        edges.append(build_edge(hypothesis_id, state, now, cause=cause, effect=effect))
    return CausalTwin(
        child_id=state.child_id, ledger_head=state.last_event_hash, edges=tuple(edges)
    )
