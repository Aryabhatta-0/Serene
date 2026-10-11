"""Canonical Maya fixture. Only model/browser I/O is scripted; authority is real."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from serene.adapters.browser import HermesBrowser
from serene.adapters.git_memory import GitMemoryRepository
from serene.adapters.hermes import HermesAgentRuntime, ScriptedHermesTransport, wire_response
from serene.adapters.telegram import (
    InMemoryPromptRegistry,
    RecordingOutbox,
    StaticBindingRegistry,
    TelegramBinding,
    TelegramChannel,
    TelegramPrompter,
)
from serene.domain.entities import Evidence, Observation
from serene.domain.values import SourceKind
from serene.evidence.service import EvidenceService
from serene.evidence.verifier import FetchedPage, IndependentEvidenceVerifier
from serene.experiments.lifecycle import LifecycleContext
from serene.experiments.service import ExperimentLifecycleService
from serene.investigation.assembly import KernelActors, build_stack
from serene.observability.telemetry import RecordingSink, SafeTelemetry
from serene.testing import SyntheticFamily
from serene.testing.synthetic import T0

SEED = "maya-daycare-pickup-v1"
SECRET = "synthetic-maya-webhook-only"  # noqa: S105 - offline fixture, never a credential
PARENT = 101
URL = "https://example.org/synthetic-daycare/pickup"
PAGE = "Synthetic daycare pickup policy. A five-minute warning precedes pickup."
HYPOTHESES = (
    "Fatigue after daycare contributes to pickup distress",
    "Hunger before pickup contributes to distress",
    "Abrupt transitions at pickup contribute to distress",
)


class SyntheticPageFetcher:
    """Pinned synthetic source for the independent verifier; no network capability."""

    def fetch(self, url: str, allowed_domains: tuple[str, ...]) -> FetchedPage | None:
        return FetchedPage(url=URL, text=PAGE) if url == URL else None


class MayaDemo:
    def __init__(self, memory_root: Path, *, seed: str = SEED) -> None:
        self.family = f = SyntheticFamily(seed=seed)
        self.transport = ScriptedHermesTransport()
        self.sink = RecordingSink()
        self.telemetry = SafeTelemetry(self.sink, pseudonym_key=b"synthetic-maya-demo-key")
        self.repo = GitMemoryRepository.init(memory_root, created_at=T0, clock=f.clock)
        bindings = StaticBindingRegistry.of(
            [TelegramBinding(telegram_user_id=PARENT, child_id=f.child_id, actor=f.parent)]
        )
        tokens = iter(range(1, 100))
        self.prompts = InMemoryPromptRegistry(token_factory=lambda: f"{next(tokens):016x}")
        self.outbox = RecordingOutbox(sent=[])
        prompter = TelegramPrompter(f.ledger, self.prompts, self.outbox, bindings)
        browser = HermesBrowser(
            self.transport,
            clock=f.clock,
            observer=f.system,
            telemetry=self.telemetry,
            new_entity_id=f.new_id,
            pinned_sources=(URL,),
        )
        evidence = EvidenceService(
            f.ledger,
            f.clock,
            browser=browser,
            verifier=IndependentEvidenceVerifier(f.clock, fetcher=SyntheticPageFetcher()),
            system_actor=f.system,
            verifier_actor=f.verifier,
            telemetry=self.telemetry,
            new_source_id=lambda: f.new_id("src"),
        )

        def runtime_factory(retriever: Any, actors: KernelActors) -> HermesAgentRuntime:
            return HermesAgentRuntime(
                self.transport,
                context_provider=lambda task: retriever.retrieve(
                    f.state(),
                    child_id=f.child_id,
                    investigation_id=task.investigation_id,
                    focus_ids=task.context_entity_ids,
                    now=f.clock.now(),
                ),
                clock=f.clock,
                agent_actor=actors.agent,
                telemetry=self.telemetry,
                new_entity_id=f.new_id,
                browse_sources=(URL,),
            )

        self.stack = build_stack(
            f.ledger,
            f.clock,
            runtime_factory=runtime_factory,
            memory=self.repo,
            telemetry=self.telemetry,
            browse_allowlist=("example.org",),
            evidence=evidence,
            asker=prompter,
            approvals=prompter,
            actors=KernelActors(f.agent, f.system, f.verifier, f.policy),
            new_entity_id=f.new_id,
        )
        self.channel = TelegramChannel(
            webhook_secret=SECRET,
            bindings=bindings,
            ledger=f.ledger,
            clock=f.clock,
            ingestion=self.stack.ingestion,
            prompts=self.prompts,
            telemetry=self.telemetry,
            namespace=f"maya-demo:{seed}",
            new_source_id=lambda: f.new_id("src"),
        )
        self.lifecycle = ExperimentLifecycleService(
            f.ledger,
            f.clock,
            LifecycleContext(f.policy, f.system, lambda: f.new_id("src")),
            new_entity_id=f.new_id,
        )
        self.update_id = 0

    def post(self, payload: dict[str, Any]) -> str:
        self.update_id += 1
        result = self.channel.handle(
            {"X-Telegram-Bot-Api-Secret-Token": SECRET},
            json.dumps({"update_id": self.update_id, **payload}).encode(),
        )
        if result.http_status != 200 or result.outcome == "REJECTED":
            raise RuntimeError(f"Telegram fixture failed: {result}")
        return result.outcome

    def say(self, text: str) -> str:
        f = self.family
        f.clock.advance(timedelta(days=1))
        evidence_ids = [
            r.entity.evidence_id
            for r in f.state().entities.values()
            if isinstance(r.entity, Evidence)
        ]
        # Resolve the newly ingested report at response time, after Telegram admission.
        self.transport.push(
            "propose",
            lambda request: wire_response(
                {
                    "proposals": [
                        {
                            "kind": "observation",
                            "evidence_ids": [
                                next(
                                    r.entity.evidence_id
                                    for r in f.state().entities.values()
                                    if isinstance(r.entity, Evidence)
                                    and r.entity.evidence_id not in evidence_ids
                                )
                            ],
                            "statement": text,
                            "contexts": ["daycare_pickup"],
                        }
                    ]
                }
            ),
        )
        return self.post(
            {
                "message": {
                    "message_id": self.update_id + 1,
                    "date": 1,
                    "chat": {"id": PARENT, "type": "private"},
                    "from": {"id": PARENT, "is_bot": False},
                    "text": text,
                }
            }
        )

    def tap(self, button: int) -> str:
        return self.post(
            {
                "callback_query": {
                    "id": str(self.update_id + 1),
                    "from": {"id": PARENT, "is_bot": False},
                    "message": {
                        "message_id": self.outbox.next_message_id,
                        "date": 1,
                        "chat": {"id": PARENT, "type": "private"},
                    },
                    "data": self.outbox.sent[-1][2][button][1],
                }
            }
        )

    def open_investigation(self) -> str:
        f = self.family
        for text in (
            "Synthetic Maya cried at daycare pickup, then settled in the car",
            "Synthetic Maya cried again at pickup after an ordinary daycare nap",
            "Synthetic Maya resisted leaving daycare despite her usual snack",
        ):
            if self.say(text) != "RECORDED_STRUCTURED":
                raise RuntimeError("Maya observation was not structured")
        inv = self.stack.investigations.open(
            f.child_id,
            "Why are synthetic Maya's daycare pickups hard?",
            opened_by=f.parent,
            source=f.source(SourceKind.TELEGRAM),
        )
        observations = [
            r.entity.observation_id
            for r in f.state().entities.values()
            if isinstance(r.entity, Observation)
        ]
        proposals: list[dict[str, Any]] = [
            {
                "kind": "pattern",
                "ref": "P1",
                "observation_ids": observations,
                "description": "Synthetic Maya has repeated distress at daycare pickup",
                "contexts": ["daycare_pickup"],
            }
        ]
        proposals.extend(
            {
                "kind": "hypothesis",
                "ref": f"H{i}",
                "pattern_refs": ["P1"],
                "statement": statement,
                "contexts": ["daycare_pickup"],
                "known_confounders": ["variable nap length", "ordinary snack timing"],
                "falsification_criteria": ["calm pickups continue without the proposed change"],
            }
            for i, statement in enumerate(HYPOTHESES)
        )
        self.transport.push("propose", wire_response({"proposals": proposals}))
        self.plan(inv, "calmer_after_snack", human=True)
        steps = self.stack.investigations.drive(f.child_id, inv)
        if steps[-1].action != "WAITING_FOR_PARENT":
            raise RuntimeError(f"Maya did not ask a parent: {steps}")
        return inv

    def plan(self, inv: str, field: str, *, human: bool = False) -> None:
        hyps = self.family.state().investigation_hypotheses[inv]
        candidate: dict[str, Any] = {
            "candidate_id": field,
            "requested_fields": [field],
            "acquisition_mode": "ASK_PARENT" if human else "BROWSE",
            "rationale": "Missing evidence distinguishes hunger, fatigue and transitions",
            "predictions": [
                {"hypothesis_id": h, "expected": answer}
                for h, answer in zip(hyps, ("UNSURE", "YES", "NO"), strict=True)
            ],
        }
        if human:
            candidate["question"] = "Was synthetic Maya calmer after her usual snack?"
        else:
            candidate.update(subject="daycare_pickup", allowed_domains=["example.org"])
        self.transport.push("plan_evidence", wire_response({"candidates": [candidate]}))
