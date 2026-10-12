"""Privacy-safe provenance projection of the Causal Twin for the web (issue #75).

The twin (`serene.causal.model`) carries ids. This projection carries what the
web needs to answer "why does Serene believe this?" for every edge without
reading the ledger:

- every observation and piece of evidence the edge cites, with its display
  text, time, `Evidence.kind` / `SourceRef.kind` and verification status, so
  external evidence is told apart from family evidence;
- every experiment on the edge with its status and its outcomes, each outcome
  carrying its own `experiment_id` (the explicit outcome -> experiment link);
- the complete `trace_lineage` of the edge, and of everything it cites: every
  intermediate node with its parents and verification status. A node the trace
  cannot find is a `MissingNode`, never silently dropped;
- supersession (`superseded_by` and the recorded reason) and refutation
  (reason codes and the refuting outcome ids);
- for a level-5 edge, its learning: scope, validity, review date and status,
  confounders, counterevidence and experiments.

Like `build_causal_twin`, it is a pure function of `KernelState` and a time,
and it carries no authority: nothing here decides what an edge means.

Privacy: no child id, no actor id (only the actor's *kind*), no `src_` source
id (it can name a private channel), and no raw evidence content. A raw-evidence
node is described by its kind, its channel and when it was captured; an
external source by its public host only. Display text is the derived text the
domain already holds (observation statement, pattern description, hypothesis
statement, investigation question, outcome summary, learning statement). Like
the Experiments and Memory views it is private application data, not telemetry.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from typing import Any, Final, Literal, Self

from pydantic import Field, model_validator

from serene.causal.model import CausalTwin, RelationshipStatus, SupportKind, build_causal_twin
from serene.domain.base import (
    EntityId,
    EvidenceId,
    ExperimentId,
    HypothesisId,
    KernelModel,
    LearningId,
    OutcomeId,
    ReasonCode,
    Sha256Hex,
    ShortText,
    Tag,
    UtcDatetime,
    id_prefix,
)
from serene.domain.entities import (
    Evidence,
    EvidenceKind,
    Experiment,
    Hypothesis,
    Investigation,
    Learning,
    LearningStatus,
    Observation,
    Outcome,
    OutcomeResult,
    Pattern,
    Trial,
    ValidityWindow,
)
from serene.domain.events import SafetyClass
from serene.domain.values import (
    ActorKind,
    DerivationMethod,
    EpistemicLevel,
    ModelRef,
    Provenance,
    SourceKind,
    VerificationStatus,
)
from serene.lineage.provenance import trace_lineage
from serene.policies.external_evidence import EXTERNAL_SOURCES, host_of
from serene.policies.learning import effective_status
from serene.projections.state import ExperimentStatus, KernelState, LifecycleStatus

VIEW_VERSION: Final = "causal-twin-provenance/1"


class NodeKind(StrEnum):
    EVIDENCE = "EVIDENCE"
    OBSERVATION = "OBSERVATION"
    PATTERN = "PATTERN"
    HYPOTHESIS = "HYPOTHESIS"
    INVESTIGATION = "INVESTIGATION"
    EXPERIMENT = "EXPERIMENT"
    TRIAL = "TRIAL"
    OUTCOME = "OUTCOME"
    LEARNING = "LEARNING"
    OTHER = "OTHER"


_KIND_BY_PREFIX: Final = {
    "evd": NodeKind.EVIDENCE,
    "obs": NodeKind.OBSERVATION,
    "pat": NodeKind.PATTERN,
    "hyp": NodeKind.HYPOTHESIS,
    "inv": NodeKind.INVESTIGATION,
    "exp": NodeKind.EXPERIMENT,
    "trl": NodeKind.TRIAL,
    "out": NodeKind.OUTCOME,
    "lrn": NodeKind.LEARNING,
}


class EvidenceOrigin(StrEnum):
    """Where the raw evidence under an item came from. Read from `SourceRef.kind`."""

    FAMILY = "FAMILY"  # every raw source entered through a family channel
    EXTERNAL = "EXTERNAL"  # every raw source is an external document or web capture
    MIXED = "MIXED"
    UNRESOLVED = "UNRESOLVED"  # no raw evidence was reached: the lineage has a gap


class NodeOrigin(KernelModel):
    """An entity's provenance without the actor id."""

    actor_kind: ActorKind
    method: DerivationMethod
    model: ModelRef | None
    created_at: UtcDatetime
    derived_from: tuple[EntityId, ...]
    source_ids: tuple[EntityId, ...]
    supersedes: EntityId | None


