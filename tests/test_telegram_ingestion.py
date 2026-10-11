"""Telegram ingestion, authentication and exact-interaction approvals (issues #9, #40)."""

from __future__ import annotations

import io
import json
from datetime import timedelta
from typing import Any

import pytest

from serene.adapters.hermes import HermesTransportError
from serene.adapters.hermes.scripted import raw_response
from serene.adapters.telegram import (
    InMemoryPromptRegistry,
    RecordingOutbox,
    StaticBindingRegistry,
    TelegramBinding,
    TelegramChannel,
    TelegramPrompter,
)
from serene.adapters.telegram.wsgi import make_wsgi_app
from serene.domain.canonical import sha256_hex
from serene.domain.events import AcquisitionMode, EventType, InformationValue
from serene.domain.values import ActorKind, ActorRef, SourceKind, VerificationStatus
from serene.evidence.micro_answer import MicroAnswerValue, decode_micro_answer
from tests.runtime_support import Rig, make_rig, structure_reply

SECRET = "s" * 32
PARENT_TG = 111_111
CAREGIVER_TG = 222_222
STRANGER_TG = 999_999


class Harness:
    def __init__(self, seed: str = "tg") -> None:
        self.rig: Rig = make_rig(seed)
        fam = self.rig.family
        self.bindings = StaticBindingRegistry.of(
            [
                TelegramBinding(
                    telegram_user_id=PARENT_TG, child_id=fam.child_id, actor=fam.parent
                ),
                TelegramBinding(
                    telegram_user_id=CAREGIVER_TG, child_id=fam.child_id, actor=fam.caregiver
                ),
            ]
        )
        counter = iter(range(1, 10_000))
        self.prompts = InMemoryPromptRegistry(token_factory=lambda: f"{next(counter):016x}")
        self.outbox = RecordingOutbox(sent=[])
        self.channel = TelegramChannel(
            webhook_secret=SECRET,
            bindings=self.bindings,
            ledger=fam.ledger,
            clock=fam.clock,
            ingestion=self.rig.ingestion,
            prompts=self.prompts,
            telemetry=self.rig.telemetry,
        )
        self.prompter = TelegramPrompter(fam.ledger, self.prompts, self.outbox, self.bindings)
        self._update_id = 500

    @property
    def fam(self) -> Any:
        return self.rig.family

    def events(self) -> list[Any]:
        return self.fam.ledger.get_events_for_child(self.fam.child_id)

    def post(self, update: dict[str, Any], secret: str = SECRET) -> Any:
        return self.channel.handle(
            {"X-Telegram-Bot-Api-Secret-Token": secret}, json.dumps(update).encode("utf-8")
        )

    def text(self, text: str, *, sender: int = PARENT_TG, chat_type: str = "private") -> Any:
        self._update_id += 1
        return self.post(
            {
                "update_id": self._update_id,
                "message": {
                    "message_id": self._update_id,
                    "date": 1_790_000_000,
                    "chat": {"id": sender, "type": chat_type},
                    "from": {"id": sender, "is_bot": False, "first_name": "Synthetic"},
                    "text": text,
                },
            }
        )

    def tap(
        self,
        data: str,
        *,
        sender: int = PARENT_TG,
        message_id: int | None = None,
        chat_id: int | None = None,
        update_id: int | None = None,
    ) -> Any:
        self._update_id += 1
        return self.post(
            {
                "update_id": update_id or self._update_id,
                "callback_query": {
                    "id": f"9{self._update_id}",
                    "from": {"id": sender, "is_bot": False},
                    "message": {
                        "message_id": message_id or self.outbox.next_message_id,
                        "date": 1_790_000_000,
                        "chat": {"id": chat_id or sender, "type": "private"},
                    },
                    "data": data,
                },
            }
        )


@pytest.fixture
def h() -> Harness:
    return Harness()


# ---------------------------------------------------------------- authentication
@pytest.mark.parametrize("secret", ["", "wrong-secret-wrong-secret", SECRET[:-1] + "x"])
def test_unauthenticated_updates_record_nothing(h: Harness, secret: str) -> None:
    h.rig.transport.push("propose", structure_reply("x"))
    result = h.post(
        {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "date": 1,
                "chat": {"id": PARENT_TG, "type": "private"},
                "from": {"id": PARENT_TG, "is_bot": False},
                "text": "hello",
            },
        },
        secret=secret,
    )
    assert result.http_status == 401 and h.events() == []


