"""One consolidation cycle: Dream proposes, the Critic reviews, the Committer decides.

    collect recent experiences -> Dreamer proposes patch -> Critic searches
    contradictions -> provenance verifier checks lineage -> Promotion Gate checks
    authority -> MemoryCommitter commits OR rejects

The Dream pipeline and the committer are separate objects with separate
capabilities; this module only sequences them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from serene.memory.committer import CommitOutcome, MemoryCommitter
from serene.memory.dream import DreamPipeline, DreamReport


@dataclass(frozen=True, slots=True)
class ConsolidationResult:
    dream: DreamReport
    outcomes: tuple[CommitOutcome, ...]

    @property
    def committed(self) -> tuple[CommitOutcome, ...]:
        return tuple(o for o in self.outcomes if o.committed)

    @property
    def rejected(self) -> tuple[CommitOutcome, ...]:
        return tuple(o for o in self.outcomes if not o.committed)


def run_consolidation(
    pipeline: DreamPipeline,
    committer: MemoryCommitter,
    child_id: str,
    *,
    since: datetime | None = None,
) -> ConsolidationResult:
    report = pipeline.run(child_id, since=since)
    outcomes = tuple(committer.process(child_id, patch_id) for patch_id in report.proposed)
    return ConsolidationResult(report, outcomes)
