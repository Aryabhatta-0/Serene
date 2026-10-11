"""Memory / Dream review read view (issue #36): what Dream proposed, what was kept,
what was refused and why, and where every kept memory came from."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError

from serene.domain.canonical import sha256_hex
from serene.memory.view import MemoryDreamView, PatchStatus, PatchView, build_memory_dream_view
from serene.ports.memory import MemoryDocument
from serene.projections.state import replay

from .memory_view_fixture import FIXTURE, PATCH_A, PATCH_B, build_fixture_view, fixture_json


@pytest.fixture(scope="module")
def view(tmp_path_factory: pytest.TempPathFactory) -> MemoryDreamView:
    return build_fixture_view(tmp_path_factory.mktemp("memory-view"))


def test_the_web_fixture_is_exactly_what_the_kernel_produces(view: MemoryDreamView) -> None:
    # The web surface is tested against kernel output, never hand-written data.
    assert FIXTURE.read_text(encoding="utf-8") == fixture_json(view), (
        "regenerate with: uv run python -m tests.memory_view_fixture"
    )
    assert MemoryDreamView.model_validate_json(FIXTURE.read_text(encoding="utf-8")) == view


def test_accepted_rejected_and_pending_patches_are_all_shown(view: MemoryDreamView) -> None:
    by_path = {p.target_path: p for p in view.patches}
    accepted, rejected = by_path[PATCH_A], by_path[PATCH_B]
    assert accepted.status is PatchStatus.COMMITTED and accepted.commit_sha is not None
    assert rejected.status is PatchStatus.REJECTED and rejected.commit_sha is None
    assert any(
        r.startswith("INSUFFICIENT_EVIDENCE:OBSERVATION_BELOW_PATTERN")
        for r in rejected.rejection_reasons
    )
    assert rejected.review is not None and not rejected.review.passed
    pending = [p for p in view.patches if p.status is PatchStatus.PROPOSED]
    assert pending and all(p.decided_at is None and p.review is None for p in pending)


def test_every_rejection_carries_a_reason(view: MemoryDreamView) -> None:
    rejected = [p for p in view.patches if p.status is PatchStatus.REJECTED]
    assert rejected and all(p.rejection_reasons for p in rejected)
    data = rejected[0].model_dump(mode="json")
    data["rejection_reasons"] = []
    with pytest.raises(ValidationError, match="rejection reasons"):
        PatchView.model_validate_json(json.dumps(data))


def test_dream_runs_link_to_the_patches_they_proposed(view: MemoryDreamView) -> None:
    patches = {p.patch_id: p for p in view.patches}
    assert len(view.dream_runs) == 2
    newest, oldest = view.dream_runs
    assert newest.started_at > oldest.started_at
    assert {patches[p].target_path for p in oldest.proposed} == {PATCH_A, PATCH_B}
    for run in view.dream_runs:
        assert run.complete
        assert [s.stage.value for s in run.stages] == [
            "ORIENT",
            "CONSOLIDATE",
            "REFLECT",
            "CHALLENGE",
            "VERIFY",
            "PROPOSE_PATCH",
        ]
        assert all(patches[p].dream_run_id == run.run_id for p in run.proposed)


def test_memory_provenance_resolves_to_raw_evidence(view: MemoryDreamView) -> None:
    patches = {p.patch_id: p for p in view.patches}
    (memory,) = view.memories
    assert memory.path == PATCH_A
    assert memory.written_by is not None
    assert patches[memory.written_by].status is PatchStatus.COMMITTED
    assert patches[memory.written_by].commit_sha == memory.revision
    lineage = memory.lineage
    nodes = {n.entity_id: n for n in lineage.nodes}
    assert lineage.root == memory.subject and not lineage.missing
    assert set(memory.sources) <= set(lineage.raw_evidence)
    # Every parent named in the chain is itself a node: the chain is closed.
    assert all(parent in nodes for n in lineage.nodes for parent in n.parents)
    assert all(nodes[e].level == 0 for e in lineage.raw_evidence)


def test_the_view_holds_no_child_or_actor_identifiers(view: MemoryDreamView) -> None:
    text = fixture_json(view)
    assert "chd_" not in text and "act_" not in text
    assert "actor_id" not in text and "child_id" not in text


def test_the_view_is_rebuilt_from_the_ledger_alone(tmp_path: Path) -> None:
    from serene.testing import build_full_ladder

    from .memory_helpers import memory_stack

    ladder = build_full_ladder(seed="memory-view-replay")
    stack = memory_stack(ladder["family"], tmp_path / "m")
    fam = stack.fam
    stack.pipeline().run(fam.child_id)
    live = build_memory_dream_view(fam.state(), stack.repo)
    rebuilt = build_memory_dream_view(
        replay(fam.ledger.get_events_for_child(fam.child_id)), stack.repo
    )
    assert live == rebuilt


class _Repo:
    def __init__(self, files: dict[str, str]) -> None:
        self._files = files

    def read(self, path: str) -> MemoryDocument | None:
        if path not in self._files:
            return None
        content = self._files[path]
        return MemoryDocument(
            path=path,
            revision="a" * 40,
            content=content,
            content_digest=sha256_hex(content.encode("utf-8")),
        )

    def list_paths(self, prefix: str) -> Sequence[str]:
        return tuple(sorted(p for p in self._files if p.startswith(prefix)))

    def head(self) -> str:
        return "a" * 40


def test_unreadable_memory_is_reported_not_hidden_and_other_files_are_ignored() -> None:
    state = replay([])
    repo = _Repo({"learnings/broken.md": "not a memory document\n", "SCHEMA.md": "# schema\n"})
    view = build_memory_dream_view(state, repo)
    assert [u.path for u in view.unreadable] == ["learnings/broken.md"]
    assert view.memories == () and view.patches == () and view.dream_runs == ()
