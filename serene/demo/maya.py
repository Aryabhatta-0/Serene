"""Canonical Maya fixture. Only model/browser I/O is scripted; authority is real."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from serene.adapters.browser import HermesBrowser
from serene.adapters.git_memory import GitMemoryRepository
from serene.adapters.hermes import HermesAgentRuntime, ScriptedHermesTransport, wire_response
from serene.adapters.hermes.transport import HermesToolCall, HermesTransportError
from serene.adapters.telegram import (
    InMemoryPromptRegistry,
    RecordingOutbox,
    StaticBindingRegistry,
    TelegramBinding,
    TelegramChannel,
    TelegramPrompter,
)
from serene.causal import build_causal_twin
from serene.domain.entities import Evidence, Observation
from serene.domain.events import EventType
from serene.domain.values import ActorKind, ActorRef, ModelRef, SourceKind
from serene.evidence.service import EvidenceService
from serene.evidence.verifier import FetchedPage, IndependentEvidenceVerifier
from serene.experiments.lifecycle import LifecycleContext
from serene.experiments.service import ExperimentLifecycleService
from serene.investigation.assembly import KernelActors, build_stack
from serene.memory.committer import MemoryCommitter
from serene.memory.consolidation import run_consolidation
from serene.memory.dream import DreamContext, DreamDraft, DreamPipeline
from serene.observability.telemetry import RecordingSink, SafeTelemetry
from serene.testing import SyntheticFamily
from serene.testing.synthetic import SYNTHETIC_MODEL, T0

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
            max_transport_retries=0,  # expose the one injected failure to ledger-counted recovery
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
        candidate: dict[str, Any] = {
            "candidate_id": field,
            "requested_fields": [field],
            "acquisition_mode": "ASK_PARENT" if human else "BROWSE",
            "rationale": "Missing evidence distinguishes hunger, fatigue and transitions",
        }
        if human:
            candidate["question"] = "Was synthetic Maya calmer after her usual snack?"
        else:
            candidate.update(subject="daycare_pickup", allowed_domains=["example.org"])

        def reply(request: Any) -> Any:
            hyps = self.family.state().investigation_hypotheses[inv]
            candidate["predictions"] = [
                {"hypothesis_id": h, "expected": answer}
                for h, answer in zip(hyps, ("NO", "YES", "NO"), strict=True)
            ]
            return wire_response({"candidates": [candidate]})

        self.transport.push("plan_evidence", reply)

    def browse_reply(self, field: str, *, unsuitable: bool) -> None:
        excerpt = (
            "Synthetic daycare pickup policy. Pickup notice is unnecessary." if unsuitable else PAGE
        )
        value = "unnecessary" if unsuitable else "five-minute"
        self.transport.push(
            "browse",
            wire_response(
                {
                    "captures": [
                        {
                            "url": URL,
                            "subject": "daycare_pickup",
                            "effective_date": "2026-09-01",
                            "fields": {field: value},
                            "excerpt": excerpt,
                        }
                    ]
                },
                tool_calls=(
                    HermesToolCall(
                        call_id="synthetic-page-read",
                        name="web_extract",
                        arguments=json.dumps({"urls": [URL]}),
                        output=excerpt,
                    ),
                ),
            ),
        )

    def abstain(self) -> None:
        self.transport.push(
            "propose",
            wire_response(
                {
                    "proposals": [
                        {
                            "kind": "abstain",
                            "reason": "Retain competitors; seek suitable missing evidence",
                        }
                    ]
                }
            ),
        )

    def run(self) -> dict[str, Any]:
        """Run all eighteen beats; fail visibly if any runtime step fails."""
        f = self.family
        inv = self.open_investigation()
        before = build_causal_twin(f.state(), f.clock.now()).model_dump(mode="json")
        if self.tap(1) != "ANSWER_RECORDED":  # NO: the snack did not settle the distress
            raise RuntimeError("Missing parent answer")
        self.abstain()
        for _ in range(2):  # evaluating selects, NEEDS_EVIDENCE records the selected item
            self.plan(inv, "pickup_notice")
        self.transport.push("browse", HermesTransportError("TRANSIENT", "INJECTED_DEMO_FAILURE"))
        retry = self.stack.investigations.drive(f.child_id, inv)
        if retry[-1].action != "RETRY_SCHEDULED":
            raise RuntimeError(f"Injected failure did not schedule recovery: {retry}")
        self.browse_reply("pickup_notice", unsuitable=True)
        self.abstain()
        for _ in range(2):
            self.plan(inv, "warning_duration")
        self.browse_reply("warning_duration", unsuitable=False)

        # The real verifier must reject the first excerpt before this proposal is admitted.
        def experiment(request: Any) -> Any:
            hyps = f.state().investigation_hypotheses[inv]
            return wire_response(
                {
                    "proposals": [
                        {
                            "kind": "experiment",
                            "hypothesis_ref": hyps[2],
                            "category": "TRANSITION_SUPPORT",
                            "description": "Give a five-minute heads-up before leaving daycare",
                            "reversible": True,
                            "max_duration_days": 7,
                            "burden": "LOW",
                            "comparison": "usual pickups in the prior week without a heads-up",
                            "outcome_measure": "parent-reported calm pickup (yes/no)",
                        }
                    ]
                }
            )

        self.transport.push("propose", experiment)
        approval = self.stack.investigations.drive(f.child_id, inv)
        if approval[-1].action != "WAITING_FOR_APPROVAL":
            raise RuntimeError(f"Maya never reached approval: {approval}")
        if self.tap(0) != "APPROVAL_GRANTED":
            raise RuntimeError("Missing exact-interaction parent approval")
        self.abstain()
        self.transport.push("plan_evidence", wire_response({"candidates": []}))
        self.stack.investigations.drive(f.child_id, inv)
        (record,) = f.state().experiments.values()
        exp = record.experiment
        baseline_observations = {k for k in f.state().entities if k.startswith("obs_")}
        self.say("Synthetic Maya had a calm pickup after the five-minute heads-up")
        self.say("Synthetic Maya had another calm pickup with the heads-up")
        state = f.state()
        # SyntheticFamily is the existing fixture builder; keep its lineage index in sync
        # with entities produced through the runtime, rather than building another ladder.
        f.introduced_by.update({k: r.introduced_by for k, r in state.entities.items()})
        observations = tuple(
            r.entity
            for k, r in state.entities.items()
            if isinstance(r.entity, Observation) and k not in baseline_observations
        )
        f.outcome(exp, observations)
        completion = self.lifecycle.complete(f.child_id, exp.experiment_id)
        learning = self.lifecycle.promote_to_learning(
            f.child_id, exp.hypothesis_id, reviewer=f.parent
        )
        if completion.refused or learning.refused or not f.state().learnings:
            raise RuntimeError(f"Promotion failed: {completion} {learning}")
        learning_id = next(iter(f.state().learnings))
        dreamer = MayaDreamer(f.agent, learning_id, observations[0].observation_id)
        committer = MemoryCommitter(
            f.ledger,
            self.repo,
            f.clock,
            committer=ActorRef(kind=ActorKind.MEMORY_COMMITTER, actor_id=f.new_id("act")),
            policy=f.policy,
            new_source_id=lambda: f.new_id("src"),
        )
        consolidation = run_consolidation(
            DreamPipeline(
                f.ledger,
                self.repo,
                dreamer,
                f.clock,
                system=f.system,
                new_entity_id=f.new_id,
            ),
            committer,
            f.child_id,
        )
        if len(consolidation.committed) != 1 or len(consolidation.rejected) != 1:
            raise RuntimeError("Dream did not accept one patch and reject one patch")
        events = f.ledger.get_events_for_child(f.child_id)
        if not f.ledger.verify_hash_chain(f.child_id).ok:
            raise RuntimeError("Demo ledger hash chain invalid")
        return {
            "fixture": SEED,
            "seed": f.seed,
            "synthetic": True,
            "mode": "offline-scripted-io",
            "investigation_id": inv,
            "events": [e.model_dump(mode="json") for e in events],
            "prompts": [
                {"text": text, "buttons": [b[0] for b in buttons]}
                for _, text, buttons in self.outbox.sent
            ],
            "twin_before": before,
            "twin_after": build_causal_twin(f.state(), f.clock.now()).model_dump(mode="json"),
            "memory": {
                p: doc.content
                for p in self.repo.list_paths("")
                if (doc := self.repo.read(p)) is not None
            },
            "memory_head": self.repo.head(),
            "dream_rejections": [list(r.reason_codes) for r in consolidation.rejected],
            "phase": f.state().investigation_phases[inv].value,
            "hash_chain_valid": True,
            "browser_calls": sum(r.purpose == "browse" for r in self.transport.requests),
            "retry_action": retry[-1].action,
            "event_counts": {
                kind.value: sum(e.event_type is kind for e in events)
                for kind in EventType
                if any(e.event_type is kind for e in events)
            },
        }


class MayaDreamer:
    """Two synthetic model drafts, reviewed by the production Dream Critic."""

    model: ModelRef | None = SYNTHETIC_MODEL

    def __init__(self, actor: ActorRef, learning: str, observation: str) -> None:
        self.actor, self.learning, self.observation = actor, learning, observation

    def reflect(self, context: DreamContext) -> list[DreamDraft]:
        return [
            DreamDraft(
                self.learning,
                "learnings/maya-pickup.md",
                "Weekday pickup heads-up",
                "Synthetic Maya's weekday daycare pickups were calmer with a heads-up. "
                "This scoped synthetic result does not establish a universal cause.",
            ),
            DreamDraft(
                self.observation,
                "child/every-transition.md",
                "Universal transition rule",
                "Maya always needs a warning for every transition everywhere.",
            ),
        ]
