"""Value objects shared by every entity: actors, sources, scope and provenance."""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from serene.domain.base import (
    SCHEMA_VERSION,
    ActorId,
    ChildId,
    EntityId,
    KernelModel,
    Sha256Hex,
    SourceId,
    Tag,
    UtcDatetime,
)


class EpistemicLevel(IntEnum):
    """The six-rung ladder. Promotion moves exactly one rung at a time."""

    RAW_EVIDENCE = 0
    OBSERVATION = 1
    PATTERN = 2
    HYPOTHESIS = 3
    TESTED_HYPOTHESIS = 4
    CONTEXTUAL_LEARNING = 5


class VerificationStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    # Lifecycle events (approvals, status changes) make no truth claim.
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ActorKind(StrEnum):
    PARENT = "PARENT"
    CAREGIVER = "CAREGIVER"
    AGENT = "AGENT"  # any model-driven runtime (e.g. Hermes); proposals only
    POLICY = "POLICY"  # deterministic kernel policy (Promotion Gate, safety, approvals)
    VERIFIER = "VERIFIER"  # deterministic external-evidence verifier
    SYSTEM = "SYSTEM"  # trusted kernel/adapter plumbing (ingestion, timers)
    MEMORY_COMMITTER = "MEMORY_COMMITTER"  # single writer of memory_repo


HUMAN_ACTORS = frozenset({ActorKind.PARENT, ActorKind.CAREGIVER})


class ActorRef(KernelModel):
    """Who did something. Opaque id only: no names, no contact details."""

    kind: ActorKind
    actor_id: ActorId


class SourceKind(StrEnum):
    TELEGRAM = "TELEGRAM"
    WEB_APP = "WEB_APP"
    BROWSER = "BROWSER"
    EXTERNAL_DOCUMENT = "EXTERNAL_DOCUMENT"
    KERNEL = "KERNEL"
    EVAL_FIXTURE = "EVAL_FIXTURE"


# Channels on which an authenticated principal speaks for themselves.
AUTHENTICATED_CHANNELS = frozenset({SourceKind.TELEGRAM, SourceKind.WEB_APP})

HttpsUri = Annotated[str, StringConstraints(pattern=r"^https?://[^\s]{1,2000}$")]


class SourceRef(KernelModel):
    """Where a piece of information entered the system."""

    kind: SourceKind
    source_id: SourceId
    uri: HttpsUri | None = None
    content_digest: Sha256Hex | None = None
    retrieved_at: UtcDatetime | None = None

    @model_validator(mode="after")
    def _uri_only_for_external(self) -> Self:
        external = self.kind in {SourceKind.BROWSER, SourceKind.EXTERNAL_DOCUMENT}
        if external and (self.uri is None or self.content_digest is None):
            raise ValueError("external sources require uri and content_digest")
        if not external and self.uri is not None:
            raise ValueError("only external sources carry a uri")
        return self


class Scope(KernelModel):
    """Bounded applicability of a claim: whose child, in which contexts."""

    child_id: ChildId
    contexts: tuple[Tag, ...] = Field(min_length=1, max_length=16)


class DerivationMethod(StrEnum):
    PARENT_REPORT = "PARENT_REPORT"
    CAREGIVER_REPORT = "CAREGIVER_REPORT"
    BROWSER_ACQUISITION = "BROWSER_ACQUISITION"
    MODEL_EXTRACTION = "MODEL_EXTRACTION"
    MODEL_INFERENCE = "MODEL_INFERENCE"
    DETERMINISTIC_RULE = "DETERMINISTIC_RULE"
    EXPERIMENT_OUTCOME = "EXPERIMENT_OUTCOME"
    HUMAN_REVIEW = "HUMAN_REVIEW"


MODEL_METHODS = frozenset({DerivationMethod.MODEL_EXTRACTION, DerivationMethod.MODEL_INFERENCE})


class ModelRef(KernelModel):
    """Which model produced a proposal, so a belief can be re-examined later."""

    provider: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    model_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    prompt_version: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    runtime: Annotated[str, StringConstraints(min_length=1, max_length=64)]


class Provenance(KernelModel):
    """Why the kernel holds this object: the answer to 'why do you believe this?'.

    `derived_from` lists parent entity ids (one rung down the ladder);
    `source_ids` lists the raw evidence ids at the bottom of the chain.
    """

    schema_version: Literal[1] = SCHEMA_VERSION
    created_by: ActorRef
    created_at: UtcDatetime
    method: DerivationMethod
    model: ModelRef | None = None
    derived_from: tuple[EntityId, ...] = Field(default=(), max_length=256)
    source_ids: tuple[EntityId, ...] = Field(default=(), max_length=256)
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    supersedes: EntityId | None = None

    @model_validator(mode="after")
    def _model_attribution(self) -> Self:
        by_agent = self.created_by.kind is ActorKind.AGENT
        model_method = self.method in MODEL_METHODS
        if by_agent != model_method:
            raise ValueError("model methods must be attributed to an AGENT actor and vice versa")
        if model_method and self.model is None:
            raise ValueError("model-derived objects must record the model that produced them")
        if not model_method and self.model is not None:
            raise ValueError("model reference given for a non-model derivation")
        if len(set(self.derived_from)) != len(self.derived_from):
            raise ValueError("derived_from contains duplicates")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("source_ids contains duplicates")
        return self