class RawEvidenceDetail(KernelModel):
    """What can be shown about one piece of raw evidence: never its content."""

    evidence_kind: EvidenceKind
    source_kind: SourceKind
    external: bool
    source_host: ShortText | None  # public host of an external source only
    captured_at: UtcDatetime
    retrieved_at: UtcDatetime | None
    content_digest: Sha256Hex
    checks_passed: tuple[ReasonCode, ...]
    rejection_reason_codes: tuple[ReasonCode, ...]

    @model_validator(mode="after")
    def _external_is_the_source_kind(self) -> Self:
        if self.external != (self.source_kind in EXTERNAL_SOURCES):
            raise ValueError("external evidence is exactly evidence from an external source")
        if self.source_host is not None and not self.external:
            raise ValueError("only an external source names its host")
        return self


class ProvenanceNode(KernelModel):
    """One entity on a provenance chain, as the web may show it."""

    entity_id: EntityId
    kind: NodeKind
    epistemic_level: EpistemicLevel | None
    verification_status: VerificationStatus
    lifecycle: LifecycleStatus
    superseded_by: EntityId | None
    summary: ShortText
    occurred_at: UtcDatetime
    origin: NodeOrigin
    evidence: RawEvidenceDetail | None
    parents: tuple[EntityId, ...]
    raw_evidence: tuple[EvidenceId, ...]  # this node's own trace, down to raw evidence
    missing: tuple[EntityId, ...]  # gaps in this node's own trace
    evidence_origin: EvidenceOrigin

    @model_validator(mode="after")
    def _raw_evidence_is_the_floor(self) -> Self:
        if (self.kind is NodeKind.EVIDENCE) != (self.evidence is not None):
            raise ValueError("evidence detail is present exactly on raw evidence")
        if self.kind is NodeKind.EVIDENCE and (
            self.parents or self.raw_evidence != (self.entity_id,)
        ):
            raise ValueError("raw evidence has no parents and rests on itself")
        if (self.evidence_origin is EvidenceOrigin.UNRESOLVED) != (not self.raw_evidence):
            raise ValueError("an item's origin is unresolved exactly when no evidence is reached")
        return self


class MissingNode(KernelModel):
    """An id the chain names that Serene's record does not hold. Shown, never dropped."""

    entity_id: EntityId
    referenced_by: tuple[EntityId, ...] = Field(min_length=1)


class LineageStep(KernelModel):
    entity_id: EntityId
    depth: int = Field(ge=0, le=64)  # fewest hops from the edge


class EdgeLineage(KernelModel):
    """`trace_lineage` of the edge: every node, nearest first, and every gap."""

    root: HypothesisId
    steps: tuple[LineageStep, ...]
    raw_evidence: tuple[EvidenceId, ...]
    missing: tuple[MissingNode, ...]
    complete: bool

    @model_validator(mode="after")
    def _complete_means_no_gaps(self) -> Self:
        if self.complete != (not self.missing and bool(self.raw_evidence)):
            raise ValueError("a lineage is complete when it has no gaps and reaches evidence")
        on_chain = {s.entity_id for s in self.steps}
        if not set(self.raw_evidence) <= on_chain:
            raise ValueError("raw evidence of a lineage lies on it")
        return self


class SupportRef(KernelModel):
    entity_id: EntityId
    kind: SupportKind


class CounterRef(KernelModel):
    entity_id: EntityId
    contradicting_outcome: bool  # a CONTRADICTS outcome of a test of this edge


class OutcomeProvenance(KernelModel):
    outcome_id: OutcomeId
    experiment_id: ExperimentId
    result: OutcomeResult
    reported_at: UtcDatetime
    summary: ShortText


