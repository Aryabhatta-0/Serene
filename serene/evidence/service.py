"""Evidence acquisition + verification service (issues #15, #16, #50).

Connects the bounded browser and the independent verifier to the ledger. All
state lives in the ledger, so a crash or restart resumes from facts:

    acquire(child, request)
        open BROWSE request only (answered / exhausted -> no dispatch, idempotent)
        attempt = ledger-counted failures + 1
        browser.acquire(bounds rebuilt from EVIDENCE_REQUESTED)
          ACQUIRED  -> one EVIDENCE_ACQUIRED (SYSTEM, UNVERIFIED) per capture
          otherwise -> EVIDENCE_ACQUISITION_FAILED(attempt, failure, retryable)
        retryable only for TRANSIENT / MALFORMED and only while attempts remain;
        BLOCKED / NOT_FOUND / BUDGET_EXHAUSTED exhaust the request at once.

    verify_pending(child, request)
        for each UNVERIFIED evidence acquired for the request:
          verifier.verify(evidence, bounds) -> EVIDENCE_VERIFIED | EVIDENCE_REJECTED
          (VERIFIER actor). If admission refuses a VERIFIED verdict, the evidence
          is rejected with the admission reasons instead: never left ambiguous,
          never verified by anyone but the verifier.

Browsing is read-only, so a crash between the browser returning and the
append simply re-browses on resume (no external effect is duplicated; the
attempt is not counted twice because nothing was recorded).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from serene.domain.base import new_id
from serene.domain.entities import Evidence
from serene.domain.events import (
    AcquisitionFailure,
    AcquisitionMode,
    EventDraft,
    EventPayload,
    EventType,
    EvidenceAcquired,
    EvidenceAcquisitionFailed,
    EvidenceRejected,
    EvidenceVerified,
)
from serene.domain.values import ActorRef, SourceKind, SourceRef, VerificationStatus
from serene.ledger.service import AdmissionRejected, EventLedger
from serene.observability.telemetry import SafeTelemetry
from serene.ports.clock import Clock
from serene.ports.evidence import (
    EvidenceBrowser,
    EvidenceBrowseRequest,
    EvidenceBrowseResult,
    EvidenceVerifier,
    VerificationVerdict,
)
from serene.projections.state import EvidenceRequestRecord, KernelState

MAX_ACQUISITION_ATTEMPTS: Final = 3
DEFAULT_MAX_ACTIONS: Final = 12
_RETRYABLE: Final = frozenset({AcquisitionFailure.TRANSIENT, AcquisitionFailure.MALFORMED})
# Browser FAILED results whose reasons show the reply itself was unusable.
_MALFORMED_PREFIXES: Final = ("WIRE_", "CAPTURE_")
# ...or that the model runtime refused service: retrying cannot help until an operator acts.
_UNAVAILABLE_REASONS: Final = frozenset(
    {"TRANSPORT_AUTH", "TRANSPORT_REFUSED", "TRANSPORT_PROTOCOL"}
)
_STATUS_FAILURE: Final = {
    "NOT_FOUND": AcquisitionFailure.NOT_FOUND,
    "BLOCKED": AcquisitionFailure.BLOCKED,
    "BUDGET_EXHAUSTED": AcquisitionFailure.BUDGET_EXHAUSTED,
    "FAILED": AcquisitionFailure.TRANSIENT,
}


@dataclass(frozen=True, slots=True)
class AcquisitionOutcome:
    request_id: str
    status: str  # ACQUIRED | FAILED | NOT_OPEN | NOT_A_BROWSE_REQUEST | UNKNOWN_REQUEST
    evidence_ids: tuple[str, ...] = ()
    failure: AcquisitionFailure | None = None
    retryable: bool = False
    reason_codes: tuple[str, ...] = ()


class EvidenceService:
    def __init__(
        self,
        ledger: EventLedger,
        clock: Clock,
        *,
        browser: EvidenceBrowser,
        verifier: EvidenceVerifier,
        system_actor: ActorRef,
        verifier_actor: ActorRef,
        telemetry: SafeTelemetry | None = None,
        new_source_id: Callable[[], str] = lambda: new_id("src"),
        max_attempts: int = MAX_ACQUISITION_ATTEMPTS,
        max_actions: int = DEFAULT_MAX_ACTIONS,
    ) -> None:
        self._ledger = ledger
        self._clock = clock
        self._browser = browser
        self._verifier = verifier
        self._system = system_actor
        self._verifier_actor = verifier_actor
        self._telemetry = telemetry or SafeTelemetry()
        self._new_source_id = new_source_id
        self._max_attempts = max_attempts
        self._max_actions = max_actions

    # ------------------------------------------------------------------ bounds
    def browse_request(self, child_id: str, record: EvidenceRequestRecord) -> EvidenceBrowseRequest:
        """The browser's bounds, rebuilt from the ledger's EVIDENCE_REQUESTED only."""
        req = record.request
        return EvidenceBrowseRequest(
            request_id=req.request_id,
            child_id=child_id,
            goal=req.rationale,
            allowed_domains=req.allowed_domains,
            requested_fields=req.requested_fields,
            max_actions=self._max_actions,
            subject=req.subject,
            max_age_days=req.max_age_days,
        )

    # ------------------------------------------------------------------ acquire
    def acquire(self, child_id: str, request_id: str) -> AcquisitionOutcome:
        state = self._ledger.replay_events(child_id)
        record = state.evidence_requests.get(request_id)
        if record is None:
            return AcquisitionOutcome(request_id, "UNKNOWN_REQUEST")
        if record.request.acquisition_mode is not AcquisitionMode.BROWSE:
            return AcquisitionOutcome(request_id, "NOT_A_BROWSE_REQUEST")
        if not record.open:
            return AcquisitionOutcome(
                request_id, "NOT_OPEN", tuple(record.evidence_ids), reason_codes=("NO_DISPATCH",)
            )
        attempt = record.failed_attempts + 1
        bounds = self.browse_request(child_id, record)
        try:
            result = self._browser.acquire(bounds)
        except Exception:  # a crashing browser is a transient dependency failure
            return self._fail(
                child_id, request_id, attempt, AcquisitionFailure.TRANSIENT, ("BROWSER_ERROR",)
            )
        problems = _result_problems(result, bounds)
        if problems:
            return self._fail(child_id, request_id, attempt, AcquisitionFailure.MALFORMED, problems)
        if result.status != "ACQUIRED":
            failure = _STATUS_FAILURE[result.status]
            if failure is AcquisitionFailure.TRANSIENT:
                if _UNAVAILABLE_REASONS.intersection(result.reason_codes):
                    failure = AcquisitionFailure.UNAVAILABLE
                elif any(r.startswith(_MALFORMED_PREFIXES) for r in result.reason_codes):
                    failure = AcquisitionFailure.MALFORMED
            return self._fail(
                child_id,
                request_id,
                attempt,
                failure,
                result.reason_codes or (f"BROWSER_{result.status}",),
            )
        admitted: list[str] = []
        refused: list[str] = []
        for evidence in result.evidence:
            try:
                self._append(
                    EventType.EVIDENCE_ACQUIRED,
                    child_id,
                    EvidenceAcquired(request_id=request_id, evidence=evidence),
                    actor=self._system,
                    status=VerificationStatus.UNVERIFIED,
                    source=evidence.source,
                    occurred_at=evidence.captured_at,
                )
                admitted.append(evidence.evidence_id)
            except AdmissionRejected as exc:
                refused += [r.split(":", 1)[0] for r in exc.reason_codes]
        if not admitted:
            return self._fail(
                child_id,
                request_id,
                attempt,
                AcquisitionFailure.BLOCKED,
                tuple(dict.fromkeys(refused)) or ("NO_EVIDENCE_ADMITTED",),
            )
        self._telemetry.emit(
            "evidence.acquired",
            {
                "child_id": child_id,
                "request_id": request_id,
                "attempt": attempt,
                "count": len(admitted),
                "action_count": result.actions_used,
                "refused": len(refused),
            },
        )
        return AcquisitionOutcome(
            request_id, "ACQUIRED", tuple(admitted), reason_codes=tuple(dict.fromkeys(refused))
        )

    def _fail(
        self,
        child_id: str,
        request_id: str,
        attempt: int,
        failure: AcquisitionFailure,
        reasons: tuple[str, ...],
    ) -> AcquisitionOutcome:
        retryable = failure in _RETRYABLE and attempt < self._max_attempts
        codes = tuple(dict.fromkeys(reasons))[:32]
        self._append(
            EventType.EVIDENCE_ACQUISITION_FAILED,
            child_id,
            EvidenceAcquisitionFailed(
                request_id=request_id,
                attempt=attempt,
                failure=failure,
                retryable=retryable,
                reason_codes=codes,
            ),
            actor=self._system,
            status=VerificationStatus.NOT_APPLICABLE,
        )
        self._telemetry.emit(
            "evidence.acquisition_failed",
            {
                "child_id": child_id,
                "request_id": request_id,
                "attempt": attempt,
                "failure": failure.value,
                "retryable": retryable,
                "reason_codes": codes,
            },
        )
        return AcquisitionOutcome(
            request_id, "FAILED", failure=failure, retryable=retryable, reason_codes=codes
        )

    # ------------------------------------------------------------------ verify
    def verify_pending(self, child_id: str, request_id: str) -> tuple[VerificationVerdict, ...]:
        state = self._ledger.replay_events(child_id)
        record = state.evidence_requests.get(request_id)
        if record is None or record.request.acquisition_mode is not AcquisitionMode.BROWSE:
            return ()
        bounds = self.browse_request(child_id, record)
        verdicts: list[VerificationVerdict] = []
        for evidence_id in record.evidence_ids:
            evidence = _pending_evidence(state, evidence_id)
            if evidence is None:
                continue  # already decided (idempotent on resume)
            verdicts.append(self._decide(child_id, evidence, bounds))
        return tuple(verdicts)

    def _decide(
        self, child_id: str, evidence: Evidence, bounds: EvidenceBrowseRequest
    ) -> VerificationVerdict:
        try:
            verdict = self._verifier.verify(evidence, bounds)
        except Exception:  # a verifier that cannot decide rejects, never verifies
            verdict = VerificationVerdict(
                evidence_id=evidence.evidence_id,
                verdict="REJECTED",
                reason_codes=("VERIFIER_ERROR",),
                verifier_version="unavailable",
            )
        if verdict.evidence_id != evidence.evidence_id:
            verdict = VerificationVerdict(
                evidence_id=evidence.evidence_id,
                verdict="REJECTED",
                reason_codes=("VERDICT_FOR_OTHER_EVIDENCE",),
                verifier_version=verdict.verifier_version,
            )
        if verdict.verdict == "VERIFIED":
            try:
                self._record(child_id, verdict)
                return verdict
            except AdmissionRejected as exc:
                verdict = VerificationVerdict(
                    evidence_id=evidence.evidence_id,
                    verdict="REJECTED",
                    checks_passed=verdict.checks_passed,
                    reason_codes=exc.reason_codes[:32],
                    verifier_version=verdict.verifier_version,
                )
        self._record(child_id, verdict)
        return verdict

    def _record(self, child_id: str, verdict: VerificationVerdict) -> None:
        payload: EventPayload
        if verdict.verdict == "VERIFIED":
            event_type, status = EventType.EVIDENCE_VERIFIED, VerificationStatus.VERIFIED
            payload = EvidenceVerified(
                evidence_id=verdict.evidence_id,
                checks_passed=verdict.checks_passed,
                verifier_version=verdict.verifier_version,
            )
        else:
            event_type, status = EventType.EVIDENCE_REJECTED, VerificationStatus.REJECTED
            payload = EvidenceRejected(
                evidence_id=verdict.evidence_id,
                reason_codes=verdict.reason_codes or ("VERIFICATION_FAILED",),
                verifier_version=verdict.verifier_version,
            )
        self._append(event_type, child_id, payload, actor=self._verifier_actor, status=status)
        self._telemetry.emit(
            "evidence.verdict",
            {
                "child_id": child_id,
                "evidence_id": verdict.evidence_id,
                "decision": verdict.verdict,
                "checks_passed": tuple(c.value for c in verdict.checks_passed),
                "reason_codes": verdict.reason_codes,
                "verifier_version": verdict.verifier_version,
            },
        )

    # ------------------------------------------------------------------ ledger
    def _append(
        self,
        event_type: EventType,
        child_id: str,
        payload: EventPayload,
        *,
        actor: ActorRef,
        status: VerificationStatus,
        source: SourceRef | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        self._ledger.append_event(
            EventDraft(
                event_type=event_type,
                child_id=child_id,
                source=source or SourceRef(kind=SourceKind.KERNEL, source_id=self._new_source_id()),
                actor=actor,
                occurred_at=occurred_at or self._clock.now(),
                verification_status=status,
                payload=payload,
            )
        )


def _pending_evidence(state: KernelState, evidence_id: str) -> Evidence | None:
    record = state.entities.get(evidence_id)
    if record is None or record.verification_status is not VerificationStatus.UNVERIFIED:
        return None
    return record.entity if isinstance(record.entity, Evidence) else None


def _result_problems(
    result: EvidenceBrowseResult, bounds: EvidenceBrowseRequest
) -> tuple[str, ...]:
    """Browser output is untrusted: it must answer *this* request for *this* child."""
    problems: list[str] = []
    if result.request_id != bounds.request_id:
        problems.append("RESULT_FOR_OTHER_REQUEST")
    if result.actions_used > bounds.max_actions and result.status == "ACQUIRED":
        problems.append("ACTION_BUDGET_EXCEEDED")
    if result.status == "ACQUIRED" and not result.evidence:
        problems.append("ACQUIRED_WITHOUT_EVIDENCE")
    for evidence in result.evidence:
        if evidence.child_id != bounds.child_id:
            problems.append("EVIDENCE_FOR_OTHER_CHILD")
        if evidence.provenance.verification_status is not VerificationStatus.UNVERIFIED:
            problems.append("BROWSER_CLAIMED_VERIFICATION")
    return tuple(dict.fromkeys(problems))
