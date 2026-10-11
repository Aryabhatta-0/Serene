"""Observation ingestion: raw report first, structured reading second (issue #9).

1. `record_report` appends OBSERVATION_REPORTED with the message text exactly
   as received (content digest over its UTF-8 bytes). Nothing is trimmed,
   normalized or interpreted.
2. `structure` asks the runtime for an Observation over that evidence and
   admits it through the kernel boundary as a separate OBSERVATION_STRUCTURED
   event that references the raw evidence (lineage + `derived_from`).
3. Any extraction failure (runtime unavailable, malformed output, kernel
   refusal) appends OBSERVATION_STRUCTURING_FAILED and leaves the raw event
   untouched. Structuring is bounded by a ledger-counted attempt budget.

Inbound text can never directly change belief or memory: the only events this
module appends are a raw report, a boundary-admitted observation or a failure.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from serene.domain.base import new_id
from serene.domain.canonical import sha256_hex
from serene.domain.entities import Evidence, EvidenceKind
from serene.domain.events import (
    DomainEvent,
    EventDraft,
    EventType,
    ObservationReported,
    ObservationStructuringFailed,
)
from serene.domain.values import (
    ActorKind,
    ActorRef,
    DerivationMethod,
    Provenance,
    SourceKind,
    SourceRef,
    VerificationStatus,
)
from serene.investigation.boundary import KernelBoundary
from serene.ledger.service import EventLedger
from serene.observability.telemetry import SafeTelemetry
from serene.ports.agent_runtime import AgentRuntime, AgentTask, ProposalKind
from serene.ports.clock import Clock

MAX_STRUCTURING_ATTEMPTS: Final = 3
_STRUCTURING_KINDS: Final[tuple[ProposalKind, ...]] = ("observation", "abstain")


@dataclass(frozen=True, slots=True)
class StructuringOutcome:
    evidence_id: str
    structured: bool
    observation_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]


def report_evidence(
    *,
    child_id: str,
    observer: ActorRef,
    content: str,
    source: SourceRef,
    captured_at: datetime,
    evidence_id: str,
    verified: bool,
) -> Evidence:
    """Build L0 evidence that preserves `content` byte-for-byte."""
    status = VerificationStatus.VERIFIED if verified else VerificationStatus.UNVERIFIED
    is_parent = observer.kind is ActorKind.PARENT
    return Evidence(
        child_id=child_id,
        provenance=Provenance(
            created_by=observer,
            created_at=captured_at,
            method=(
                DerivationMethod.PARENT_REPORT if is_parent else DerivationMethod.CAREGIVER_REPORT
            ),
            verification_status=status,
        ),
        evidence_id=evidence_id,
        kind=EvidenceKind.PARENT_REPORT if is_parent else EvidenceKind.CAREGIVER_REPORT,
        source=source,
        observer=observer,
        captured_at=captured_at,
        content=content,
        content_digest=sha256_hex(content.encode("utf-8")),
    )


class ObservationIngestion:
    def __init__(
        self,
        ledger: EventLedger,
        clock: Clock,
        *,
        runtime: AgentRuntime,
        boundary: KernelBoundary,
        system_actor: ActorRef,
        telemetry: SafeTelemetry | None = None,
        max_attempts: int = MAX_STRUCTURING_ATTEMPTS,
        new_source_id: Callable[[], str] = lambda: new_id("src"),
    ) -> None:
        if system_actor.kind is not ActorKind.SYSTEM:
            raise ValueError("structuring failures are recorded by a SYSTEM actor")
        self._ledger = ledger
        self._clock = clock
        self._runtime = runtime
        self._boundary = boundary
        self._system = system_actor
        self._telemetry = telemetry or SafeTelemetry()
        self._max_attempts = max_attempts
        self._new_source_id = new_source_id

    def record_report(
        self,
        evidence: Evidence,
        *,
        request_id: str | None = None,
    ) -> DomainEvent:
        """Append the raw report. Admission enforces channel authentication for VERIFIED."""
        event = self._ledger.append_event(
            EventDraft(
                event_type=EventType.OBSERVATION_REPORTED,
                child_id=evidence.child_id,
                source=evidence.source,
                actor=evidence.observer,
                occurred_at=evidence.captured_at,
                verification_status=evidence.provenance.verification_status,
                payload=ObservationReported(evidence=evidence, request_id=request_id),
            )
        )
        self._telemetry.emit(
            "ingest.raw",
            {
                "child_id": evidence.child_id,
                "evidence_id": evidence.evidence_id,
                "event_id": event.event_id,
                "source_kind": evidence.source.kind.value,
                "actor_kind": evidence.observer.kind.value,
                "verification_status": event.verification_status.value,
                "request_id": request_id or "",
            },
        )
        return event

    def structure(self, child_id: str, evidence_id: str) -> StructuringOutcome:
        state = self._ledger.replay_events(child_id)
        attempt = state.structuring_failures.get(evidence_id, 0) + 1
        if attempt > self._max_attempts:
            return StructuringOutcome(evidence_id, False, (), ("STRUCTURING_BUDGET_EXHAUSTED",))
        task = AgentTask(
            task_id=f"structure-{evidence_id[4:20]}-{attempt}",
            child_id=child_id,
            goal="Structure this raw report as one observation; keep the observer's words.",
            context_entity_ids=(evidence_id,),
            max_steps=3,
            max_cost_micro_usd=2_000_000,
            proposal_kinds=_STRUCTURING_KINDS,
        )
        try:
            result = self._runtime.run(task)
        except Exception as exc:  # the runtime is untrusted infrastructure
            return self._fail(child_id, evidence_id, attempt, (f"RUNTIME_{type(exc).__name__}",))
        report = self._boundary.admit(task, result, allowed_kinds=set(_STRUCTURING_KINDS))
        entities = self._ledger.replay_events(child_id).entities
        admitted = tuple(
            o.entity_id
            for o in report.admitted("observation")
            if o.entity_id is not None and evidence_id in entities[o.entity_id].entity.evidence_ids
        )
        if admitted:
            self._telemetry.emit(
                "ingest.structured",
                {"child_id": child_id, "evidence_id": evidence_id, "count": len(admitted)},
            )
            return StructuringOutcome(evidence_id, True, admitted, ())
        reasons = report.reason_codes or tuple(
            r.split(":", 1)[0] for o in report.refused() for r in o.reason_codes
        )
        if report.abstentions and not reasons:
            reasons = ("MODEL_ABSTAINED",)
        return self._fail(child_id, evidence_id, attempt, reasons or ("NO_OBSERVATION_PROPOSED",))

    def _fail(
        self, child_id: str, evidence_id: str, attempt: int, reasons: tuple[str, ...]
    ) -> StructuringOutcome:
        codes = tuple(dict.fromkeys(_reason_code(r) for r in reasons))[:8]
        self._ledger.append_event(
            EventDraft(
                event_type=EventType.OBSERVATION_STRUCTURING_FAILED,
                child_id=child_id,
                source=SourceRef(kind=SourceKind.KERNEL, source_id=self._new_source_id()),
                actor=self._system,
                occurred_at=self._clock.now(),
                verification_status=VerificationStatus.NOT_APPLICABLE,
                payload=ObservationStructuringFailed(
                    evidence_id=evidence_id, attempt=attempt, reason_codes=codes
                ),
            )
        )
        self._telemetry.emit(
            "ingest.structuring_failed",
            {
                "child_id": child_id,
                "evidence_id": evidence_id,
                "attempt": attempt,
                "reason_codes": codes,
                "retryable": attempt < self._max_attempts,
            },
        )
        return StructuringOutcome(evidence_id, False, (), codes)


def _reason_code(reason: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in reason.upper())
    cleaned = cleaned.strip("_") or "UNKNOWN"
    if not cleaned[0].isalpha():
        cleaned = "R_" + cleaned
    return cleaned[:64]