class ExperimentProvenance(KernelModel):
    experiment_id: ExperimentId
    status: ExperimentStatus
    safety_class: SafetyClass | None
    intervention: ShortText
    outcome_measure: ShortText
    started_at: UtcDatetime | None
    ended_at: UtcDatetime | None
    outcomes: tuple[OutcomeProvenance, ...]

    @model_validator(mode="after")
    def _outcomes_belong_to_it(self) -> Self:
        if any(o.experiment_id != self.experiment_id for o in self.outcomes):
            raise ValueError("an experiment lists only its own outcomes")
        return self


class SupersessionDetail(KernelModel):
    superseded_by: HypothesisId | None  # the edge that replaced this one
    reason: ShortText | None  # HypothesisSuperseded.reason
    supersedes: EntityId | None  # what this edge replaced (its provenance.supersedes)

    @model_validator(mode="after")
    def _replacement_is_explained(self) -> Self:
        if (self.superseded_by is None) != (self.reason is None):
            raise ValueError("a replaced edge carries its supersession reason")
        return self


class RefutationDetail(KernelModel):
    reason_codes: tuple[ReasonCode, ...] = Field(min_length=1)
    outcome_ids: tuple[OutcomeId, ...] = Field(min_length=1)


class LearningProvenance(KernelModel):
    """A level-5 edge's learning: where, from when, until when, and what could undo it."""

    learning_id: LearningId
    statement: ShortText
    recorded_status: LearningStatus
    effective_status: LearningStatus
    review_due: bool
    scope_contexts: tuple[Tag, ...] = Field(min_length=1)
    valid_from: UtcDatetime
    review_after: UtcDatetime
    status_changed_at: UtcDatetime | None
    reviewer_kind: ActorKind
    retest_triggers: tuple[ShortText, ...]
    experiment_ids: tuple[ExperimentId, ...]
    outcome_ids: tuple[OutcomeId, ...]
    confounders: tuple[ShortText, ...]
    counterevidence: tuple[EntityId, ...]
    superseded_learnings: tuple[LearningId, ...]


class EdgeProvenance(KernelModel):
    edge_id: HypothesisId
    relationship: ShortText
    status: RelationshipStatus
    lifecycle: LifecycleStatus
    epistemic_level: EpistemicLevel
    verification_status: VerificationStatus
    learning_status: LearningStatus | None
    scope_contexts: tuple[Tag, ...] = Field(min_length=1)
    validity: ValidityWindow | None
    confounders: tuple[ShortText, ...]
    alternative_explanations: tuple[ShortText, ...]
    competing_edges: tuple[HypothesisId, ...]
    support: tuple[SupportRef, ...]
    counterevidence: tuple[CounterRef, ...]
    experiments: tuple[ExperimentProvenance, ...]
    learning: LearningProvenance | None
    supersession: SupersessionDetail
    refutation: RefutationDetail | None
    origin: NodeOrigin
    lineage: EdgeLineage

    @model_validator(mode="after")
    def _state_is_explained(self) -> Self:
        if self.lineage.root != self.edge_id:
            raise ValueError("an edge's lineage starts at the edge")
        if self.epistemic_level is EpistemicLevel.CONTEXTUAL_LEARNING and (
            self.learning is None or self.validity is None
        ):
            raise ValueError("a level-5 edge carries its learning and validity window")
        if self.status is RelationshipStatus.REFUTED and self.refutation is None:
            raise ValueError("a refuted edge carries its refutation reasons")
        if (self.lifecycle is LifecycleStatus.REFUTED) != (self.refutation is not None):
            raise ValueError("refutation detail is present exactly on a refuted edge")
        if (self.lifecycle is LifecycleStatus.SUPERSEDED) != (
            self.supersession.superseded_by is not None
        ):
            raise ValueError("supersession detail is present exactly on a superseded edge")
        return self

    def cited_ids(self) -> set[str]:
        """Every entity id this edge's projection points at."""
        ids: set[str] = {self.edge_id}
        ids |= {s.entity_id for s in self.support}
        ids |= {c.entity_id for c in self.counterevidence}
        ids |= {s.entity_id for s in self.lineage.steps}
        ids |= set(self.lineage.raw_evidence)
        for exp in self.experiments:
            ids.add(exp.experiment_id)
            ids |= {o.outcome_id for o in exp.outcomes}
        if self.learning is not None:
            ids.add(self.learning.learning_id)
            ids |= set(self.learning.outcome_ids) | set(self.learning.experiment_ids)
        if self.refutation is not None:
            ids |= set(self.refutation.outcome_ids)
        ids |= set(self.origin.derived_from) | set(self.origin.source_ids)
        return ids