def test_channel_refuses_to_run_without_a_secret(h: Harness) -> None:
    with pytest.raises(ValueError, match="TELEGRAM_WEBHOOK_SECRET"):
        TelegramChannel(
            webhook_secret="",
            bindings=h.bindings,
            ledger=h.fam.ledger,
            clock=h.fam.clock,
            ingestion=h.rig.ingestion,
            prompts=h.prompts,
        )


def test_unbound_and_group_senders_are_ignored(h: Harness) -> None:
    assert h.text("hi", sender=STRANGER_TG).outcome == "IGNORED_UNBOUND"
    assert h.text("hi", chat_type="group").outcome == "IGNORED_NOT_PRIVATE_HUMAN"
    assert h.events() == []


def test_malformed_update_is_rejected(h: Harness) -> None:
    result = h.channel.handle({"x-telegram-bot-api-secret-token": SECRET}, b"{not json")
    assert result.http_status == 400 and h.events() == []


# ---------------------------------------------------------------- raw -> structured
RAW = 'Pickup  was hard 😢\r\nshe screamed "no" at the door…  '


def test_raw_text_is_preserved_byte_for_byte_then_structured_separately(h: Harness) -> None:
    h.rig.transport.push("propose", structure_reply("Distress at daycare pickup"))
    result = h.text(RAW)
    assert result.outcome == "RECORDED_STRUCTURED"
    raw_event, structured_event = h.events()
    assert raw_event.event_type is EventType.OBSERVATION_REPORTED
    evidence = raw_event.payload["evidence"]
    assert evidence["content"] == RAW
    assert evidence["content_digest"] == sha256_hex(RAW.encode("utf-8"))
    assert raw_event.verification_status is VerificationStatus.VERIFIED
    assert raw_event.source.kind is SourceKind.TELEGRAM
    assert raw_event.actor == h.fam.parent

    assert structured_event.event_type is EventType.OBSERVATION_STRUCTURED
    assert structured_event.derived_from == (raw_event.event_id,)
    observation = structured_event.payload["observation"]
    assert observation["evidence_ids"] == [evidence["evidence_id"]]
    assert observation["provenance"]["source_ids"] == [evidence["evidence_id"]]
    assert structured_event.actor.kind is ActorKind.AGENT


@pytest.mark.parametrize(
    "failure",
    [
        raw_response("I think she was sad"),  # malformed, and malformed again on repair
        HermesTransportError("AUTH", "HTTP_401"),
    ],
)
def test_extraction_failure_preserves_raw_and_records_failure(h: Harness, failure: Any) -> None:
    h.rig.transport.push("propose", failure, failure)
    result = h.text(RAW)
    assert result.outcome == "RECORDED_UNSTRUCTURED"
    types = [e.event_type for e in h.events()]
    assert types == [EventType.OBSERVATION_REPORTED, EventType.OBSERVATION_STRUCTURING_FAILED]
    raw = h.events()[0].payload["evidence"]
    assert raw["content"] == RAW
    assert h.fam.ledger.verify_hash_chain(h.fam.child_id).ok
    failed = h.events()[1].payload
    assert failed["evidence_id"] == raw["evidence_id"] and failed["attempt"] == 1


def test_structuring_retries_are_bounded_by_the_ledger(h: Harness) -> None:
    h.rig.transport.push("propose", HermesTransportError("AUTH", "x"))
    h.text("Pickup was hard")
    evidence_id = h.events()[0].payload["evidence"]["evidence_id"]
    for _ in range(2):
        h.rig.transport.push("propose", HermesTransportError("AUTH", "x"))
        h.rig.ingestion.structure(h.fam.child_id, evidence_id)
    outcome = h.rig.ingestion.structure(h.fam.child_id, evidence_id)
    assert outcome.reason_codes == ("STRUCTURING_BUDGET_EXHAUSTED",)
    assert h.fam.state().structuring_failures[evidence_id] == 3


def test_redelivered_update_is_idempotent(h: Harness) -> None:
    h.rig.transport.push("propose", structure_reply("hard pickup"))
    update = {
        "update_id": 42,
        "message": {
            "message_id": 7,
            "date": 1,
            "chat": {"id": PARENT_TG, "type": "private"},
            "from": {"id": PARENT_TG, "is_bot": False},
            "text": "Pickup was hard",
        },
    }
    assert h.post(update).outcome == "RECORDED_STRUCTURED"
    count = len(h.events())
    assert h.post(update).outcome == "DUPLICATE"
    assert len(h.events()) == count


