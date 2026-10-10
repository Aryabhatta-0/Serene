"""Stable ports between the Domain Kernel and replaceable infrastructure.

Adapters (Hermes, Supabase/Postgres, neatlogs, cfo.ai, Git) implement these
protocols in `serene.adapters`. The kernel depends on ports, never on adapters.
"""

from serene.ports.agent_runtime import AgentProposal, AgentRunResult, AgentRuntime, AgentTask
from serene.ports.clock import Clock
from serene.ports.cost import CostModel
from serene.ports.event_store import ConcurrencyConflict, EventStore
from serene.ports.evidence import (
    EvidenceBrowser,
    EvidenceBrowseRequest,
    EvidenceBrowseResult,
    EvidenceVerifier,
    VerificationVerdict,
)
from serene.ports.memory import CommitAuthorization, CommitReceipt, MemoryDocument, MemoryRepository
from serene.ports.observability import AttributeValue, ObservabilitySink

__all__ = [
    "AgentProposal",
    "AgentRunResult",
    "AgentRuntime",
    "AgentTask",
    "AttributeValue",
    "Clock",
    "CommitAuthorization",
    "CommitReceipt",
    "ConcurrencyConflict",
    "CostModel",
    "EventStore",
    "EvidenceBrowseRequest",
    "EvidenceBrowseResult",
    "EvidenceBrowser",
    "EvidenceVerifier",
    "MemoryDocument",
    "MemoryRepository",
    "ObservabilitySink",
    "VerificationVerdict",
]
