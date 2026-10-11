"""Outbound Telegram prompts and the registry of exact interactions (issue #40).

Every button Serene sends carries an unguessable one-time token bound to: the
kind of prompt, the child, the ledger object it is about (approval request or
evidence request), the Telegram user it was sent to, the exact chat/message it
was rendered in, and (for approvals) the intervention digest and safety class
the parent was shown. Only a callback matching all of those can produce a
parent event, and each token is consumed once. Typed text never resolves to a
prompt, so free text can never authorize anything.
"""

from __future__ import annotations

import json
import secrets
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Final, Protocol, runtime_checkable

from serene.adapters.telegram.bindings import BindingRegistry, TelegramBinding
from serene.domain.events import SafetyClass
from serene.domain.values import ActorKind
from serene.ledger.service import EventLedger
from serene.projections.state import OPEN_APPROVAL_STATES

APPROVE: Final = "A"
REJECT: Final = "R"
ANSWERS: Final = {"Y": "YES", "N": "NO", "U": "UNSURE"}


class PromptKind(StrEnum):
    APPROVAL = "apr"
    QUESTION = "mq"


@dataclass(frozen=True, slots=True)
class PendingPrompt:
    token: str
    kind: PromptKind
    child_id: str
    ref_id: str
    telegram_user_id: int
    chat_id: int
    message_id: int | None = None
    shown_digest: str | None = None
    shown_safety_class: SafetyClass | None = None
    question: str | None = None
    consumed: bool = False


@runtime_checkable
class PromptRegistry(Protocol):
    def issue(self, prompt: PendingPrompt) -> PendingPrompt: ...

    def attach(self, token: str, message_id: int) -> PendingPrompt: ...

    def get(self, token: str) -> PendingPrompt | None: ...

    def find(self, kind: PromptKind, ref_id: str) -> PendingPrompt | None: ...

    def consume(self, token: str) -> bool: ...


class InMemoryPromptRegistry:
    """Process-local registry. Losing it only invalidates buttons (fails closed)."""

    def __init__(self, token_factory: Callable[[], str] = lambda: secrets.token_hex(8)) -> None:
        self._prompts: dict[str, PendingPrompt] = {}
        self._new_token = token_factory

    def new_token(self) -> str:
        token = self._new_token()
        if token in self._prompts:
            raise RuntimeError("token collision")
        return token

    def issue(self, prompt: PendingPrompt) -> PendingPrompt:
        if prompt.token in self._prompts:
            raise ValueError("token already issued")
        self._prompts[prompt.token] = prompt
        return prompt

    def attach(self, token: str, message_id: int) -> PendingPrompt:
        prompt = replace(self._prompts[token], message_id=message_id)
        self._prompts[token] = prompt
        return prompt

    def get(self, token: str) -> PendingPrompt | None:
        return self._prompts.get(token)

    def find(self, kind: PromptKind, ref_id: str) -> PendingPrompt | None:
        return next(
            (p for p in self._prompts.values() if p.kind is kind and p.ref_id == ref_id), None
        )

    def consume(self, token: str) -> bool:
        prompt = self._prompts.get(token)
        if prompt is None or prompt.consumed:
            return False
        self._prompts[token] = replace(prompt, consumed=True)
        return True


Buttons = tuple[tuple[str, str], ...]


@runtime_checkable
class TelegramOutbox(Protocol):
    def send(self, chat_id: int, text: str, buttons: Buttons) -> int:
        """Deliver one message with inline buttons; return Telegram's message_id."""
        ...


@dataclass
class RecordingOutbox:
    sent: list[tuple[int, str, Buttons]]
    next_message_id: int = 1000

    def send(self, chat_id: int, text: str, buttons: Buttons) -> int:
        self.sent.append((chat_id, text, buttons))
        self.next_message_id += 1
        return self.next_message_id