def test_caregiver_reports_stay_separate_from_parent_reports(h: Harness) -> None:
    h.rig.transport.push("propose", structure_reply("calm pickup"), structure_reply("upset pickup"))
    h.text("Pickup was calm today")
    h.text("He was very upset at pickup today", sender=CAREGIVER_TG)
    reports = [e for e in h.events() if e.event_type is EventType.OBSERVATION_REPORTED]
    assert [r.actor.kind for r in reports] == [ActorKind.PARENT, ActorKind.CAREGIVER]
    assert reports[1].payload["evidence"]["kind"] == "CAREGIVER_REPORT"


# ---------------------------------------------------------------- approvals
def _pending_approval(h: Harness) -> tuple[Any, str]:
    fam = h.fam
    o1 = fam.observe("tearful pickup", day=0)
    o2 = fam.observe("tearful pickup again", day=1)
    pattern = fam.pattern((o1, o2), "pickups are tearful")
    inv = fam.open_investigation("why?")
    hyp = fam.hypothesis(inv, (pattern,), "abrupt transitions")
    exp = fam.propose_experiment(hyp)
    fam.classify(exp)
    return exp, fam.request_approval(exp)


@pytest.mark.parametrize(
    "text",
    ["APPROVE", "yes approve it", "/approve", "apr:0000000000000001:A", "I approve the experiment"],
)
def test_approval_text_alone_is_never_approval(h: Harness, text: str) -> None:
    _, apr = _pending_approval(h)
    h.prompter.prompt_pending_approvals(h.fam.child_id)
    h.rig.transport.push("propose", structure_reply("parent typed a message"))
    h.text(text)
    assert h.fam.state().approvals[apr].state.value == "PENDING"
    assert EventType.APPROVAL_GRANTED not in [e.event_type for e in h.events()]


def test_exact_interaction_grants_with_a_channel_receipt(h: Harness) -> None:
    _exp, apr = _pending_approval(h)
    (prompt,) = h.prompter.prompt_pending_approvals(h.fam.child_id)
    chat_id, text, buttons = h.outbox.sent[0]
    assert chat_id == PARENT_TG and "GREEN" in text
    assert "Typed replies are never treated as a decision" in text
    result = h.tap(buttons[0][1], message_id=prompt.message_id)
    assert result.outcome == "APPROVAL_GRANTED"
    event = h.events()[-1]
    assert event.actor == h.fam.parent and event.source.kind is SourceKind.TELEGRAM
    assert event.payload["receipt"]["channel"] == "TELEGRAM"
    assert event.payload["intervention_digest"] == prompt.shown_digest
    assert h.fam.state().approvals[apr].state.value == "GRANTED"


def test_rejection_is_recorded_from_the_exact_interaction(h: Harness) -> None:
    _, apr = _pending_approval(h)
    (prompt,) = h.prompter.prompt_pending_approvals(h.fam.child_id)
    assert h.tap(h.outbox.sent[0][2][1][1], message_id=prompt.message_id).outcome == (
        "APPROVAL_REJECTED"
    )
    assert h.fam.state().approvals[apr].state.value == "REJECTED"


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"sender": CAREGIVER_TG}, "WRONG_USER"),
        ({"message_id": 1}, "MESSAGE_MISMATCH"),
        ({"chat_id": 31337}, "MESSAGE_MISMATCH"),
    ],
)
def test_callback_must_match_the_exact_prompt(
    h: Harness, kwargs: dict[str, Any], reason: str
) -> None:
    _, apr = _pending_approval(h)
    (prompt,) = h.prompter.prompt_pending_approvals(h.fam.child_id)
    kwargs.setdefault("message_id", prompt.message_id)
    result = h.tap(h.outbox.sent[0][2][0][1], **kwargs)
    assert result.outcome == "REJECTED" and reason in result.reason_codes
    assert h.fam.state().approvals[apr].state.value == "PENDING"


def test_forged_token_and_replay_are_rejected(h: Harness) -> None:
    _, _apr = _pending_approval(h)
    (prompt,) = h.prompter.prompt_pending_approvals(h.fam.child_id)
    forged = h.tap("apr:ffffffffffffffff:A", message_id=prompt.message_id)
    assert forged.reason_codes == ("UNKNOWN_PROMPT",)
    data = h.outbox.sent[0][2][0][1]
    assert h.tap(data, message_id=prompt.message_id).outcome == "APPROVAL_GRANTED"
    replay = h.tap(data, message_id=prompt.message_id)
    assert replay.outcome == "REJECTED" and "PROMPT_ALREADY_USED" in replay.reason_codes


