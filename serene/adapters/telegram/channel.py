"""Authenticated Telegram ingress (issues #9, #40).

Accepts a Telegram `Update` exactly as Telegram (or the Hermes gateway relay)
delivers it, with Telegram's `X-Telegram-Bot-Api-Secret-Token` header:

* no/incorrect secret        -> 401, nothing is read or recorded;
* unbound sender / group     -> ignored (Telegram ids never reach the ledger);
* text message               -> OBSERVATION_REPORTED, byte-faithful, VERIFIED as a
                                channel-authenticated first-hand report, then a
                                separate structuring attempt (fail closed);
* button callback            -> only the exact prompt interaction (token, user,
                                chat, message, unused) yields a parent event:
                                APPROVAL_GRANTED / APPROVAL_REJECTED with a
                                `ChannelReceipt`, or a micro-answer report.

Text that says "approve", "yes, go ahead" or anything else is always just an
observation. Every outcome is idempotent: Telegram redelivery of the same
update is detected by deterministic ids and reported as DUPLICATE.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from pydantic import ValidationError

from serene.adapters.telegram.bindings import BindingRegistry, TelegramBinding
from serene.adapters.telegram.prompts import (
    ANSWERS,
    APPROVE,
    REJECT,
    InMemoryPromptRegistry,
    PendingPrompt,
    PromptKind,
)
from serene.adapters.telegram.updates import TgCallbackQuery, TgMessage, TgUpdate
from serene.domain.base import new_id
from serene.domain.events import (
    ApprovalGranted,
    ApprovalRejected,
    ChannelReceipt,
    EventDraft,
    EventPayload,
    EventType,
)
from serene.domain.values import ActorKind, SourceKind, SourceRef, VerificationStatus
from serene.evidence.ingestion import ObservationIngestion, report_evidence
from serene.evidence.micro_answer import MicroAnswer, MicroAnswerValue, encode_micro_answer
from serene.ledger.service import AdmissionRejected, EventLedger
from serene.observability.telemetry import SafeTelemetry
from serene.ports.clock import Clock

SECRET_HEADER: Final = "x-telegram-bot-api-secret-token"  # noqa: S105 - header name
MAX_BODY_BYTES: Final = 64_000
_CALLBACK = re.compile(r"^(apr|mq):([0-9a-f]{16}):([ARYNU])$")
# Kernel refusals that a later tap on the same prompt can legitimately overcome
# (e.g. an AMBER grant tapped inside the deliberation window). The prompt token
# survives these; every other refusal burns it.
RETRYABLE_REFUSALS: Final = frozenset({"AMBER_DELIBERATION_TOO_SHORT"})


@dataclass(frozen=True, slots=True)
class ChannelResult:
    http_status: int
    outcome: str
    event_ids: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()


class TelegramChannel:
    def __init__(
        self,
        *,
        webhook_secret: str,
        bindings: BindingRegistry,
        ledger: EventLedger,
        clock: Clock,
        ingestion: ObservationIngestion,
        prompts: InMemoryPromptRegistry,
        telemetry: SafeTelemetry | None = None,
        namespace: str = "serene-telegram",
        structure_reports: bool = True,
        new_source_id: Callable[[], str] = lambda: new_id("src"),
    ) -> None:
        if len(webhook_secret) < 16:
            raise ValueError("TELEGRAM_WEBHOOK_SECRET must be set (>=16 chars); refusing to run")
        self._secret = webhook_secret.encode("utf-8")
        self._bindings = bindings
        self._ledger = ledger
        self._clock = clock
        self._ingestion = ingestion
        self._prompts = prompts
        self._telemetry = telemetry or SafeTelemetry()
        self._namespace = namespace
        self._structure = structure_reports
        self._new_source_id = new_source_id

    # ------------------------------------------------------------------ entry
    def handle(self, headers: Mapping[str, str], body: bytes) -> ChannelResult:
        supplied = next((v for k, v in headers.items() if k.lower() == SECRET_HEADER), "")
        if not hmac.compare_digest(supplied.encode("utf-8"), self._secret):
            return self._result(ChannelResult(401, "UNAUTHENTICATED"), "auth")
        if len(body) > MAX_BODY_BYTES:
            return self._result(ChannelResult(413, "TOO_LARGE"), "auth")
        try:
            update = TgUpdate.model_validate_json(body)
        except ValidationError:
            return self._result(ChannelResult(400, "MALFORMED_UPDATE"), "parse")
        if update.callback_query is not None:
            return self._result(self._callback(update, update.callback_query), "callback")
        if update.message is not None:
            return self._result(self._message(update, update.message), "message")
        return self._result(ChannelResult(200, "IGNORED_UNSUPPORTED"), "other")

    # ------------------------------------------------------------------ text
    def _message(self, update: TgUpdate, message: TgMessage) -> ChannelResult:
        sender = message.from_
        if sender is None or sender.is_bot or message.chat.type != "private":
            return ChannelResult(200, "IGNORED_NOT_PRIVATE_HUMAN")
        binding = self._bindings.lookup(sender.id)
        if binding is None:
            return ChannelResult(200, "IGNORED_UNBOUND")
        if not message.text:
            return ChannelResult(200, "IGNORED_NO_TEXT")
        evidence = report_evidence(
            child_id=binding.child_id,
            observer=binding.actor,
            content=message.text,  # byte-faithful: never trimmed or normalized
            source=SourceRef(kind=SourceKind.TELEGRAM, source_id=self._derived("src", update)),
            captured_at=self._clock.now(),
            evidence_id=self._derived("evd", update),
            verified=True,
        )
        try:
            event = self._ingestion.record_report(evidence)
        except AdmissionRejected as exc:
            return _refusal(exc)
        if self._structure:
            outcome = self._ingestion.structure(binding.child_id, evidence.evidence_id)
            outcome_code = "RECORDED_STRUCTURED" if outcome.structured else "RECORDED_UNSTRUCTURED"
            return ChannelResult(200, outcome_code, (event.event_id,), outcome.reason_codes)
        return ChannelResult(200, "RECORDED", (event.event_id,))

    # ------------------------------------------------------------------ buttons
    def _callback(self, update: TgUpdate, cq: TgCallbackQuery) -> ChannelResult:
        match = _CALLBACK.match(cq.data or "")
        if match is None:
            return ChannelResult(200, "IGNORED_UNKNOWN_CALLBACK")
        kind, token, action = PromptKind(match.group(1)), match.group(2), match.group(3)
        binding = self._bindings.lookup(cq.from_.id)
        if binding is None:
            return ChannelResult(200, "IGNORED_UNBOUND")
        prompt = self._prompts.get(token)
        reasons = _prompt_mismatch(prompt, kind, binding, cq)
        if reasons or prompt is None:
            return ChannelResult(200, "REJECTED", reason_codes=tuple(reasons))
        if kind is PromptKind.APPROVAL:
            return self._decision(update, cq, prompt, binding, action)
        return self._answer(update, prompt, binding, action)

    def _decision(
        self,
        update: TgUpdate,
        cq: TgCallbackQuery,
        prompt: PendingPrompt,
        binding: TelegramBinding,
        action: str,
    ) -> ChannelResult:
        if action not in (APPROVE, REJECT):
            return ChannelResult(200, "REJECTED", reason_codes=("INVALID_ACTION",))
        if binding.actor.kind is not ActorKind.PARENT:
            return ChannelResult(200, "REJECTED", reason_codes=("APPROVER_NOT_PARENT",))
        receipt = ChannelReceipt(
            channel=SourceKind.TELEGRAM,
            message_ref=f"tg-callback:{cq.id}",
            received_at=self._clock.now(),
        )
        payload: EventPayload
        if action == APPROVE:
            if prompt.shown_digest is None or prompt.shown_safety_class is None:
                return ChannelResult(200, "REJECTED", reason_codes=("PROMPT_INCOMPLETE",))
            event_type = EventType.APPROVAL_GRANTED
            payload = ApprovalGranted(
                approval_request_id=prompt.ref_id,
                intervention_digest=prompt.shown_digest,
                acknowledged_safety_class=prompt.shown_safety_class,
                receipt=receipt,
            )
        else:
            event_type = EventType.APPROVAL_REJECTED
            payload = ApprovalRejected(approval_request_id=prompt.ref_id, receipt=receipt)
        try:
            event = self._ledger.append_event(
                EventDraft(
                    event_type=event_type,
                    child_id=binding.child_id,
                    source=SourceRef(
                        kind=SourceKind.TELEGRAM, source_id=self._derived("src", update)
                    ),
                    actor=binding.actor,
                    occurred_at=self._clock.now(),
                    verification_status=VerificationStatus.NOT_APPLICABLE,
                    payload=payload,
                )
            )
        except AdmissionRejected as exc:
            if not set(exc.reason_codes) <= RETRYABLE_REFUSALS:
                self._prompts.consume(prompt.token)  # a refused decision is not replayable
            return _refusal(exc)
        self._prompts.consume(prompt.token)
        return ChannelResult(200, event_type.value, (event.event_id,))

    def _answer(
        self, update: TgUpdate, prompt: PendingPrompt, binding: TelegramBinding, action: str
    ) -> ChannelResult:
        if action not in ANSWERS or prompt.question is None:
            return ChannelResult(200, "REJECTED", reason_codes=("INVALID_ACTION",))
        answer = MicroAnswer(
            request_id=prompt.ref_id,
            question=prompt.question,
            answer=MicroAnswerValue(ANSWERS[action]),
        )
        evidence = report_evidence(
            child_id=binding.child_id,
            observer=binding.actor,
            content=encode_micro_answer(answer),
            source=SourceRef(kind=SourceKind.TELEGRAM, source_id=self._derived("src", update)),
            captured_at=self._clock.now(),
            evidence_id=self._derived("evd", update),
            verified=True,
        )
        try:
            event = self._ingestion.record_report(evidence, request_id=prompt.ref_id)
        except AdmissionRejected as exc:
            return _refusal(exc)
        self._prompts.consume(prompt.token)
        return ChannelResult(200, "ANSWER_RECORDED", (event.event_id,))

    # ------------------------------------------------------------------ helpers
    def _derived(self, prefix: str, update: TgUpdate) -> str:
        digest = hashlib.sha256(
            f"{self._namespace}:{prefix}:{update.update_id}".encode()
        ).hexdigest()
        return f"{prefix}_{digest[:32]}"

    def _result(self, result: ChannelResult, update_kind: str) -> ChannelResult:
        self._telemetry.emit(
            "telegram.update",
            {
                "update_kind": update_kind,
                "status": result.outcome,
                "decision": "ACCEPTED" if result.event_ids else "NO_EVENT",
                "reason_codes": tuple(r.split(":", 1)[0] for r in result.reason_codes),
                "count": len(result.event_ids),
            },
        )
        return result


def _prompt_mismatch(
    prompt: PendingPrompt | None, kind: PromptKind, binding: TelegramBinding, cq: TgCallbackQuery
) -> list[str]:
    if prompt is None:
        return ["UNKNOWN_PROMPT"]
    reasons: list[str] = []
    if prompt.consumed:
        reasons.append("PROMPT_ALREADY_USED")
    if prompt.kind is not kind:
        reasons.append("PROMPT_KIND_MISMATCH")
    if prompt.telegram_user_id != cq.from_.id:
        reasons.append("WRONG_USER")
    if prompt.child_id != binding.child_id:
        reasons.append("WRONG_CHILD")
    if (
        cq.message is None
        or prompt.message_id is None
        or cq.message.message_id != prompt.message_id
        or cq.message.chat.id != prompt.chat_id
    ):
        reasons.append("MESSAGE_MISMATCH")
    return reasons


def _refusal(exc: AdmissionRejected) -> ChannelResult:
    duplicate = any(r.startswith("DUPLICATE_ENTITY") for r in exc.reason_codes)
    return ChannelResult(200, "DUPLICATE" if duplicate else "REJECTED", (), exc.reason_codes)