class BotApiOutbox:
    """`sendMessage` via the Telegram Bot API (outbound only; does not poll)."""

    def __init__(self, bot_token: str, *, timeout_s: float = 15.0) -> None:
        if not bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._timeout = timeout_s

    def send(self, chat_id: int, text: str, buttons: Buttons) -> int:
        body = json.dumps(
            {
                "chat_id": chat_id,
                "text": text,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": label, "callback_data": data}] for label, data in buttons
                    ]
                },
            }
        ).encode("utf-8")
        request = urllib.request.Request(  # noqa: S310 - fixed https endpoint
            self._url, data=body, method="POST", headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as resp:  # noqa: S310
            payload = json.loads(resp.read(100_000).decode("utf-8"))
        if not payload.get("ok"):
            raise RuntimeError("telegram sendMessage failed")
        return int(payload["result"]["message_id"])


class TelegramPrompter:
    """Turns ledger state (pending approvals, open questions) into exact prompts."""

    def __init__(
        self,
        ledger: EventLedger,
        registry: InMemoryPromptRegistry,
        outbox: TelegramOutbox,
        bindings: BindingRegistry,
    ) -> None:
        self._ledger = ledger
        self._registry = registry
        self._outbox = outbox
        self._bindings = bindings

    def prompt_pending_approvals(self, child_id: str) -> list[PendingPrompt]:
        state = self._ledger.replay_events(child_id)
        sent: list[PendingPrompt] = []
        for apr_id, approval in sorted(state.approvals.items()):
            if approval.state not in OPEN_APPROVAL_STATES:
                continue
            if self._registry.find(PromptKind.APPROVAL, apr_id) is not None:
                continue
            binding = self._bindings.for_actor(approval.requested_of)
            if binding is None or binding.child_id != child_id:
                continue
            intervention = state.experiments[approval.experiment_id].experiment.intervention
            text = (
                f"Serene asks for your decision on a {approval.safety_class.value} experiment:\n"
                f"{intervention.description}\n"
                f"Up to {intervention.max_duration_days} days; reversible; you can stop any time.\n"
                "Tap APPROVE or REJECT. Typed replies are never treated as a decision."
            )
            prompt = PendingPrompt(
                token=self._registry.new_token(),
                kind=PromptKind.APPROVAL,
                child_id=child_id,
                ref_id=apr_id,
                telegram_user_id=binding.telegram_user_id,
                chat_id=binding.telegram_user_id,
                shown_digest=approval.intervention_digest,
                shown_safety_class=approval.safety_class,
            )
            sent.append(
                self._send(
                    prompt,
                    text,
                    (
                        ("APPROVE", f"{PromptKind.APPROVAL.value}:{prompt.token}:{APPROVE}"),
                        ("REJECT", f"{PromptKind.APPROVAL.value}:{prompt.token}:{REJECT}"),
                    ),
                )
            )
        return sent

    def ask(self, child_id: str, request_id: str) -> PendingPrompt | None:
        """Send the one micro-question of an open ASK_PARENT evidence request."""
        state = self._ledger.replay_events(child_id)
        record = state.evidence_requests.get(request_id)
        if record is None or not record.open or record.request.question is None:
            return None
        existing = self._registry.find(PromptKind.QUESTION, request_id)
        if existing is not None:
            return existing
        binding = _first_parent(self._bindings.for_child(child_id))
        if binding is None:
            return None
        prompt = PendingPrompt(
            token=self._registry.new_token(),
            kind=PromptKind.QUESTION,
            child_id=child_id,
            ref_id=request_id,
            telegram_user_id=binding.telegram_user_id,
            chat_id=binding.telegram_user_id,
            question=record.request.question,
        )
        buttons = tuple(
            (label, f"{PromptKind.QUESTION.value}:{prompt.token}:{code}")
            for code, label in ANSWERS.items()
        )
        return self._send(prompt, record.request.question, buttons)

    def _send(self, prompt: PendingPrompt, text: str, buttons: Buttons) -> PendingPrompt:
        self._registry.issue(prompt)
        message_id = self._outbox.send(prompt.chat_id, text, buttons)
        return self._registry.attach(prompt.token, message_id)


def _first_parent(bindings: tuple[TelegramBinding, ...]) -> TelegramBinding | None:
    return next((b for b in bindings if b.actor.kind is ActorKind.PARENT), None)