def test_expired_approval_is_refused_by_the_kernel(h: Harness) -> None:
    _, _apr = _pending_approval(h)
    (prompt,) = h.prompter.prompt_pending_approvals(h.fam.child_id)
    h.fam.clock.advance(timedelta(hours=25))
    result = h.tap(h.outbox.sent[0][2][0][1], message_id=prompt.message_id)
    assert result.outcome == "REJECTED" and "APPROVAL_EXPIRED" in result.reason_codes


def test_changed_intervention_cannot_reuse_an_old_prompt(h: Harness) -> None:
    from dataclasses import replace

    _, _apr = _pending_approval(h)
    (prompt,) = h.prompter.prompt_pending_approvals(h.fam.child_id)
    h.prompts._prompts[prompt.token] = replace(prompt, shown_digest="0" * 64)
    result = h.tap(h.outbox.sent[0][2][0][1], message_id=prompt.message_id)
    assert "INTERVENTION_DIGEST_MISMATCH" in result.reason_codes


# ---------------------------------------------------------------- micro-questions
def _open_question(h: Harness) -> str:
    from serene.domain.entities import InvestigationPhase as P
    from serene.domain.events import (
        EvidenceRequested,
        HypothesisPrediction,
        InvestigationPhaseChanged,
        PredictedAnswer,
    )

    fam = h.fam
    o1 = fam.observe("tearful pickup", day=0)
    o2 = fam.observe("tearful pickup again", day=1)
    pattern = fam.pattern((o1, o2), "pickups are tearful")
    inv = fam.open_investigation("why are pickups hard?")
    transitions = fam.hypothesis(inv, (pattern,), "abrupt transitions")
    hunger = fam.hypothesis(inv, (pattern,), "hunger after daycare")
    fam.append(
        fam.draft(
            EventType.INVESTIGATION_PHASE_CHANGED,
            fam.system,
            InvestigationPhaseChanged(
                investigation_id=inv.investigation_id,
                from_phase=P.FORMING_HYPOTHESES,
                to_phase=P.NEEDS_EVIDENCE,
                reason_codes=("TEST",),
            ),
        )
    )
    request_id = fam.new_id("erq")
    fam.append(
        fam.draft(
            EventType.EVIDENCE_REQUESTED,
            fam.system,
            EvidenceRequested(
                request_id=request_id,
                investigation_id=inv.investigation_id,
                requested_fields=("snack_before_pickup",),
                information_value=InformationValue.HIGH,
                rationale="discriminates hunger from transitions",
                acquisition_mode=AcquisitionMode.ASK_PARENT,
                question="Did he eat a snack before pickup today?",
                predictions=(
                    HypothesisPrediction(
                        hypothesis_id=hunger.hypothesis_id, expected=PredictedAnswer.NO
                    ),
                    HypothesisPrediction(
                        hypothesis_id=transitions.hypothesis_id, expected=PredictedAnswer.YES
                    ),
                ),
            ),
        )
    )
    return request_id


@pytest.mark.parametrize(("button", "value"), [(0, "YES"), (1, "NO"), (2, "UNSURE")])
def test_each_micro_answer_path_is_recorded_distinctly(h: Harness, button: int, value: str) -> None:
    request_id = _open_question(h)
    prompt = h.prompter.ask(h.fam.child_id, request_id)
    assert prompt is not None
    _, _text, buttons = h.outbox.sent[-1]
    assert [b[0] for b in buttons] == ["YES", "NO", "UNSURE"]
    result = h.tap(buttons[button][1], message_id=prompt.message_id)
    assert result.outcome == "ANSWER_RECORDED"
    event = h.events()[-1]
    assert event.event_type is EventType.OBSERVATION_REPORTED
    assert event.payload["request_id"] == request_id
    answer = decode_micro_answer(event.payload["evidence"]["content"])
    assert answer is not None and answer.answer is MicroAnswerValue(value)
    assert h.fam.state().evidence_requests[request_id].answered


def test_a_question_is_answered_once(h: Harness) -> None:
    request_id = _open_question(h)
    prompt = h.prompter.ask(h.fam.child_id, request_id)
    assert prompt is not None
    yes = h.outbox.sent[-1][2][0][1]
    assert h.tap(yes, message_id=prompt.message_id).outcome == "ANSWER_RECORDED"
    assert h.tap(yes, message_id=prompt.message_id).outcome == "REJECTED"
    sent = len(h.outbox.sent)
    assert h.prompter.ask(h.fam.child_id, request_id) is None  # answered: never re-asked
    assert len(h.outbox.sent) == sent