class TwinProvenanceView(KernelModel):
    version: Literal["causal-twin-provenance/1"] = VIEW_VERSION
    ledger_head: Sha256Hex
    as_of: UtcDatetime
    nodes: tuple[ProvenanceNode, ...]
    missing: tuple[MissingNode, ...]
    edges: tuple[EdgeProvenance, ...]

    @model_validator(mode="after")
    def _every_link_resolves(self) -> Self:
        known = {n.entity_id for n in self.nodes}
        gaps = {m.entity_id for m in self.missing}
        if len(known) != len(self.nodes) or known & gaps:
            raise ValueError("each id is one node or one missing entry")
        referenced: set[str] = set()
        for node in self.nodes:
            referenced |= set(node.parents) | set(node.raw_evidence) | set(node.missing)
        for edge in self.edges:
            referenced |= edge.cited_ids()
            referenced |= {m.entity_id for m in edge.lineage.missing}
        unresolved = referenced - known - gaps
        if unresolved:
            raise ValueError(f"unresolved provenance ids: {sorted(unresolved)}")
        if len({e.edge_id for e in self.edges}) != len(self.edges):
            raise ValueError("duplicate edge")
        return self


# ------------------------------------------------------------------- builders

_EVIDENCE_LABELS: Final = {
    EvidenceKind.PARENT_REPORT: "Parent report",
    EvidenceKind.CAREGIVER_REPORT: "Caregiver report",
    EvidenceKind.DOCUMENT: "Document",
    EvidenceKind.BROWSER_CAPTURE: "Web page capture",
}
_SOURCE_LABELS: Final = {
    SourceKind.TELEGRAM: "Telegram",
    SourceKind.WEB_APP: "the Serene web app",
    SourceKind.BROWSER: "the bounded browser",
    SourceKind.EXTERNAL_DOCUMENT: "an external document",
    SourceKind.KERNEL: "Serene's kernel",
    SourceKind.EVAL_FIXTURE: "a synthetic evaluation fixture",
}


def _origin(prov: Provenance) -> NodeOrigin:
    return NodeOrigin(
        actor_kind=prov.created_by.kind,
        method=prov.method,
        model=prov.model,
        created_at=prov.created_at,
        derived_from=prov.derived_from,
        source_ids=prov.source_ids,
        supersedes=prov.supersedes,
    )


def _evidence_detail(entity: Evidence, state: KernelState) -> RawEvidenceDetail:
    external = entity.source.kind in EXTERNAL_SOURCES
    return RawEvidenceDetail(
        evidence_kind=entity.kind,
        source_kind=entity.source.kind,
        external=external,
        source_host=host_of(entity.source.uri) if external else None,
        captured_at=entity.captured_at,
        retrieved_at=entity.source.retrieved_at,
        content_digest=entity.content_digest,
        checks_passed=state.evidence_checks.get(entity.evidence_id, ()),
        rejection_reason_codes=state.evidence_rejections.get(entity.evidence_id, ()),
    )


def _summary(entity: Any, detail: RawEvidenceDetail | None) -> tuple[str, datetime]:
    """Display text and time. Raw evidence is named by kind and channel, never quoted."""
    match entity:
        case Evidence():
            assert detail is not None
            where = detail.source_host or _SOURCE_LABELS[detail.source_kind]
            return f"{_EVIDENCE_LABELS[entity.kind]} via {where}", entity.captured_at
        case Observation():
            return entity.statement, entity.observed_at
        case Pattern():
            return entity.description, entity.provenance.created_at
        case Hypothesis():
            return entity.statement, entity.provenance.created_at
        case Investigation():
            return entity.question, entity.opened_at
        case Experiment():
            return entity.intervention.description, entity.provenance.created_at
        case Trial():
            return f"{entity.arm.value.title()} trial", entity.occurred_at
        case Outcome():
            return entity.summary, entity.reported_at
        case Learning():
            return entity.statement, entity.provenance.created_at
    return "Recorded item", entity.provenance.created_at


