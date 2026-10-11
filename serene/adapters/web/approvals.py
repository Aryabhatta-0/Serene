"""Parent approval decisions from the web app (issue #37).

    web app --(authenticated parent, WebApprovalCommand)--> WebApprovalChannel
      -> APPROVAL_GRANTED / APPROVAL_REJECTED with a WEB_APP ChannelReceipt
      -> EventLedger.append_event: admission re-runs serene.policies.approval
         (requested parent, open request, expiry, receipt replay, the exact
         intervention digest and safety class the parent was shown, RED never
         approvable, AMBER deliberation, safety class unchanged since request)

The command carries what the parent was *shown* (the intervention digest and
safety class), so a grant binds to exactly that intervention; if it has changed
since, admission refuses. Nothing the web app sends can approve RED: the channel
refuses it before appending, and admission refuses it again.

Authentication is the transport's job, not this module's: `principal` must be
the opaque PARENT actor the transport resolved from a verified session. No
transport is wired yet; see the blocker linked from issue #37.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Final

from pydantic import StringConstraints

from serene.domain.base import ApprovalRequestId, KernelModel, Sha256Hex, new_id
from serene.domain.events import (
    ApprovalGranted,
    ApprovalRejected,
    ChannelReceipt,
    EventDraft,
    EventPayload,
    EventType,
    SafetyClass,
)
from serene.domain.values import ActorKind, ActorRef, SourceKind, SourceRef, VerificationStatus
from serene.ledger.service import AdmissionRejected, EventLedger
from serene.ports.clock import Clock

RECEIPT_PREFIX: Final = "web-decision:"


class WebDecision(StrEnum):
    APPROVE = "APPROVE"
    DECLINE = "DECLINE"


class WebApprovalCommand(KernelModel):
    """What the web app sends when a parent approves or declines one request."""

    approval_request_id: ApprovalRequestId
    decision: WebDecision
    # Exactly what the parent was shown; a grant binds to it.
    shown_intervention_digest: Sha256Hex
    shown_safety_class: SafetyClass
    # Client-generated, single-use: the receipt's message_ref, so a retried
    # submission is recognised as a replay instead of a second decision.
    request_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{16,64}$")]


@dataclass(frozen=True, slots=True)
class WebDecisionResult:
    """The ledger's answer. `outcome` is the appended event type, or REFUSED."""

    outcome: str
    event_ids: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.outcome != "REFUSED"


def _refused(*reasons: str) -> WebDecisionResult:
    return WebDecisionResult("REFUSED", (), tuple(reasons))


class WebApprovalChannel:
    def __init__(
        self,
        ledger: EventLedger,
        clock: Clock,
        *,
        new_source_id: Callable[[], str] = lambda: new_id("src"),
    ) -> None:
        self._ledger = ledger
        self._clock = clock
        self._new_source_id = new_source_id

    def decide(
        self, principal: ActorRef, child_id: str, command: WebApprovalCommand
    ) -> WebDecisionResult:
        if principal.kind is not ActorKind.PARENT:
            return _refused("APPROVER_NOT_PARENT")
        approve = command.decision is WebDecision.APPROVE
        if approve and command.shown_safety_class is SafetyClass.RED:
            return _refused("RED_CANNOT_BE_APPROVED")
        state = self._ledger.replay_events(child_id)
        request = state.approvals.get(command.approval_request_id)
        if request is None:
            return _refused("UNKNOWN_APPROVAL_REQUEST")
        if approve and request.safety_class is SafetyClass.RED:
            return _refused("RED_CANNOT_BE_APPROVED")

        receipt = ChannelReceipt(
            channel=SourceKind.WEB_APP,
            message_ref=f"{RECEIPT_PREFIX}{command.request_id}",
            received_at=self._clock.now(),
        )
        payload: EventPayload
        if approve:
            event_type = EventType.APPROVAL_GRANTED
            payload = ApprovalGranted(
                approval_request_id=command.approval_request_id,
                intervention_digest=command.shown_intervention_digest,
                acknowledged_safety_class=command.shown_safety_class,
                receipt=receipt,
            )
        else:
            event_type = EventType.APPROVAL_REJECTED
            payload = ApprovalRejected(
                approval_request_id=command.approval_request_id, receipt=receipt
            )
        try:
            event = self._ledger.append_event(
                EventDraft(
                    event_type=event_type,
                    child_id=child_id,
                    source=SourceRef(kind=SourceKind.WEB_APP, source_id=self._new_source_id()),
                    actor=principal,
                    occurred_at=self._clock.now(),
                    verification_status=VerificationStatus.NOT_APPLICABLE,
                    payload=payload,
                )
            )
        except AdmissionRejected as exc:
            return WebDecisionResult("REFUSED", (), exc.reason_codes)
        return WebDecisionResult(event_type.value, (event.event_id,))