def test_micro_answer_cannot_be_used_as_an_approval(h: Harness) -> None:
    _, apr = _pending_approval(h)
    request_id = _open_question(h)
    prompt = h.prompter.ask(h.fam.child_id, request_id)
    assert prompt is not None
    forged = f"apr:{prompt.token}:A"
    result = h.tap(forged, message_id=prompt.message_id)
    assert "PROMPT_KIND_MISMATCH" in result.reason_codes
    assert h.fam.state().approvals[apr].state.value == "PENDING"


# ---------------------------------------------------------------- WSGI surface
def test_wsgi_endpoint_authenticates_and_never_echoes_content(h: Harness) -> None:
    h.rig.transport.push("propose", structure_reply("hard pickup"))
    app = make_wsgi_app(h.channel)
    body = json.dumps(
        {
            "update_id": 77,
            "message": {
                "message_id": 1,
                "date": 1,
                "chat": {"id": PARENT_TG, "type": "private"},
                "from": {"id": PARENT_TG, "is_bot": False},
                "text": "secret family detail",
            },
        }
    ).encode()
    statuses: list[str] = []

    def call(secret: str) -> bytes:
        environ = {
            "PATH_INFO": "/telegram",
            "REQUEST_METHOD": "POST",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
            "HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": secret,
        }
        return b"".join(app(environ, lambda status, headers: statuses.append(status)))

    denied = call("nope")
    assert statuses[-1].startswith("401") and b"secret family" not in denied
    ok = call(SECRET)
    assert statuses[-1].startswith("200") and b"secret family" not in ok
    assert len(h.events()) == 2


def test_telegram_telemetry_has_no_text_or_telegram_ids(h: Harness) -> None:
    h.rig.transport.push("propose", structure_reply("hard pickup"))
    h.text("My kid Sam had a meltdown at Sunny Days daycare")
    blob = json.dumps(h.rig.sink.records)
    for leaked in ("Sam", "Sunny", "meltdown", str(PARENT_TG), h.fam.child_id):
        assert leaked not in blob


def test_bindings_reject_non_human_principals(h: Harness) -> None:
    with pytest.raises(ValueError):
        TelegramBinding(
            telegram_user_id=1,
            child_id=h.fam.child_id,
            actor=ActorRef(kind=ActorKind.AGENT, actor_id=h.fam.new_id("act")),
        )


def test_each_callback_mints_a_unique_stable_receipt_ref(h: Harness) -> None:
    """Receipt replay keys (channel, message_ref) must be unique per tap and stable per tap."""
    _, apr = _pending_approval(h)
    (prompt,) = h.prompter.prompt_pending_approvals(h.fam.child_id)
    data = h.outbox.sent[0][2][0][1]
    result = h.tap(data, message_id=prompt.message_id)
    assert result.outcome == "APPROVAL_GRANTED"
    (granted,) = [e for e in h.events() if e.event_id in result.event_ids]
    ref = granted.payload["receipt"]["message_ref"]
    assert ref == f"tg-callback:9{h._update_id}"  # the Telegram callback_query id, verbatim
    assert str(PARENT_TG) not in ref  # no Telegram user/chat ids reach the ledger
    assert h.fam.state().approvals[apr].state.value == "GRANTED"


def test_retryable_kernel_refusal_keeps_the_prompt_usable(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from serene.ledger.service import AdmissionRejected

    _, apr = _pending_approval(h)
    (prompt,) = h.prompter.prompt_pending_approvals(h.fam.child_id)
    data = h.outbox.sent[0][2][0][1]
    real_append = h.fam.ledger.append_event
    calls = {"n": 0}

    def too_early(draft: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:  # first tap lands inside an AMBER deliberation window
            raise AdmissionRejected(["AMBER_DELIBERATION_TOO_SHORT"])
        return real_append(draft)

    monkeypatch.setattr(h.fam.ledger, "append_event", too_early)
    early = h.tap(data, message_id=prompt.message_id)
    assert early.outcome == "REJECTED"
    assert early.reason_codes == ("AMBER_DELIBERATION_TOO_SHORT",)
    later = h.tap(data, message_id=prompt.message_id)
    assert later.outcome == "APPROVAL_GRANTED"
    assert h.fam.state().approvals[apr].state.value == "GRANTED"