def _evidence_origin(raw: Iterable[str], state: KernelState) -> EvidenceOrigin:
    kinds = {state.entities[e].entity.source.kind in EXTERNAL_SOURCES for e in raw}
    if not kinds:
        return EvidenceOrigin.UNRESOLVED
    if kinds == {True}:
        return EvidenceOrigin.EXTERNAL
    return EvidenceOrigin.FAMILY if kinds == {False} else EvidenceOrigin.MIXED


def _node(entity_id: str, state: KernelState) -> ProvenanceNode:
    record = state.entities[entity_id]
    entity = record.entity
    detail = _evidence_detail(entity, state) if isinstance(entity, Evidence) else None
    summary, occurred_at = _summary(entity, detail)
    trace = trace_lineage(entity_id, state)
    return ProvenanceNode(
        entity_id=entity_id,
        kind=_KIND_BY_PREFIX.get(id_prefix(entity_id), NodeKind.OTHER),
        epistemic_level=record.level,
        verification_status=record.verification_status,
        lifecycle=record.status,
        superseded_by=record.superseded_by,
        summary=summary[:500],
        occurred_at=occurred_at,
        origin=_origin(entity.provenance),
        evidence=detail,
        parents=tuple(entity.provenance.derived_from),
        raw_evidence=trace.raw_evidence,
        missing=trace.missing,
        evidence_origin=_evidence_origin(trace.raw_evidence, state),
    )


def _missing(gaps: set[str], referrers: dict[str, set[str]]) -> tuple[MissingNode, ...]:
    return tuple(
        MissingNode(entity_id=m, referenced_by=tuple(sorted(referrers[m]))) for m in sorted(gaps)
    )


def _lineage(edge_id: str, state: KernelState) -> EdgeLineage:
    trace = trace_lineage(edge_id, state)
    parents = {n.entity_id: n.parents for n in trace.nodes}
    depth: dict[str, int] = {}
    queue: deque[tuple[str, int]] = deque([(edge_id, 0)])
    while queue:
        current, d = queue.popleft()
        if current in depth or current not in parents:
            continue
        depth[current] = d
        queue.extend((p, d + 1) for p in parents[current])
    referrers: dict[str, set[str]] = {}
    for node in trace.nodes:
        for parent in node.parents:
            referrers.setdefault(parent, set()).add(node.entity_id)
    for gap in trace.missing:
        referrers.setdefault(gap, set()).add(edge_id)  # the root itself, if it is the gap
    return EdgeLineage(
        root=edge_id,
        steps=tuple(
            LineageStep(entity_id=n, depth=d)
            for n, d in sorted(depth.items(), key=lambda pair: (pair[1], pair[0]))
        ),
        raw_evidence=trace.raw_evidence,
        missing=tuple(
            MissingNode(entity_id=m, referenced_by=tuple(sorted(referrers[m] - {m})) or (edge_id,))
            for m in trace.missing
        ),
        complete=trace.complete,
    )


def _experiment(exp_id: str, state: KernelState) -> ExperimentProvenance:
    record = state.experiments[exp_id]
    exp = record.experiment
    outcomes = []
    for outcome_id in record.outcome_ids:
        outcome = state.entities[outcome_id].entity
        outcomes.append(
            OutcomeProvenance(
                outcome_id=outcome_id,
                experiment_id=outcome.experiment_id,
                result=outcome.result,
                reported_at=outcome.reported_at,
                summary=outcome.summary,
            )
        )
    return ExperimentProvenance(
        experiment_id=exp_id,
        status=record.status,
        safety_class=record.safety_class,
        intervention=exp.intervention.description,
        outcome_measure=exp.outcome_measure,
        started_at=record.started_at,
        ended_at=record.ended_at,
        outcomes=tuple(outcomes),
    )


