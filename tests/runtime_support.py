"""Shared wiring for branch-A runtime tests. Synthetic data only."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from serene.adapters.hermes import HermesAgentRuntime, ScriptedHermesTransport, wire_response
from serene.adapters.hermes.runtime import TokenPricing
from serene.adapters.hermes.transport import HermesRequest, HermesResponse
from serene.domain.values import ActorKind, ActorRef
from serene.evidence.ingestion import ObservationIngestion
from serene.investigation.boundary import KernelBoundary
from serene.investigation.context import ContextRetriever
from serene.observability.telemetry import RecordingSink, SafeTelemetry
from serene.ports.agent_runtime import AgentTask
from serene.ports.memory import MemoryDocument
from serene.testing import SyntheticFamily

PSEUDONYM_KEY = b"test-pseudonym-key"
_EVD = re.compile(r"(evd_[0-9a-f]{32}) evidence")
_OBS = re.compile(r"(obs_[0-9a-f]{32}) observation")
_HYP = re.compile(r"(hyp_[0-9a-f]{32}) hypothesis level=\w+ status=ACTIVE")


def evidence_ids_in(request: HermesRequest) -> list[str]:
    return _EVD.findall(request.input)


def observation_ids_in(request: HermesRequest) -> list[str]:
    return _OBS.findall(request.input)


def live_hypothesis_ids_in(request: HermesRequest) -> list[str]:
    return _HYP.findall(request.input)


def structure_reply(statement: str, contexts: Iterable[str] = ("daycare_pickup",)) -> Any:
    """Scripted Hermes reply structuring the most recent evidence in the context."""

    def reply(request: HermesRequest) -> HermesResponse:
        evidence = evidence_ids_in(request)
        focus = re.search(r"TASK structure-([0-9a-f]{16})-", request.input)
        if focus is not None:  # the report being structured, not merely the newest one
            evidence = [e for e in evidence if e.startswith("evd_" + focus.group(1))] or evidence
        return wire_response(
            {
                "proposals": [
                    {
                        "kind": "observation",
                        "evidence_ids": [evidence[-1]],
                        "statement": statement,
                        "contexts": list(contexts),
                    }
                ]
            }
        )

    return reply


@dataclass
class InMemoryMemory:
    """Read-only MemoryRepository fake (branch B owns the real Git adapter)."""

    docs: dict[str, str] = field(default_factory=dict)

    def read(self, path: str) -> MemoryDocument | None:
        import hashlib

        if path not in self.docs:
            return None
        content = self.docs[path]
        return MemoryDocument(
            path=path,
            revision="a" * 40,
            content=content,
            content_digest=hashlib.sha256(content.encode()).hexdigest(),
        )

    def list_paths(self, prefix: str) -> list[str]:
        return sorted(p for p in self.docs if p.startswith(prefix))

    def commit(self, patch: Any, authorization: Any) -> Any:
        raise PermissionError("branch A never writes memory")


@dataclass
class Rig:
    family: SyntheticFamily
    transport: ScriptedHermesTransport
    sink: RecordingSink
    telemetry: SafeTelemetry
    retriever: ContextRetriever
    runtime: HermesAgentRuntime
    boundary: KernelBoundary
    ingestion: ObservationIngestion
    memory: InMemoryMemory

    @property
    def ledger(self) -> Any:
        return self.family.ledger

    def task(self, task_id: str = "t-1", **kwargs: Any) -> AgentTask:
        defaults: dict[str, Any] = {
            "task_id": task_id,
            "child_id": self.family.child_id,
            "goal": "test goal",
            "max_steps": 4,
            "max_cost_micro_usd": 1_000_000,
        }
        defaults.update(kwargs)
        return AgentTask(**defaults)


def make_rig(seed: str = "rig", *, memory: dict[str, str] | None = None) -> Rig:
    family = SyntheticFamily(seed=seed)
    sink = RecordingSink()
    telemetry = SafeTelemetry(sink, pseudonym_key=PSEUDONYM_KEY)
    family.ledger._telemetry = telemetry  # same privacy-safe sink for ledger spans
    transport = ScriptedHermesTransport()
    mem = InMemoryMemory(dict(memory or {}))
    retriever = ContextRetriever(mem)
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
        agent_actor=ActorRef(kind=ActorKind.AGENT, actor_id=family.new_id("act")),
        pricing=TokenPricing(
            input_micro_usd_per_mtok=3_000_000, output_micro_usd_per_mtok=15_000_000
        ),
        telemetry=telemetry,
        new_entity_id=family.new_id,
    )
    boundary = KernelBoundary(
        family.ledger,
        family.clock,
        agent_actor=family.agent,
        telemetry=telemetry,
        new_source_id=lambda: family.new_id("src"),
    )
    ingestion = ObservationIngestion(
        family.ledger,
        family.clock,
        runtime=runtime,
        boundary=boundary,
        system_actor=family.system,
        telemetry=telemetry,
        new_source_id=lambda: family.new_id("src"),
    )
    return Rig(family, transport, sink, telemetry, retriever, runtime, boundary, ingestion, mem)
