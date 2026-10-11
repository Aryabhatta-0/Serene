"""Wiring for the branch-A runtime path (one place, used by app/, eval/ and tests).

The kernel's own actors are stable, derived identities so that a restart (or
a second process) stamps the same AGENT / SYSTEM / VERIFIER actor ids.
Nothing here carries authority: every component appends only through
`EventLedger.append_event`, which re-runs admission.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from serene.domain.base import new_id
from serene.domain.values import ActorKind, ActorRef
from serene.evidence.ingestion import ObservationIngestion
from serene.experiments.lifecycle import LifecycleContext
from serene.experiments.service import ExperimentLifecycleService
from serene.investigation.boundary import KernelBoundary
from serene.investigation.context import ContextRetriever
from serene.investigation.minimum_data import EvidencePlanner, MinimumDataPolicy
from serene.investigation.service import (
    ApprovalPrompter,
    EvidenceActions,
    InvestigationBudget,
    InvestigationService,
    QuestionAsker,
)
from serene.ledger.service import EventLedger
from serene.observability.telemetry import SafeTelemetry
from serene.ports.agent_runtime import AgentRuntime
from serene.ports.clock import Clock
from serene.ports.cost import CostModel
from serene.ports.memory import MemoryRepository


def kernel_actor(kind: ActorKind, namespace: str = "serene") -> ActorRef:
    digest = hashlib.sha256(f"{namespace}:kernel-actor:{kind.value}".encode()).hexdigest()
    return ActorRef(kind=kind, actor_id=f"act_{digest[:32]}")


@dataclass(frozen=True, slots=True)
class KernelActors:
    agent: ActorRef
    system: ActorRef
    verifier: ActorRef
    policy: ActorRef | None = None  # None: the derived kernel POLICY identity

    @classmethod
    def derived(cls, namespace: str = "serene") -> KernelActors:
        return cls(
            agent=kernel_actor(ActorKind.AGENT, namespace),
            system=kernel_actor(ActorKind.SYSTEM, namespace),
            verifier=kernel_actor(ActorKind.VERIFIER, namespace),
            policy=kernel_actor(ActorKind.POLICY, namespace),
        )


class _NoCost:
    def estimate_cost_micro_usd(self, option_id: str) -> int | None:
        return None


@dataclass(frozen=True, slots=True)
class RuntimeStack:
    ledger: EventLedger
    clock: Clock
    telemetry: SafeTelemetry
    actors: KernelActors
    retriever: ContextRetriever
    boundary: KernelBoundary
    ingestion: ObservationIngestion
    investigations: InvestigationService


def build_stack(
    ledger: EventLedger,
    clock: Clock,
    *,
    runtime_factory: Callable[[ContextRetriever, KernelActors], AgentRuntime],
    planner: EvidencePlanner | None = None,
    memory: MemoryRepository | None = None,
    telemetry: SafeTelemetry | None = None,
    cost_model: CostModel | None = None,
    browse_allowlist: Sequence[str] = (),
    evidence: EvidenceActions | None = None,
    asker: QuestionAsker | None = None,
    approvals: ApprovalPrompter | None = None,
    actors: KernelActors | None = None,
    budget: InvestigationBudget | None = None,
    new_entity_id: Callable[[str], str] = new_id,
) -> RuntimeStack:
    telemetry = telemetry or SafeTelemetry()
    actors = actors or KernelActors.derived()
    retriever = ContextRetriever(memory)
    runtime = runtime_factory(retriever, actors)
    boundary = KernelBoundary(
        ledger,
        clock,
        agent_actor=actors.agent,
        telemetry=telemetry,
        new_source_id=lambda: new_entity_id("src"),
    )
    ingestion = ObservationIngestion(
        ledger,
        clock,
        runtime=runtime,
        boundary=boundary,
        system_actor=actors.system,
        telemetry=telemetry,
        new_source_id=lambda: new_entity_id("src"),
    )
    if planner is None:
        if not isinstance(runtime, EvidencePlanner):
            raise ValueError("an EvidencePlanner is required (the Hermes runtime is one)")
        planner = runtime
    investigations = InvestigationService(
        ledger,
        clock,
        runtime=runtime,
        planner=planner,
        boundary=boundary,
        retriever=retriever,
        policy=MinimumDataPolicy(cost_model or _NoCost(), browse_allowlist=browse_allowlist),
        system_actor=actors.system,
        evidence=evidence,
        asker=asker,
        telemetry=telemetry,
        budget=budget,
        new_entity_id=new_entity_id,
        experiments=ExperimentLifecycleService(
            ledger,
            clock,
            LifecycleContext(
                actors.policy or kernel_actor(ActorKind.POLICY),
                actors.system,
                lambda: new_entity_id("src"),
            ),
            new_entity_id=new_entity_id,
        ),
        approvals=approvals,
    )
    return RuntimeStack(
        ledger=ledger,
        clock=clock,
        telemetry=telemetry,
        actors=actors,
        retriever=retriever,
        boundary=boundary,
        ingestion=ingestion,
        investigations=investigations,
    )
