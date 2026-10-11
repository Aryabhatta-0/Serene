"""Canonical domain entities (issue #1).

Shape-only: these models say what a well-formed object is. Whether an object
may *enter* the ledger at its epistemic level is decided by
`serene.policies.promotion`, never by the model that proposed it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from serene.domain.base import (
    SCHEMA_VERSION,
    ChildId,
    EvidenceId,
    ExperimentId,
    HypothesisId,
    InvestigationId,
    KernelModel,
    LearningId,
    LongText,
    MemoryPatchId,
    ObservationId,
    OutcomeId,
    PatternId,
    Sha256Hex,
    ShortText,
    Tag,
    TrialId,
    UtcDatetime,
)
from serene.domain.values import (
    ActorKind,
    ActorRef,
    EpistemicLevel,
    Provenance,
    Scope,
    SourceRef,
)


class _Entity(KernelModel):
    level: ClassVar[EpistemicLevel | None] = None

    schema_version: Literal[1] = SCHEMA_VERSION
    child_id: ChildId
    provenance: Provenance

    @property
    def entity_id(self) -> str:  # pragma: no cover - overridden
        raise NotImplementedError


class _DerivedEntity(_Entity):
    """Anything above raw evidence must point back down the ladder."""

    @model_validator(mode="after")
    def _lineage_present(self) -> Self:
        if not self.provenance.derived_from:
            raise ValueError("derived entities require provenance.derived_from")
        if not self.provenance.source_ids:
            raise ValueError("derived entities require provenance.source_ids")
        return self


# --------------------------------------------------------------------------- L0
class EvidenceKind(StrEnum):
    PARENT_REPORT = "PARENT_REPORT"
    CAREGIVER_REPORT = "CAREGIVER_REPORT"
    DOCUMENT = "DOCUMENT"
    BROWSER_CAPTURE = "BROWSER_CAPTURE"


class Evidence(_Entity):
    """Level 0: raw evidence, preserved verbatim and never rewritten."""

    level: ClassVar[EpistemicLevel | None] = EpistemicLevel.RAW_EVIDENCE

    evidence_id: EvidenceId
    kind: EvidenceKind
    source: SourceRef
    observer: ActorRef
    captured_at: UtcDatetime
    content: LongText
    content_digest: Sha256Hex

    @property
    def entity_id(self) -> str:
        return self.evidence_id

    @model_validator(mode="after")
    def _raw_has_no_parents(self) -> Self:
        if self.provenance.derived_from:
            raise ValueError("raw evidence cannot be derived from other entities")
        human_report = self.kind in {EvidenceKind.PARENT_REPORT, EvidenceKind.CAREGIVER_REPORT}
        if human_report:
            expected = (
                ActorKind.PARENT if self.kind is EvidenceKind.PARENT_REPORT else ActorKind.CAREGIVER
            )
            if self.observer.kind is not expected:
                raise ValueError("report kind must match the observer's actor kind")
        return self


# --------------------------------------------------------------------------- L1
class Observation(_DerivedEntity):
    """Level 1: a structured reading of raw evidence. Raw evidence is untouched."""

    level: ClassVar[EpistemicLevel | None] = EpistemicLevel.OBSERVATION

    observation_id: ObservationId
    evidence_ids: tuple[EvidenceId, ...] = Field(min_length=1, max_length=32)
    observer: ActorRef
    observed_at: UtcDatetime
    statement: ShortText
    contexts: tuple[Tag, ...] = Field(default=(), max_length=16)

    @property
    def entity_id(self) -> str:
        return self.observation_id


# --------------------------------------------------------------------------- L2
class Pattern(_DerivedEntity):
    """Level 2: a regularity across several observations. Not a cause."""

    level: ClassVar[EpistemicLevel | None] = EpistemicLevel.PATTERN

    pattern_id: PatternId
    observation_ids: tuple[ObservationId, ...] = Field(min_length=2, max_length=128)
    counter_observation_ids: tuple[ObservationId, ...] = Field(default=(), max_length=128)
    description: ShortText
    contexts: tuple[Tag, ...] = Field(default=(), max_length=16)

    @property
    def entity_id(self) -> str:
        return self.pattern_id


# --------------------------------------------------------------------------- L3/L4
class Hypothesis(_DerivedEntity):
    """Level 3: a candidate explanation, held alongside its competitors."""

    level: ClassVar[EpistemicLevel | None] = EpistemicLevel.HYPOTHESIS

    hypothesis_id: HypothesisId
    investigation_id: InvestigationId
    statement: ShortText
    pattern_ids: tuple[PatternId, ...] = Field(min_length=1, max_length=32)
    supporting_evidence_ids: tuple[EvidenceId, ...] = Field(default=(), max_length=128)
    counter_evidence_ids: tuple[EvidenceId, ...] = Field(default=(), max_length=128)
    competing_hypothesis_ids: tuple[HypothesisId, ...] = Field(default=(), max_length=16)
    alternative_explanations: tuple[ShortText, ...] = Field(default=(), max_length=16)
    known_confounders: tuple[ShortText, ...] = Field(default=(), max_length=16)
    falsification_criteria: tuple[ShortText, ...] = Field(min_length=1, max_length=8)
    scope: Scope

    @property
    def entity_id(self) -> str:
        return self.hypothesis_id

    @model_validator(mode="after")
    def _scope_matches_child(self) -> Self:
        if self.scope.child_id != self.child_id:
            raise ValueError("hypothesis scope must belong to the same child")
        return self


# --------------------------------------------------------------------------- investigation
class InvestigationStatus(StrEnum):
    OPEN = "OPEN"
    GATHERING_EVIDENCE = "GATHERING_EVIDENCE"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXPERIMENTING = "EXPERIMENTING"
    PARKED_UNRESOLVED = "PARKED_UNRESOLVED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


TERMINAL_INVESTIGATION_STATUSES = frozenset(
    {InvestigationStatus.RESOLVED, InvestigationStatus.CLOSED}
)


class InvestigationPhase(StrEnum):
    """Reasoning-loop phase of an investigation (issue #10, branch A).

    Orthogonal to `InvestigationStatus` (the coarse lifecycle used by the
    experiment/approval flow). Legal transitions and their evidence guards live
    in `serene.policies.investigation`; COMPLETE and PARKED_UNRESOLVED are
    terminal, so a finished investigation can never silently resume.
    """

    UNDERSTANDING = "UNDERSTANDING"
    RETRIEVING_CONTEXT = "RETRIEVING_CONTEXT"
    FORMING_HYPOTHESES = "FORMING_HYPOTHESES"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"
    ASKING_HUMAN = "ASKING_HUMAN"
    RESEARCHING = "RESEARCHING"
    VERIFYING = "VERIFYING"
    EVALUATING = "EVALUATING"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    COMPLETE = "COMPLETE"
    PARKED_UNRESOLVED = "PARKED_UNRESOLVED"


TERMINAL_INVESTIGATION_PHASES = frozenset(
    {InvestigationPhase.COMPLETE, InvestigationPhase.PARKED_UNRESOLVED}
)


class Investigation(_Entity):
    investigation_id: InvestigationId
    question: ShortText
    opened_by: ActorRef
    opened_at: UtcDatetime
    status: Literal[InvestigationStatus.OPEN] = InvestigationStatus.OPEN

    @property
    def entity_id(self) -> str:
        return self.investigation_id


# --------------------------------------------------------------------------- experiments
class InterventionCategory(StrEnum):
    # Candidate low-risk categories.
    ROUTINE_TIMING = "ROUTINE_TIMING"
    ENVIRONMENT = "ENVIRONMENT"
    TRANSITION_SUPPORT = "TRANSITION_SUPPORT"
    COMMUNICATION = "COMMUNICATION"
    PLAY_ACTIVITY = "PLAY_ACTIVITY"
    # Higher-burden categories that always escalate.
    CAREGIVER_COORDINATION = "CAREGIVER_COORDINATION"
    SLEEP_SCHEDULE = "SLEEP_SCHEDULE"
    MEAL_TIMING = "MEAL_TIMING"
    SCREEN_TIME = "SCREEN_TIME"
    # Forbidden: never enter autonomous experimentation (docs/safety.md).
    MEDICATION = "MEDICATION"
    SUPPLEMENT = "SUPPLEMENT"
    ALLERGEN_EXPOSURE = "ALLERGEN_EXPOSURE"
    SYMPTOM_TREATMENT = "SYMPTOM_TREATMENT"
    RESTRAINT = "RESTRAINT"
    PUNISHMENT = "PUNISHMENT"
    DANGEROUS_ACTIVITY = "DANGEROUS_ACTIVITY"
    FOOD_DEPRIVATION = "FOOD_DEPRIVATION"
    SLEEP_DEPRIVATION = "SLEEP_DEPRIVATION"
    # Anything the proposer could not place. Fails closed.
    OTHER = "OTHER"


class Burden(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Intervention(KernelModel):
    category: InterventionCategory
    description: ShortText
    reversible: bool
    max_duration_days: int = Field(ge=1, le=365)
    burden: Burden


class Experiment(_DerivedEntity):
    """A bounded N-of-1 test of one hypothesis. Safety class is never self-declared."""

    experiment_id: ExperimentId
    hypothesis_id: HypothesisId
    investigation_id: InvestigationId
    intervention: Intervention
    comparison: ShortText
    outcome_measure: ShortText
    scope: Scope

    @property
    def entity_id(self) -> str:
        return self.experiment_id

    @model_validator(mode="after")
    def _scope_matches_child(self) -> Self:
        if self.scope.child_id != self.child_id:
            raise ValueError("experiment scope must belong to the same child")
        return self


class TrialArm(StrEnum):
    BASELINE = "BASELINE"
    INTERVENTION = "INTERVENTION"


class Trial(_DerivedEntity):
    trial_id: TrialId
    experiment_id: ExperimentId
    arm: TrialArm
    occurred_at: UtcDatetime
    observation_ids: tuple[ObservationId, ...] = Field(min_length=1, max_length=32)

    @property
    def entity_id(self) -> str:
        return self.trial_id


class OutcomeResult(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    INCONCLUSIVE = "INCONCLUSIVE"


class Outcome(_DerivedEntity):
    outcome_id: OutcomeId
    experiment_id: ExperimentId
    result: OutcomeResult
    observation_ids: tuple[ObservationId, ...] = Field(min_length=1, max_length=64)
    reported_by: ActorRef
    reported_at: UtcDatetime
    summary: ShortText

    @property
    def entity_id(self) -> str:
        return self.outcome_id


# --------------------------------------------------------------------------- L5
class LearningStatus(StrEnum):
    ACTIVE = "ACTIVE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NEEDS_RETEST = "NEEDS_RETEST"
    STALE = "STALE"
    DEPRECATED = "DEPRECATED"


class ValidityWindow(KernelModel):
    valid_from: UtcDatetime
    review_after: UtcDatetime

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.review_after <= self.valid_from:
            raise ValueError("review_after must be later than valid_from")
        return self


class ReviewMetadata(KernelModel):
    reviewer: ActorRef
    retest_triggers: tuple[ShortText, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def _parent_reviews(self) -> Self:
        if self.reviewer.kind is not ActorKind.PARENT:
            raise ValueError("a contextual learning is reviewed by the parent")
        return self


class Learning(_DerivedEntity):
    """Level 5: a scoped, reviewable, expiring learning. Never a universal fact."""

    level: ClassVar[EpistemicLevel | None] = EpistemicLevel.CONTEXTUAL_LEARNING

    learning_id: LearningId
    hypothesis_id: HypothesisId
    experiment_ids: tuple[ExperimentId, ...] = Field(min_length=1, max_length=16)
    outcome_ids: tuple[OutcomeId, ...] = Field(min_length=1, max_length=64)
    statement: ShortText
    scope: Scope
    validity: ValidityWindow
    review: ReviewMetadata
    status: Literal[LearningStatus.ACTIVE] = LearningStatus.ACTIVE

    @property
    def entity_id(self) -> str:
        return self.learning_id

    @model_validator(mode="after")
    def _scope_matches_child(self) -> Self:
        if self.scope.child_id != self.child_id:
            raise ValueError("learning scope must belong to the same child")
        return self


# --------------------------------------------------------------------------- memory
class MemoryOperation(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DEPRECATE = "DEPRECATE"


MemoryPath = Annotated[
    str,
    StringConstraints(
        pattern=(
            r"^(child|caregivers|routines|patterns|investigations|decisions|learnings)"
            r"/[a-z0-9][a-z0-9_\-]{0,63}\.md$"
        )
    ),
]


class MemoryPatch(_DerivedEntity):
    """A *proposed* change to memory_repo. Only the Memory Committer applies it."""

    patch_id: MemoryPatchId
    target_path: MemoryPath
    operation: MemoryOperation
    base_revision: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")] | None
    diff: Annotated[str, StringConstraints(min_length=1, max_length=20000)]
    rationale: ShortText
    required_level: EpistemicLevel

    @property
    def entity_id(self) -> str:
        return self.patch_id


DomainEntity = (
    Evidence
    | Observation
    | Pattern
    | Hypothesis
    | Investigation
    | Experiment
    | Trial
    | Outcome
    | Learning
    | MemoryPatch
)
