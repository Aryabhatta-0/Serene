"""Builders for memory / Dream tests: a synthetic ledger plus a throwaway Git memory repo."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from serene.adapters.git_memory import GitMemoryRepository
from serene.domain.values import ActorKind, ActorRef
from serene.memory.committer import MemoryCommitter
from serene.memory.dream import DreamContext, DreamDraft, DreamPipeline, TemplateDreamer
from serene.testing import SyntheticFamily
from serene.testing.synthetic import SYNTHETIC_MODEL, T0


@dataclass
class MemoryStack:
    fam: SyntheticFamily
    repo: GitMemoryRepository
    committer: MemoryCommitter
    committer_actor: ActorRef

    def pipeline(self, dreamer: object | None = None) -> DreamPipeline:
        return DreamPipeline(
            self.fam.ledger,
            self.repo,
            dreamer or TemplateDreamer(self.fam.system),  # type: ignore[arg-type]
            self.fam.clock,
            system=self.fam.system,
            new_entity_id=self.fam.new_id,
        )


def memory_stack(fam: SyntheticFamily, root: Path) -> MemoryStack:
    repo = GitMemoryRepository.init(root, created_at=T0, clock=fam.clock)
    actor = ActorRef(kind=ActorKind.MEMORY_COMMITTER, actor_id=fam.new_id("act"))
    committer = MemoryCommitter(
        fam.ledger,
        repo,
        fam.clock,
        committer=actor,
        policy=fam.policy,
        new_source_id=lambda: fam.new_id("src"),
    )
    return MemoryStack(fam, repo, committer, actor)


class ScriptedModelDreamer:
    """Stands in for an LLM Dreamer: proposes whatever it is told, attributed to a model."""

    model = SYNTHETIC_MODEL

    def __init__(self, actor: ActorRef, drafts: Sequence[DreamDraft]) -> None:
        assert actor.kind is ActorKind.AGENT
        self.actor = actor
        self._drafts = list(drafts)

    def reflect(self, context: DreamContext) -> Sequence[DreamDraft]:
        return list(self._drafts)
