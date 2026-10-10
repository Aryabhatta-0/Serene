"""Hermes Agent adapter (placeholder seam; implemented on branch A).

Hermes (NousResearch/hermes-agent) is replaceable infrastructure: reasoning,
tools, Telegram gateway, browser and model routing. It sits *behind* the
`AgentRuntime` / `EvidenceBrowser` ports and never owns evidence truth,
promotion, safety, approval or memory authority.

This module deliberately does not import Hermes at module load, so the kernel
and its tests run without Hermes installed. Branch A replaces `run` with a
bounded call into the Hermes runtime that returns `AgentRunResult` proposals.
"""

from __future__ import annotations

from serene.ports.agent_runtime import AgentRunResult, AgentTask


class HermesNotConfigured(RuntimeError):
    pass


class HermesAgentRuntime:
    """`AgentRuntime` adapter for Hermes. Not wired yet: fails closed."""

    def __init__(self, hermes_home: str | None = None) -> None:
        self.hermes_home = hermes_home

    def run(self, task: AgentTask) -> AgentRunResult:
        raise HermesNotConfigured(
            "Hermes runtime adapter is not implemented yet (see docs/parallel-handoff.md, "
            "branch A). No proposal is produced, so nothing can enter the ledger."
        )
