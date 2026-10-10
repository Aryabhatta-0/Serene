"""Git memory repo + single-writer Memory Committer: two-phase commits, deterministic
receipts, Critic gating and tamper detection (issues #28, #31, #32)."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from serene.adapters.git_memory import GitMemoryRepository
from serene.domain.entities import MemoryOperation, MemoryPatch, OutcomeResult
from serene.domain.events import EventType, MemoryPatchCommitted, MemoryPatchProposed
from serene.domain.values import DerivationMethod, Provenance, VerificationStatus
from serene.ledger import AdmissionRejected
from serene.lineage.provenance import raw_sources_of
from serene.memory import critic
from serene.memory.committer import MemoryIntegrityError, audit
from serene.memory.diff import full_diff
from serene.memory.document import MemoryDoc, render
from serene.memory.retrieval import active_learnings
from serene.memory.rules import required_level_for
from serene.memory.store import StaleHead
from serene.ports.memory import CommitAuthorization, MemoryRepository
from serene.testing import build_full_ladder
from serene.testing.synthetic import T0

from .memory_helpers import MemoryStack, memory_stack

ROOT = Path(__file__).resolve().parents[1]
PATH = "learnings/pickup-heads-up.md"


def _learning_patch(
    stack: MemoryStack, lrn: str, *, body: str = "A heads-up helps."
) -> MemoryPatch:
    fam = stack.fam
    state = fam.state()
    front = critic.expected_front(lrn, PATH, state, fam.clock.now())
    text = render(MemoryDoc(front=front, title="Pickup heads-up", body=body))
    current = stack.repo.read(PATH)
    operation = MemoryOperation.CREATE if current is None else MemoryOperation.UPDATE
    return MemoryPatch(
        child_id=fam.child_id,
        provenance=Provenance(
            created_by=fam.system,
            created_at=fam.clock.now(),
            method=DerivationMethod.DETERMINISTIC_RULE,
            derived_from=(lrn,),
            source_ids=tuple(sorted(raw_sources_of(lrn, state))),
        ),
        patch_id=fam.new_id("mpt"),
        target_path=PATH,
        operation=operation,
        base_revision=None if current is None else current.revision,
        diff=full_diff(PATH, None if current is None else current.content, text),
        rationale="consolidate the pickup learning",
        required_level=required_level_for(PATH, operation),
    )


def _propose(stack: MemoryStack, patch: MemoryPatch) -> None:
    fam = stack.fam
    subject = patch.provenance.derived_from[0]
    fam.append(
        fam.draft(
            EventType.MEMORY_PATCH_PROPOSED,
            fam.system,
            MemoryPatchProposed(patch=patch),
            status=VerificationStatus.UNVERIFIED,
            derived_from=(fam.introduced_by[subject],),
        )
    )


def _ladder_stack(tmp_path: Path, seed: str = "mem") -> tuple[MemoryStack, dict[str, Any]]:
    ladder = build_full_ladder(seed=seed)
    return memory_stack(ladder["family"], tmp_path / seed), ladder


# ------------------------------------------------------------------ Git repository
def test_repo_init_is_deterministic_and_reads_come_from_head(tmp_path: Path) -> None:
    a = GitMemoryRepository.init(tmp_path / "a", created_at=T0)
    b = GitMemoryRepository.init(tmp_path / "b", created_at=T0)
    assert a.head() == b.head()
    assert isinstance(a, MemoryRepository)
    (tmp_path / "a" / "learnings").mkdir()
    (tmp_path / "a" / "learnings" / "planted.md").write_text("planted\n", encoding="utf-8")
    assert a.read("learnings/planted.md") is None  # working-tree edits are never served
    assert a.list_paths("learnings/") == ()
    assert not a.worktree_clean()


def test_committed_patch_is_readable_searchable_and_linked_to_its_proposal(tmp_path: Path) -> None:
    stack, ladder = _ladder_stack(tmp_path)
    lrn = ladder["learning"].learning_id
    patch = _learning_patch(stack, lrn)
    _propose(stack, patch)
    outcome = stack.committer.process(stack.fam.child_id, patch.patch_id)
    assert outcome.committed and outcome.receipt is not None
    receipt = outcome.receipt
    doc = stack.repo.read(PATH)
    assert doc is not None and doc.revision == receipt.commit_sha
    assert stack.repo.search("heads-up") == (PATH,)
    assert stack.repo.worktree_clean()
    assert (tmp_path / "mem" / PATH).read_text(encoding="utf-8") == doc.content

    events = {e.event_id: e for e in stack.fam.ledger.get_events_for_child(stack.fam.child_id)}
    commit_event = events[receipt.commit_event_id]
    assert commit_event.event_type is EventType.MEMORY_PATCH_COMMITTED
    assert commit_event.actor == stack.committer_actor
    assert set(commit_event.derived_from) == {receipt.proposal_event_id, receipt.review_event_id}
    history = stack.repo.history()[0]
    assert history.trailers["Serene-Patch-Id"] == patch.patch_id
    assert history.trailers["Serene-Proposal-Event"] == receipt.proposal_event_id
    assert history.trailers["Serene-Review-Event"] == receipt.review_event_id
    assert audit(stack.repo, stack.fam.state()) == []
    assert [
        r.doc.front.subject
        for r in active_learnings(stack.repo, stack.fam.state(), stack.fam.clock.now())
    ] == [lrn]


def test_commits_and_receipts_are_deterministic(tmp_path: Path) -> None:
    receipts = []
    for run in ("one", "two"):
        stack, ladder = _ladder_stack(tmp_path / run, seed="deterministic")
        patch = _learning_patch(stack, ladder["learning"].learning_id)
        _propose(stack, patch)
        receipts.append(stack.committer.process(stack.fam.child_id, patch.patch_id).receipt)
    assert receipts[0] is not None and receipts[1] is not None
    assert receipts[0].commit_sha == receipts[1].commit_sha
    assert receipts[0].digest == receipts[1].digest


def test_failed_review_is_rejected_and_never_written(tmp_path: Path) -> None:
    stack, ladder = _ladder_stack(tmp_path)
    head = stack.repo.head()
    patch = _learning_patch(stack, ladder["learning"].learning_id)
    lying = patch.model_copy(update={"diff": patch.diff.replace("weekday_evening", "all_day")})
    _propose(stack, lying)
    outcome = stack.committer.process(stack.fam.child_id, lying.patch_id)
    assert not outcome.committed
    assert "SCOPE_MISMATCH" in outcome.reason_codes
    assert stack.repo.head() == head
    assert stack.fam.state().memory_patches[lying.patch_id] == "REJECTED"


def test_no_commit_without_a_passed_review(tmp_path: Path) -> None:
    stack, ladder = _ladder_stack(tmp_path)
    patch = _learning_patch(stack, ladder["learning"].learning_id)
    _propose(stack, patch)
    fam = stack.fam
    forged = fam.draft(
        EventType.MEMORY_PATCH_COMMITTED,
        stack.committer_actor,
        MemoryPatchCommitted(patch_id=patch.patch_id, commit_sha="a" * 40),
    )
    with pytest.raises(AdmissionRejected, match="NO_PASSED_REVIEW"):
        fam.append(forged)
    for actor in (fam.agent, fam.system, fam.policy, fam.parent):
        with pytest.raises(AdmissionRejected, match="ACTOR_NOT_PERMITTED"):
            fam.append(forged.model_copy(update={"actor": actor}))


def test_forged_passing_review_is_refused(tmp_path: Path) -> None:
    from serene.domain.events import MemoryCheck, MemoryPatchReviewed

    stack, ladder = _ladder_stack(tmp_path)
    patch = _learning_patch(stack, ladder["learning"].learning_id)
    bad = patch.model_copy(
        update={"required_level": required_level_for("patterns/x.md", MemoryOperation.CREATE)}
    )
    _propose(stack, bad)
    fam = stack.fam
    forged = MemoryPatchReviewed(
        patch_id=bad.patch_id,
        passed=True,
        checks_passed=tuple(MemoryCheck),
        reason_codes=("ALL_CHECKS_PASSED",),
        critic_version=critic.CRITIC_VERSION,
        facts_digest="0" * 64,
    )
    with pytest.raises(AdmissionRejected) as info:
        fam.append(fam.draft(EventType.MEMORY_PATCH_REVIEWED, fam.policy, forged))
    assert {"VERDICT_MISMATCH", "STALE_FACTS_DIGEST"} <= set(info.value.reason_codes)


def test_review_that_no_longer_holds_cannot_commit(tmp_path: Path) -> None:
    """A contradiction lands between review and commit: the ledger refuses, Git never moves."""
    stack, ladder = _ladder_stack(tmp_path)
    fam = stack.fam
    patch = _learning_patch(stack, ladder["learning"].learning_id)
    _propose(stack, patch)
    stack.committer.review(fam.child_id, patch.patch_id)
    exp = fam.propose_experiment(ladder["hypothesis"])
    fam.classify(exp)
    apr = fam.request_approval(exp)
    fam.grant(exp, apr)
    fam.start(exp, apr)
    fam.outcome(
        exp, (fam.observe("meltdown with heads-up", day=30),), result=OutcomeResult.CONTRADICTS
    )
    head = stack.repo.head()
    outcome = stack.committer.process(fam.child_id, patch.patch_id)
    assert not outcome.committed
    assert any(r.startswith("REVIEW_NO_LONGER_VALID") for r in outcome.reason_codes)
    assert stack.repo.head() == head


def test_out_of_band_writes_are_detected_and_fail_closed(tmp_path: Path) -> None:
    stack, ladder = _ladder_stack(tmp_path)
    fam = stack.fam
    lrn = ladder["learning"].learning_id
    first = _learning_patch(stack, lrn)
    _propose(stack, first)
    stack.committer.process(fam.child_id, first.patch_id)

    # A component bypasses the committer and calls the port's write method directly.
    rogue = _learning_patch(stack, lrn, body="Rewritten silently.")
    stack.repo.commit(
        rogue,
        CommitAuthorization(
            patch_id=rogue.patch_id, proposal_event_id=fam.new_id("evt"), ledger_head="0" * 64
        ),
    )
    findings = audit(stack.repo, fam.state())
    assert any(f.startswith("UNAUTHORIZED_COMMIT") for f in findings)
    with pytest.raises(MemoryIntegrityError):
        active_learnings(stack.repo, fam.state(), fam.clock.now())
    second = _learning_patch(stack, lrn, body="Another update.")
    _propose(stack, second)
    with pytest.raises(MemoryIntegrityError):
        stack.committer.process(fam.child_id, second.patch_id)


def test_hand_edited_working_tree_is_detected(tmp_path: Path) -> None:
    stack, ladder = _ladder_stack(tmp_path)
    patch = _learning_patch(stack, ladder["learning"].learning_id)
    _propose(stack, patch)
    stack.committer.process(stack.fam.child_id, patch.patch_id)
    (tmp_path / "mem" / PATH).write_text("trust me\n", encoding="utf-8")
    assert "DIRTY_WORKTREE" in audit(stack.repo, stack.fam.state())
    assert stack.repo.read(PATH) is not None and "trust me" not in stack.repo.read(PATH).content  # type: ignore[union-attr]


def test_publish_is_compare_and_set(tmp_path: Path) -> None:
    stack, ladder = _ladder_stack(tmp_path)
    lrn = ladder["learning"].learning_id
    patch = _learning_patch(stack, lrn)
    auth = CommitAuthorization(
        patch_id=patch.patch_id, proposal_event_id=stack.fam.new_id("evt"), ledger_head="0" * 64
    )
    a = stack.repo.prepare_commit(patch, auth, trailers={}, committed_at=T0)
    assert stack.repo.head() == a.parent_sha  # preparing never moves the branch
    other = patch.model_copy(
        update={
            "patch_id": stack.fam.new_id("mpt"),
            "diff": _learning_patch(stack, lrn, body="Other.").diff,
        }
    )
    b = stack.repo.prepare_commit(
        other, auth.model_copy(update={"patch_id": other.patch_id}), trailers={}, committed_at=T0
    )
    stack.repo.publish(b)
    with pytest.raises(StaleHead):
        stack.repo.publish(a)


def test_only_the_committer_module_writes_memory() -> None:
    """Static single-writer check over the whole package (issue #32)."""
    writers = {"prepare_commit", "publish", "commit"}
    offenders = []
    for path in (ROOT / "serene").rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel in {
            "serene/memory/committer.py",
            "serene/adapters/git_memory.py",
            "serene/memory/store.py",
        }:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr in writers:
                offenders.append(f"{rel}:{node.lineno}:{node.attr}")
    assert offenders == []


def test_dream_has_no_write_capability() -> None:
    source = (ROOT / "serene" / "memory" / "dream.py").read_text(encoding="utf-8")
    imported = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "serene.memory.committer" not in imported
    assert not any(m.startswith("serene.adapters") for m in imported)
    assert "MemoryStore" not in source


def test_memory_package_never_reaches_runtime_or_adapters() -> None:
    code = (
        "import sys\n"
        "import serene.memory.dream, serene.memory.committer, serene.memory.retrieval\n"
        "import serene.causal, serene.experiments.service\n"
        "bad = sorted(m for m in sys.modules if m.split('.')[0] in "
        "{'hermes', 'hermes_agent', 'psycopg', 'neatlogs', 'inspect_ai', 'openai', 'anthropic'} "
        "or m.startswith('serene.adapters'))\n"
        "print(','.join(bad))\n"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, cwd=ROOT, check=True
    )
    assert result.stdout.strip() == ""
