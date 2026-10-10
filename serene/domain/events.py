"""Closed domain-event taxonomy and the ledger envelope (issues #3, #5).

Every event type is bound to exactly one payload schema and to the actor kinds
allowed to append it. Unknown types, wrong payload schemas and unauthorized
actors are rejected before anything is hashed or stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Literal

from pydantic import Field, JsonValue

from serene.domain.base import (
    SCHEMA_VERSION,
    ActorId,
    ApprovalRequestId,
    ChildId,
    EntityId,
    EventId,
    EvidenceId,
    EvidenceRequestId,
    ExperimentId,
    HypothesisId,
    InvestigationId,
    KernelModel,
    LearningId,
    MemoryPatchId,
    OutcomeId,
    ReasonCode,
    Sha256Hex,
    ShortText,
    Tag,
    UtcDatetime,
)
from serene.domain.canonical import canonical_json
from serene.domain.entities import (
    Evidence,
    Experiment,
    Hypothesis,
    Investigation,
    InvestigationStatus,
    Learning,
    LearningStatus,
    MemoryPatch,
    Observation,
    Outcome,
    Pattern,
    Trial,
)
from serene.domain.values import (
    ActorKind,
    ActorRef,
    EpistemicLevel,
    SourceKind,
    SourceRef,
    VerificationStatus,
)

HASH_VERSION: Final = 1
GENESIS_HASH: Final = "0" * 64


class EventType(StrEnum):
    # observation
    OBSERVATION_REPORTED = "OBSERVATION_REPORTED"
    OBSERVATION_STRUCTURED = "OBSERVATION_STRUCTURED"
    # evidence
    EVIDENCE_REQUESTED = "EVIDENCE_REQUESTED"
    EVIDENCE_ACQUIRED = "EVIDENCE_ACQUIRED"
    EVIDENCE_VERIFIED = "EVIDENCE_VERIFIED"
    EVIDENCE_REJECTED = "EVIDENCE_REJECTED"
    # pattern / hypothesis
    PATTERN_PROPOSED = "PATTERN_PROPOSED"
    HYPOTHESIS_PROPOSED = "HYPOTHESIS_PROPOSED"
    HYPOTHESIS_SUPERSEDED = "HYPOTHESIS_SUPERSEDED"
    HYPOTHESIS_REFUTED = "HYPOTHESIS_REFUTED"
    # promotion
    PROMOTION_REQUESTED = "PROMOTION_REQUESTED"
    PROMOTION_GRANTED = "PROMOTION_GRANTED"
    PROMOTION_DENIED = "PROMOTION_DENIED"
    # investigation
    INVESTIGATION_OPENED = "INVESTIGATION_OPENED"
    INVESTIGATION_STATUS_CHANGED = "INVESTIGATION_STATUS_CHANGED"
    # experiment
    EXPERIMENT_PROPOSED = "EXPERIMENT_PROPOSED"
    EXPERIMENT_CLASSIFIED = "EXPERIMENT_CLASSIFIED"
    EXPERIMENT_BLOCKED = "EXPERIMENT_BLOCKED"
    EXPERIMENT_STARTED = "EXPERIMENT_STARTED"
    TRIAL_RECORDED = "TRIAL_RECORDED"
    OUTCOME_REPORTED = "OUTCOME_REPORTED"
    EXPERIMENT_COMPLETED = "EXPERIMENT_COMPLETED"
    EXPERIMENT_ABANDONED = "EXPERIMENT_ABANDONED"
    # approval
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_NUDGED = "APPROVAL_NUDGED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    APPROVAL_TIMED_OUT = "APPROVAL_TIMED_OUT"
    # learning
    LEARNING_RECORDED = "LEARNING_RECORDED"
    LEARNING_STATUS_CHANGED = "LEARNING_STATUS_CHANGED"
    LEARNING_SUPERSEDED = "LEARNING_SUPERSEDED"
    # memory
    MEMORY_PATCH_PROPOSED = "MEMORY_PATCH_PROPOSED"
    MEMORY_PATCH_COMMITTED = "MEMORY_PATCH_COMMITTED"
    MEMORY_PATCH_REJECTED = "MEMORY_PATCH_REJECTED"


# ----------------------------------------------------------------- payloads
class _Payload(KernelModel):
    schema_version: Literal[1] = SCHEMA_VERSION


class ObservationReported(_Payload):
    evidence: Evidence


class ObservationStructured(_Payload):
    observation: Observation


class InformationValue(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EvidenceRequested(_Payload):
    request_id: EvidenceRequestId
    investigation_id: InvestigationId
    requested_fields: tuple[Tag, ...] = Field(min_length=1, max_length=16)
    information_value: InformationValue
    rationale: ShortText


class EvidenceAcquired(_Payload):
    request_id: EvidenceRequestId | None = None
    evidence: Evidence


class VerificationCheck(StrEnum):
    SOURCE_ALLOWED = "SOURCE_ALLOWED"
    SUBJECT_MATCHES = "SUBJECT_MATCHES"
    EFFECTIVE_DATE_VALID = "EFFECTIVE_DATE_VALID"
    REQUESTED_FIELDS_PRESENT = "REQUESTED_FIELDS_PRESENT"
    DIGEST_MATCHES = "DIGEST_MATCHES"
    CHANNEL_AUTHENTICATED = "CHANNEL_AUTHENTICATED"


class EvidenceVerified(_Payload):
    evidence_id: EvidenceId
    checks_passed: tuple[VerificationCheck, ...] = Field(min_length=1)
    verifier_version: ShortText


class EvidenceRejected(_Payload):
    evidence_id: EvidenceId
    reason_codes: tuple[ReasonCode, ...] = Field(min_length=1)
    verifier_version: ShortText


class PatternProposed(_Payload):
    pattern: Pattern


class HypothesisProposed(_Payload):
    hypothesis: Hypothesis


class HypothesisSuperseded(_Payload):
    hypothesis_id: HypothesisId
    superseded_by: HypothesisId
    reason: ShortText


class HypothesisRefuted(_Payload):
    hypothesis_id: HypothesisId
    outcome_ids: tuple[OutcomeId, ...] = Field(min_length=1)
    reason_codes: tuple[ReasonCode, ...] = Field(min_length=1)


class PromotionRequested(_Payload):
    subject_id: EntityId
    from_level: EpistemicLevel
    to_level: EpistemicLevel
    rationale: ShortText


class PromotionDecisionRecord(_Payload):
    subject_id: EntityId
    from_level: EpistemicLevel
    to_level: EpistemicLevel
    reason_codes: tuple[ReasonCode, ...]
    policy_version: ShortText
    facts_digest: Sha256Hex


class InvestigationOpened(_Payload):
    investigation: Investigation


class InvestigationStatusChanged(_Payload):
    investigation_id: InvestigationId
    from_status: InvestigationStatus
    to_status: InvestigationStatus
    reason_codes: tuple[ReasonCode, ...] = Field(min_length=1)


class ExperimentProposed(_Payload):
    experiment: Experiment


class SafetyClass(StrEnum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"


class ExperimentClassified(_Payload):
    experiment_id: ExperimentId
    safety_class: SafetyClass
    intervention_digest: Sha256Hex
    reason_codes: tuple[ReasonCode, ...] = Field(min_length=1)
    policy_version: ShortText


class ExperimentBlocked(_Payload):
    experiment_id: ExperimentId
    reason_codes: tuple[ReasonCode, ...] = Field(min_length=1)
    policy_version: ShortText


class ExperimentStarted(_Payload):
    experiment_id: ExperimentId
    approval_request_id: ApprovalRequestId
    intervention_digest: Sha256Hex
    policy_version: ShortText


class TrialRecorded(_Payload):
    trial: Trial


class OutcomeReported(_Payload):
    outcome: Outcome


class ExperimentCompleted(_Payload):
    experiment_id: ExperimentId
    outcome_ids: tuple[OutcomeId, ...] = Field(min_length=1)


class ExperimentAbandoned(_Payload):
    experiment_id: ExperimentId
    reason_codes: tuple[ReasonCode, ...] = Field(min_length=1)


class ApprovalRequested(_Payload):
    approval_request_id: ApprovalRequestId
    experiment_id: ExperimentId
    intervention_digest: Sha256Hex
    safety_class: SafetyClass
    requested_of: ActorId
    expires_at: UtcDatetime


class ApprovalNudged(_Payload):
    approval_request_id: ApprovalRequestId


class ChannelReceipt(KernelModel):
    """Proof that a decision arrived on an authenticated channel.

    Minted by the channel adapter after verifying the transport (e.g. Telegram
    webhook secret + callback query), never by model text.
    """

    channel: Literal[SourceKind.TELEGRAM, SourceKind.WEB_APP]
    message_ref: ShortText
    received_at: UtcDatetime


class ApprovalGranted(_Payload):
    approval_request_id: ApprovalRequestId
    intervention_digest: Sha256Hex
    acknowledged_safety_class: SafetyClass
    receipt: ChannelReceipt


class ApprovalRejected(_Payload):
    approval_request_id: ApprovalRequestId
    receipt: ChannelReceipt


class ApprovalTimedOut(_Payload):
    approval_request_id: ApprovalRequestId


class LearningRecorded(_Payload):
    learning: Learning
    promotion_event_id: EventId


class LearningStatusChanged(_Payload):
    learning_id: LearningId
    from_status: LearningStatus
    to_status: LearningStatus
    reason_codes: tuple[ReasonCode, ...] = Field(min_length=1)


class LearningSuperseded(_Payload):
    learning_id: LearningId
    superseded_by: LearningId
    reason: ShortText


class MemoryPatchProposed(_Payload):
    patch: MemoryPatch


class MemoryPatchCommitted(_Payload):
    patch_id: MemoryPatchId
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")


class MemoryPatchRejected(_Payload):
    patch_id: MemoryPatchId
    reason_codes: tuple[ReasonCode, ...] = Field(min_length=1)


# ----------------------------------------------------------------- taxonomy
@dataclass(frozen=True, slots=True)
class EventSpec:
    payload: type[_Payload]
    actors: frozenset[ActorKind]
    # Verification statuses an event of this type may carry.
    statuses: frozenset[VerificationStatus]


_A = ActorKind
_V = VerificationStatus
_NA = frozenset({_V.NOT_APPLICABLE})
_CLAIM = frozenset({_V.UNVERIFIED, _V.VERIFIED})


def _spec(payload: type[_Payload], actors: set[ActorKind], statuses: frozenset[_V]) -> EventSpec:
    return EventSpec(payload, frozenset(actors), statuses)


EVENT_TAXONOMY: Final[dict[EventType, EventSpec]] = {
    EventType.OBSERVATION_REPORTED: _spec(ObservationReported, {_A.PARENT, _A.CAREGIVER}, _CLAIM),
    EventType.OBSERVATION_STRUCTURED: _spec(
        ObservationStructured, {_A.AGENT, _A.SYSTEM}, frozenset({_V.UNVERIFIED})
    ),
    EventType.EVIDENCE_REQUESTED: _spec(EvidenceRequested, {_A.AGENT, _A.SYSTEM, _A.POLICY}, _NA),
    EventType.EVIDENCE_ACQUIRED: _spec(
        EvidenceAcquired, {_A.SYSTEM, _A.PARENT, _A.CAREGIVER}, frozenset({_V.UNVERIFIED})
    ),
    EventType.EVIDENCE_VERIFIED: _spec(EvidenceVerified, {_A.VERIFIER}, frozenset({_V.VERIFIED})),
    EventType.EVIDENCE_REJECTED: _spec(EvidenceRejected, {_A.VERIFIER}, frozenset({_V.REJECTED})),
    EventType.PATTERN_PROPOSED: _spec(
        PatternProposed, {_A.AGENT, _A.SYSTEM}, frozenset({_V.UNVERIFIED})
    ),
    EventType.HYPOTHESIS_PROPOSED: _spec(
        HypothesisProposed, {_A.AGENT, _A.SYSTEM}, frozenset({_V.UNVERIFIED})
    ),
    EventType.HYPOTHESIS_SUPERSEDED: _spec(
        HypothesisSuperseded, {_A.AGENT, _A.SYSTEM, _A.POLICY}, _NA
    ),
    EventType.HYPOTHESIS_REFUTED: _spec(HypothesisRefuted, {_A.POLICY}, _NA),
    EventType.PROMOTION_REQUESTED: _spec(PromotionRequested, {_A.AGENT, _A.SYSTEM, _A.PARENT}, _NA),
    EventType.PROMOTION_GRANTED: _spec(PromotionDecisionRecord, {_A.POLICY}, _NA),
    EventType.PROMOTION_DENIED: _spec(PromotionDecisionRecord, {_A.POLICY}, _NA),
    EventType.INVESTIGATION_OPENED: _spec(
        InvestigationOpened, {_A.PARENT, _A.AGENT, _A.SYSTEM}, _NA
    ),
    EventType.INVESTIGATION_STATUS_CHANGED: _spec(
        InvestigationStatusChanged, {_A.SYSTEM, _A.POLICY}, _NA
    ),
    EventType.EXPERIMENT_PROPOSED: _spec(
        ExperimentProposed, {_A.AGENT, _A.PARENT}, frozenset({_V.UNVERIFIED})
    ),
    EventType.EXPERIMENT_CLASSIFIED: _spec(ExperimentClassified, {_A.POLICY}, _NA),
    EventType.EXPERIMENT_BLOCKED: _spec(ExperimentBlocked, {_A.POLICY}, _NA),
    EventType.EXPERIMENT_STARTED: _spec(ExperimentStarted, {_A.POLICY}, _NA),
    EventType.TRIAL_RECORDED: _spec(
        TrialRecorded, {_A.PARENT, _A.CAREGIVER, _A.SYSTEM}, frozenset({_V.UNVERIFIED})
    ),
    EventType.OUTCOME_REPORTED: _spec(OutcomeReported, {_A.PARENT, _A.CAREGIVER}, _CLAIM),
    EventType.EXPERIMENT_COMPLETED: _spec(ExperimentCompleted, {_A.POLICY}, _NA),
    EventType.EXPERIMENT_ABANDONED: _spec(ExperimentAbandoned, {_A.PARENT, _A.POLICY}, _NA),
    EventType.APPROVAL_REQUESTED: _spec(ApprovalRequested, {_A.POLICY}, _NA),
    EventType.APPROVAL_NUDGED: _spec(ApprovalNudged, {_A.SYSTEM}, _NA),
    EventType.APPROVAL_GRANTED: _spec(ApprovalGranted, {_A.PARENT}, _NA),
    EventType.APPROVAL_REJECTED: _spec(ApprovalRejected, {_A.PARENT}, _NA),
    EventType.APPROVAL_TIMED_OUT: _spec(ApprovalTimedOut, {_A.SYSTEM, _A.POLICY}, _NA),
    EventType.LEARNING_RECORDED: _spec(LearningRecorded, {_A.POLICY}, frozenset({_V.VERIFIED})),
    EventType.LEARNING_STATUS_CHANGED: _spec(LearningStatusChanged, {_A.POLICY, _A.SYSTEM}, _NA),
    EventType.LEARNING_SUPERSEDED: _spec(LearningSuperseded, {_A.POLICY}, _NA),
    EventType.MEMORY_PATCH_PROPOSED: _spec(
        MemoryPatchProposed, {_A.AGENT, _A.SYSTEM, _A.PARENT}, frozenset({_V.UNVERIFIED})
    ),
    EventType.MEMORY_PATCH_COMMITTED: _spec(MemoryPatchCommitted, {_A.MEMORY_COMMITTER}, _NA),
    EventType.MEMORY_PATCH_REJECTED: _spec(MemoryPatchRejected, {_A.MEMORY_COMMITTER}, _NA),
}

EventPayload = _Payload


# ----------------------------------------------------------------- envelope
class EventDraft(KernelModel):
    """What a caller asks the ledger to append. Hashes/sequence are kernel-assigned."""

    event_type: EventType
    child_id: ChildId
    source: SourceRef
    actor: ActorRef
    occurred_at: UtcDatetime
    derived_from: tuple[EventId, ...] = Field(default=(), max_length=256)
    verification_status: VerificationStatus
    payload: _Payload


class DomainEvent(KernelModel):
    """An immutable, hash-chained ledger record."""

    event_id: EventId
    child_id: ChildId
    sequence: int = Field(ge=1)
    event_type: EventType
    schema_version: int = Field(ge=1)
    hash_version: Literal[1] = HASH_VERSION
    source: SourceRef
    actor: ActorRef
    occurred_at: UtcDatetime
    recorded_at: UtcDatetime
    derived_from: tuple[EventId, ...]
    verification_status: VerificationStatus
    payload: dict[str, JsonValue]
    prev_event_hash: Sha256Hex
    payload_hash: Sha256Hex
    event_hash: Sha256Hex

    def typed_payload(self) -> Any:
        """Re-validate the stored payload against its registered schema (fail closed)."""
        spec = EVENT_TAXONOMY[self.event_type]
        return spec.payload.model_validate_json(canonical_json(self.payload))
