"""AgentRuntime port: where model reasoning happens (Hermes is one adapter).

The runtime returns *proposals* in a closed, discriminated contract. Nothing a
runtime returns is authoritative: the kernel validates every proposal, stamps
the AGENT actor itself, and decides admission with deterministic policy.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal, Protocol, runtime_checkable

from pydantic import Field

from serene.domain.base import ChildId, EntityId, InvestigationId, KernelModel, ShortText, Tag
from serene.domain.entities import Experiment, Hypothesis, MemoryPatch, Observation, Pattern
from serene.domain.values import ModelRef

CONTRACT_VERSION: Final = "agent-runtime/1"
ProposalKind = Literal[
    "observation", "pattern", "hypothesis", "experiment", "memory_patch", "need_evidence", "abstain"
]


class AgentTask(KernelModel):
    contract_version: Literal["agent-runtime/1"] = CONTRACT_VERSION
    task_id: Annotated[str, Field(pattern=r"^[a-z0-9_\-]{1,64}$")]
    child_id: ChildId
    investigation_id: InvestigationId | None = None
    goal: ShortText
    # Pointers only; the adapter resolves visible context through kernel reads.
    context_entity_ids: tuple[EntityId, ...] = Field(default=(), max_length=256)
    max_steps: int = Field(ge=1, le=50)
    max_cost_micro_usd: int = Field(ge=0, le=50_000_000)
    # Additive (branch A): the proposal kinds the caller will admit, so an adapter can
    # describe only those. Empty = unspecified. The kernel boundary still enforces it.
    proposal_kinds: tuple[ProposalKind, ...] = Field(default=(), max_length=8)


class _Proposal(KernelModel):
    model: ModelRef


class ProposeObservation(_Proposal):
    kind: Literal["observation"] = "observation"
    observation: Observation


class ProposePattern(_Proposal):
    kind: Literal["pattern"] = "pattern"
    pattern: Pattern


class ProposeHypothesis(_Proposal):
    kind: Literal["hypothesis"] = "hypothesis"
    hypothesis: Hypothesis


class ProposeExperiment(_Proposal):
    kind: Literal["experiment"] = "experiment"
    experiment: Experiment


class ProposeMemoryPatch(_Proposal):
    kind: Literal["memory_patch"] = "memory_patch"
    patch: MemoryPatch


class NeedEvidence(_Proposal):
    kind: Literal["need_evidence"] = "need_evidence"
    requested_fields: tuple[Tag, ...] = Field(min_length=1, max_length=16)
    rationale: ShortText


class Abstain(_Proposal):
    kind: Literal["abstain"] = "abstain"
    reason: ShortText


AgentProposal = Annotated[
    ProposeObservation
    | ProposePattern
    | ProposeHypothesis
    | ProposeExperiment
    | ProposeMemoryPatch
    | NeedEvidence
    | Abstain,
    Field(discriminator="kind"),
]


class AgentRunResult(KernelModel):
    contract_version: Literal["agent-runtime/1"] = CONTRACT_VERSION
    task_id: str
    status: Literal["COMPLETED", "BUDGET_EXHAUSTED", "FAILED", "CANCELLED"]
    proposals: tuple[AgentProposal, ...] = Field(default=(), max_length=32)
    steps_used: int = Field(ge=0)
    cost_micro_usd: int = Field(ge=0)


@runtime_checkable
class AgentRuntime(Protocol):
    def run(self, task: AgentTask) -> AgentRunResult:
        """Run bounded reasoning for one task and return proposals only."""
        ...