def _learning(
    hypothesis_id: str, state: KernelState, now: datetime, edge_counter: tuple[str, ...]
) -> LearningProvenance | None:
    records = [lr for _, lr in sorted(state.learnings.items()) if lr.hypothesis_id == hypothesis_id]
    current = next((lr for lr in records if lr.superseded_by is None), None)
    if current is None:
        return None
    learning: Learning = state.entities[current.learning_id].entity
    hyp: Hypothesis = state.entities[hypothesis_id].entity
    return LearningProvenance(
        learning_id=current.learning_id,
        statement=learning.statement,
        recorded_status=current.status,
        effective_status=effective_status(current, state, now),
        review_due=now >= current.review_after,
        scope_contexts=learning.scope.contexts,
        valid_from=current.valid_from,
        review_after=current.review_after,
        status_changed_at=current.status_changed_at,
        reviewer_kind=learning.review.reviewer.kind,
        retest_triggers=learning.review.retest_triggers,
        experiment_ids=learning.experiment_ids,
        outcome_ids=learning.outcome_ids,
        confounders=hyp.known_confounders,
        counterevidence=edge_counter,
        superseded_learnings=tuple(lr.learning_id for lr in records if lr is not current),
    )


def build_twin_provenance(
    state: KernelState, now: datetime, twin: CausalTwin | None = None
) -> TwinProvenanceView:
    """Project every twin edge's provenance. `twin` defaults to the twin of `state` at `now`."""
    twin = twin or build_causal_twin(state, now)
    if twin.ledger_head != state.last_event_hash:
        raise ValueError("the twin was built from another ledger position")

    edges: list[EdgeProvenance] = []
    cited: dict[str, set[str]] = {}  # id -> the edges that cite it directly
    for edge in twin.edges:
        record = state.entities[edge.edge_id]
        contradicting = set(edge.contradicting_outcomes)
        lineage = _lineage(edge.edge_id, state)
        projected = EdgeProvenance(
            edge_id=edge.edge_id,
            relationship=edge.relationship,
            status=edge.status,
            lifecycle=record.status,
            epistemic_level=edge.epistemic_level,
            verification_status=record.verification_status,
            learning_status=edge.learning_status,
            scope_contexts=edge.scope.contexts,
            validity=edge.validity,
            confounders=edge.confounders,
            alternative_explanations=edge.alternative_explanations,
            competing_edges=edge.competing_edges,
            support=tuple(SupportRef(entity_id=s.entity_id, kind=s.kind) for s in edge.support),
            counterevidence=tuple(
                CounterRef(entity_id=c, contradicting_outcome=c in contradicting)
                for c in edge.counterevidence
            ),
            experiments=tuple(_experiment(e, state) for e in edge.experiments),
            learning=(
                _learning(edge.edge_id, state, now, edge.counterevidence)
                if edge.epistemic_level is EpistemicLevel.CONTEXTUAL_LEARNING
                else None
            ),
            supersession=SupersessionDetail(
                superseded_by=record.superseded_by,
                reason=record.supersession_reason,
                supersedes=edge.provenance.supersedes,
            ),
            refutation=(
                RefutationDetail(
                    reason_codes=record.refutation_reason_codes,
                    outcome_ids=record.refuting_outcome_ids,
                )
                if record.status is LifecycleStatus.REFUTED
                else None
            ),
            origin=_origin(edge.provenance),
            lineage=lineage,
        )
        edges.append(projected)
        for entity_id in projected.cited_ids():
            cited.setdefault(entity_id, set()).add(edge.edge_id)

    # Every cited id, and everything its own trace reaches, becomes one node.
    nodes: dict[str, ProvenanceNode] = {}
    gaps: set[str] = set()
    referrers: dict[str, set[str]] = {k: set(v) for k, v in cited.items()}
    pending = sorted(cited)
    while pending:
        entity_id = pending.pop()
        if entity_id in nodes or entity_id in gaps:
            continue
        if entity_id not in state.entities:
            gaps.add(entity_id)
            continue
        node = _node(entity_id, state)
        nodes[entity_id] = node
        for parent in (*node.parents, *node.raw_evidence, *node.missing):
            referrers.setdefault(parent, set()).add(entity_id)
            pending.append(parent)
    return TwinProvenanceView(
        ledger_head=twin.ledger_head,
        as_of=now,
        nodes=tuple(nodes[k] for k in sorted(nodes)),
        missing=_missing(gaps, referrers),
        edges=tuple(edges),
    )
