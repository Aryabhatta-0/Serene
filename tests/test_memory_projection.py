"""Pinned Memory/Dream publication, deterministic replay and failure isolation."""

from __future__ import annotations

from pathlib import Path

import pytest

from serene.adapters.git_memory import BRANCH, GitError, GitMemoryRepository
from serene.adapters.memory_projection import publishable_projections
from serene.domain.canonical import canonical_json
from serene.ledger.service import EventLedger
from serene.observability.telemetry import RecordingSink, SafeTelemetry
from serene.projections.memory import (
    MemoryPublicationError,
    memory_dream,
    memory_review,
    privacy_checked,
)
from serene.projections.state import replay
from serene.testing import build_full_ladder

from .memory_helpers import memory_stack


def test_review_and_snapshot_rebuild_ignore_head_and_dirty_worktree(tmp_path: Path) -> None:
    fam = build_full_ladder(seed="memory-pinned")["family"]
    stack = memory_stack(fam, tmp_path / "memory")
    genesis = stack.repo.head()
    run = stack.pipeline().run(fam.child_id)
    for patch_id in run.proposed:
        stack.committer.process(fam.child_id, patch_id)
    state = fam.state()
    revision = stack.repo.head()

    def resolve(child, sha):
        return stack.repo.at_revision(sha)

    expected = canonical_json(memory_dream(state, resolve))
    review = canonical_json(memory_review(state))
    assert state.memory_commits and revision in state.memory_commits.values()
    assert memory_dream(state, resolve)["memory_head"] == revision
    assert memory_dream(state, resolve)["memories"]

    # Move the branch backwards, add private worktree bytes. Neither is read.
    stack.repo._git("update-ref", BRANCH, genesis)
    (tmp_path / "memory" / "learnings").mkdir(exist_ok=True)
    (tmp_path / "memory" / "learnings" / "private.md").write_text("private worktree")
    rebuilt = replay(fam.ledger.get_events_for_child(fam.child_id))
    assert canonical_json(memory_dream(rebuilt, resolve)) == expected
    assert canonical_json(memory_review(rebuilt)) == review
    for symbolic in ("HEAD", "main", revision[:12], "f" * 40):
        with pytest.raises(GitError, match="MEMORY_REVISION_UNAVAILABLE"):
            stack.repo.at_revision(symbolic)

    # A repo that lacks the recorded object fails rather than falling back.
    other = GitMemoryRepository.init(tmp_path / "missing", created_at=fam.clock.now())
    with pytest.raises(GitError, match="MEMORY_REVISION_UNAVAILABLE"):
        memory_dream(rebuilt, lambda child, sha: other.at_revision(sha))
    with pytest.raises(MemoryPublicationError, match="MEMORY_REVISION_MISMATCH"):
        memory_dream(rebuilt, lambda child, sha: other)


@pytest.mark.parametrize(
    "private",
    [
        "chd_" + "1" * 32,
        "act_" + "2" * 32,
        "sk-" + "q" * 32,
        "chat_id: -1001234567890",
        "https://t.me/private_room",
        "password=hidden",
    ],
)
def test_private_values_in_derived_text_refuse_publication(private: str) -> None:
    with pytest.raises(MemoryPublicationError, match="MEMORY_PRIVATE_PAYLOAD"):
        privacy_checked({"rationale": private})


@pytest.mark.postgres
def test_reviewed_dream_publishes_and_backfill_uses_exact_revision(
    pg_dsn: str, tmp_path: Path
) -> None:
    from serene.adapters.postgres import (
        PostgresEventStore,
        PostgresProjectionStore,
        backfill_projections,
        projection_publisher,
    )
    from serene.memory.consolidation import run_consolidation
    from serene.memory.dream import DreamDraft

    from .memory_helpers import ScriptedModelDreamer

    ladder = build_full_ladder(seed="pg-memory", store=PostgresEventStore(pg_dsn))
    fam = ladder["family"]
    sink = RecordingSink()
    projections = PostgresProjectionStore(pg_dsn)
    repo_holder: list[GitMemoryRepository] = []

    def resolve(child, sha):
        return repo_holder[0].at_revision(sha)

    fam.ledger = EventLedger(
        fam.store,
        fam.clock,
        telemetry=SafeTelemetry(sink),
        after_append=projection_publisher(projections, resolve),
    )
    stack = memory_stack(fam, tmp_path / "memory")
    repo_holder.append(stack.repo)
    dreamer = ScriptedModelDreamer(
        fam.agent,
        [
            DreamDraft(
                ladder["learning"].learning_id,
                "learnings/kept.md",
                "Synthetic kept memory",
                "Synthetic reviewed learning.",
            ),
            DreamDraft(
                ladder["observations"][2].observation_id,
                "child/refused.md",
                "Synthetic refused memory",
                "Synthetic unsupported generalisation.",
            ),
        ],
    )
    run_consolidation(stack.pipeline(dreamer), stack.committer, fam.child_id)
    state = fam.state()
    published = projections.load(fam.child_id)
    view = published["memory_dream"]
    assert view["memory_head"] == stack.repo.head()
    assert len(view["memories"]) == 1
    assert {p["status"] for p in view["patches"]} == {"COMMITTED", "REJECTED"}
    rejected = next(p for p in view["patches"] if p["status"] == "REJECTED")
    assert rejected["rejection_reasons"] and rejected["review"]["passed"] is False
    assert view["dream_runs"][0]["complete"]
    text = canonical_json(view).decode()
    assert "chd_" not in text and "act_" not in text
    assert "child_id" not in text and "actor_id" not in text
    assert canonical_json(published) == canonical_json(publishable_projections(state, resolve))
    # No document narrative is ever emitted to telemetry.
    assert "Synthetic reviewed learning" not in str(sink.records)
    assert not any(name == "ledger.after_append_failed" for name, _ in sink.records)

    stack.repo._git("update-ref", BRANCH, stack.repo.history()[-1].sha)
    for replace in (False, True, True):
        backfill_projections(pg_dsn, [fam.child_id], replace=replace, memory_snapshot=resolve)
        assert canonical_json(projections.load(fam.child_id)) == canonical_json(published)

    def missing(child: str, sha: str) -> object:
        raise MemoryPublicationError("MEMORY_REVISION_UNAVAILABLE")

    # Even --replace validates Git before deleting anything.
    with pytest.raises(MemoryPublicationError, match="MEMORY_REVISION_UNAVAILABLE"):
        backfill_projections(pg_dsn, [fam.child_id], replace=True, memory_snapshot=missing)  # type: ignore[arg-type]
    assert canonical_json(projections.load(fam.child_id)) == canonical_json(published)
