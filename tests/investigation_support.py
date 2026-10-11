"""Scripted Hermes replies and wiring for investigation tests and evals."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from serene.adapters.cfoai import TableCostModel
from serene.adapters.hermes import HermesAgentRuntime, wire_response
from serene.adapters.hermes.transport import HermesRequest, HermesResponse
from serene.adapters.telegram import (
    InMemoryPromptRegistry,
    RecordingOutbox,
    StaticBindingRegistry,
    TelegramBinding,
    TelegramChannel,
    TelegramPrompter,
)
from serene.investigation.assembly import KernelActors, RuntimeStack, build_stack
from serene.investigation.service import InvestigationBudget
from tests.runtime_support import (
    PSEUDONYM_KEY,
    InMemoryMemory,
    live_hypothesis_ids_in,
    observation_ids_in,
)

Reply = Callable[[HermesRequest], HermesResponse]
SECRET = "w" * 32
PARENT_TG = 101
CAREGIVER_TG = 202


def form_reply(hypotheses: Sequence[dict[str, Any]], *, pattern: str = "Pickups are hard") -> Reply:
    """Pattern over all visible observations + the given competing hypotheses."""

    def reply(request: HermesRequest) -> HermesResponse:
        observations = observation_ids_in(request)
        proposals: list[dict[str, Any]] = [
            {
                "kind": "pattern",
                "ref": "P1",
                "observation_ids": observations,
                "description": pattern,
                "contexts": ["daycare_pickup"],
            }
        ]
        for i, h in enumerate(hypotheses, start=1):
            proposals.append(
                {
                    "kind": "hypothesis",
                    "ref": f"H{i}",
                    "pattern_refs": ["P1"],
                    "statement": h["statement"],
                    "known_confounders": h.get("confounders", ["variable nap length"]),
                    "falsification_criteria": h.get("falsify", ["pattern continues regardless"]),
                    "contexts": ["daycare_pickup"],
                }
            )
        return wire_response({"proposals": proposals})

    return reply


def plan_reply(make: Callable[[list[str]], list[dict[str, Any]]]) -> Reply:
    """Candidates built from the live hypothesis ids shown in the context (in order)."""

    def reply(request: HermesRequest) -> HermesResponse:
        return wire_response({"candidates": make(live_hypothesis_ids_in(request))})

    return reply


def no_change_reply() -> Reply:
    return lambda request: wire_response(
        {"proposals": [{"kind": "abstain", "reason": "evidence does not warrant revision"}]}
    )


@dataclass
class InvestigationRig:
    stack: RuntimeStack
    family: Any
    transport: Any
    sink: Any
    channel: TelegramChannel
    prompter: TelegramPrompter
    outbox: RecordingOutbox
    prompts: InMemoryPromptRegistry
    runtime: HermesAgentRuntime

    def events(self) -> list[Any]:
        return self.stack.ledger.get_events_for_child(self.family.child_id)

    def phase(self, inv: str) -> str:
        return self.stack.ledger.replay_events(self.family.child_id).investigation_phases[inv].value


def make_investigation_rig(
    seed: str = "inv",
    *,
    memory: dict[str, str] | None = None,
    evidence: Any = None,
    budget: InvestigationBudget | None = None,
    browse_allowlist: Sequence[str] = ("example.org",),
    store: Any = None,
    clock: Any = None,
    resume_counter: int = 0,
    transport: Any = None,
    browse_sources: Sequence[str] = (),
) -> InvestigationRig:
    """`store`/`clock`/`resume_counter` simulate a process restart over an existing ledger.
    `transport` replaces the scripted Hermes wire (live evaluation runs);
    `browse_sources` are the pinned pages the planner is told about."""
    from serene.adapters.hermes import ScriptedHermesTransport
    from serene.adapters.in_memory_event_store import InMemoryEventStore
    from serene.observability.telemetry import RecordingSink, SafeTelemetry
    from serene.testing import SyntheticFamily

    family = (
        SyntheticFamily(seed=seed, store=store or InMemoryEventStore())
        if clock is None
        else SyntheticFamily(seed=seed, store=store or InMemoryEventStore(), clock=clock)
    )
    family._counter = max(family._counter, resume_counter)  # never re-mint an existing id
    sink = RecordingSink()
    telemetry = SafeTelemetry(sink, pseudonym_key=PSEUDONYM_KEY)
    family.ledger._telemetry = telemetry
    transport = transport if transport is not None else ScriptedHermesTransport()
    actors = KernelActors(
        agent=family.agent, system=family.system, verifier=family.verifier, policy=family.policy
    )
    holder: dict[str, HermesAgentRuntime] = {}

    def runtime_factory(retriever: Any, kernel_actors: KernelActors) -> HermesAgentRuntime:
        runtime = HermesAgentRuntime(
            transport,
            context_provider=lambda task: retriever.retrieve(
                family.ledger.replay_events(task.child_id),
                child_id=task.child_id,
                investigation_id=task.investigation_id,
                focus_ids=task.context_entity_ids,
                now=family.clock.now(),
            ),
            clock=family.clock,
            agent_actor=kernel_actors.agent,
            telemetry=telemetry,
            new_entity_id=family.new_id,
            browse_sources=browse_sources,
        )
        holder["runtime"] = runtime
        return runtime

    bindings = StaticBindingRegistry.of(
        [
            TelegramBinding(
                telegram_user_id=PARENT_TG, child_id=family.child_id, actor=family.parent
            ),
            TelegramBinding(
                telegram_user_id=CAREGIVER_TG, child_id=family.child_id, actor=family.caregiver
            ),
        ]
    )
    counter = iter(range(1, 100_000))
    prompts = InMemoryPromptRegistry(token_factory=lambda: f"{next(counter):016x}")
    outbox = RecordingOutbox(sent=[])
    prompter = TelegramPrompter(family.ledger, prompts, outbox, bindings)
    stack = build_stack(
        family.ledger,
        family.clock,
        runtime_factory=runtime_factory,
        memory=InMemoryMemory(dict(memory or {})),
        telemetry=telemetry,
        cost_model=TableCostModel({"acquire:BROWSE": 2_000, "acquire:ASK_PARENT": 0}),
        browse_allowlist=browse_allowlist,
        evidence=evidence(family, telemetry, transport) if callable(evidence) else evidence,
        asker=prompter,
        approvals=prompter,
        actors=actors,
        budget=budget,
        new_entity_id=family.new_id,
    )
    channel = TelegramChannel(
        webhook_secret=SECRET,
        bindings=bindings,
        ledger=family.ledger,
        clock=family.clock,
        ingestion=stack.ingestion,
        prompts=prompts,
        telemetry=telemetry,
    )
    return InvestigationRig(
        stack, family, transport, sink, channel, prompter, outbox, prompts, holder["runtime"]
    )


class TelegramScript:
    """Drive the authenticated Telegram ingress like a parent's phone would."""

    def __init__(self, rig: InvestigationRig) -> None:
        self.rig = rig
        self.update_id = 10_000

    def _post(self, update: dict[str, Any]) -> Any:
        import json

        return self.rig.channel.handle(
            {"X-Telegram-Bot-Api-Secret-Token": SECRET}, json.dumps(update).encode("utf-8")
        )

    def say(self, text: str, *, sender: int = PARENT_TG) -> Any:
        from datetime import timedelta

        self.rig.family.clock.advance(timedelta(days=1))  # one report per day
        self.update_id += 1
        return self._post(
            {
                "update_id": self.update_id,
                "message": {
                    "message_id": self.update_id,
                    "date": 1,
                    "chat": {"id": sender, "type": "private"},
                    "from": {"id": sender, "is_bot": False},
                    "text": text,
                },
            }
        )

    def tap_last(self, button: int, *, sender: int = PARENT_TG) -> Any:
        _chat, _text, buttons = self.rig.outbox.sent[-1]
        self.update_id += 1
        return self._post(
            {
                "update_id": self.update_id,
                "callback_query": {
                    "id": str(self.update_id),
                    "from": {"id": sender, "is_bot": False},
                    "message": {
                        "message_id": self.rig.outbox.next_message_id,
                        "date": 1,
                        "chat": {"id": sender, "type": "private"},
                    },
                    "data": buttons[button][1],
                },
            }
        )
