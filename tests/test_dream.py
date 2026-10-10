"""Dream pipeline: stages, proposal-only output, Critic/committer decisions, and the
Experience / Memory / Belief separation (issues #29, #30, #31, #32)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from serene.causal import build_causal_twin
from serene.domain.canonical import canonical_digest
from serene.domain.entities import LearningStatus, MemoryOperation
from serene.domain.events import DreamStage, EventType, MemoryDreamStageRecorded
from serene.experiments.service import ExperimentLifecycleService
from serene.ledger import AdmissionRejected
from serene.memory.consolidation import run_consolidation
from serene.memory.document import parse
from serene.memory.dream import DreamDraft
from serene.memory.retrieval import active_learnings
from serene.memory.store import ReadOnlyMemory
from serene.testing import build_full_ladder

from .memory_helpers import MemoryStack, ScriptedModelDreamer, memory_stack
from .trust_helpers import ctx

PATCH_A = "learnings/pickup-heads-up.md"
PATCH_B = "child/needs-warning-before-every-transition.md"


def _stack(tmp_path: Path, seed: str) -> tuple[MemoryStack, dict[str, Any]]:
    ladder = build_full_ladder(seed=seed)
    return memory_stack(ladder["family"], tmp_path / seed), ladder


def _a_and_b(stack: MemoryStack, ladder: dict[str, Any]) -> ScriptedModelDreamer:
    fam = stack.fam
    return ScriptedModelDreamer(
        fam.agent,
        [
            DreamDraft(
                ladder["learning"].learning_id,
                PATCH_A,
                "A five-minute heads-up helps weekday pickups",
                "On weekday daycare pickups, a five-minute heads-up before leaving went calmly.",
            ),
            DreamDraft(
                ladder["observations"][2].observation_id,  # a single observation (level 1)
                PATCH_B,
                "Needs a warning before every transition",
                "The child always needs a warning before any transition, everywhere.",
            ),
        ],
    )


def test_patch_a_is_accepted_and_patch_b_is_rejected_for_insufficient_evidence(
    tmp_path: Path,
) -> None:
    stack, ladder = _stack(tmp_path, "dream-ab")
    fam = stack.fam
    result = run_consolidation(
        stack.pipeline(_a_and_b(stack, ladder)), stack.committer, fam.child_id
    )

    assert len(result.dream.proposed) == 2
    (accepted,) = result.committed
    (rejected,) = result.rejected
    assert accepted.receipt is not None and accepted.receipt.target_path == PATCH_A
    assert any(
        r.startswith("INSUFFICIENT_EVIDENCE:OBSERVATION_BELOW_PATTERN")
        for r in rejected.reason_codes
    )

    state = fam.state()
    assert state.memory_patches[accepted.patch_id] == "COMMITTED"
    assert state.memory_patches[rejected.patch_id] == "REJECTED"
    assert stack.repo.list_paths("") == (PATCH_A,)
    doc = parse(stack.repo.read(PATCH_A).content)  # type: ignore[union-attr]
    # Authority-bearing fields came from the ledger, not from the model's prose.
    assert doc.front.subject == ladder["learning"].learning_id
    assert doc.front.status is LearningStatus.ACTIVE
    assert doc.front.scope == ladder["learning"].scope.contexts
    assert doc.front.review_after == ladder["learning"].validity.review_after
    proposals = [
        e
        for e in fam.ledger.get_events_for_child(fam.child_id)
        if e.event_type is EventType.MEMORY_PATCH_PROPOSED
    ]
    assert {e.actor for e in proposals} == {fam.agent}
    assert all(e.payload["patch"]["provenance"]["model"] is not None for e in proposals)


def test_every_stage_is_recorded_in_order_and_dream_only_proposes(tmp_path: Path) -> None:
    stack, _ladder = _stack(tmp_path, "dream-stages")
    fam = stack.fam
    head = stack.repo.head()
    report = stack.pipeline().run(fam.child_id)
    assert [e.payload["stage"] for e in report.stage_events] == [s.value for s in DreamStage]
    for previous, current in zip(report.stage_events, report.stage_events[1:], strict=False):
        assert current.derived_from == (previous.event_id,)
    assert report.proposed  # learning + pattern documents
    assert stack.repo.head() == head  # nothing written by Dream
    assert all(fam.state().memory_patches[p] == "PROPOSED" for p in report.proposed)
    assert isinstance(stack.pipeline()._memory, ReadOnlyMemory)
    assert not hasattr(stack.pipeline()._memory, "prepare_commit")

    run = report.run_id
    with pytest.raises(AdmissionRejected, match="RUN_ALREADY_COMPLETE"):
        fam.append(
            fam.draft(
                EventType.MEMORY_DREAM_STAGE_RECORDED,
                fam.system,
                MemoryDreamStageRecorded(
                    dream_run_id=run, stage=DreamStage.ORIENT, output_digest="0" * 64, item_count=0
                ),
            )
        )
    with pytest.raises(AdmissionRejected) as info:
        fam.append(
            fam.draft(
                EventType.MEMORY_DREAM_STAGE_RECORDED,
                fam.system,
                MemoryDreamStageRecorded(
                    dream_run_id="1" * 64,
                    stage=DreamStage.PROPOSE_PATCH,
                    input_ids=(fam.new_id("mpt"),),
                    output_digest="0" * 64,
                    item_count=1,
                ),
            )
        )
    assert {r.split(":", 1)[0] for r in info.value.reason_codes} >= {
        "STAGE_OUT_OF_ORDER",
        "UNKNOWN_INPUT",
        "NOT_A_PROPOSED_PATCH",
    }
    with pytest.raises(AdmissionRejected, match="ACTOR_NOT_PERMITTED:AGENT"):
        fam.append(
            fam.draft(
                EventType.MEMORY_DREAM_STAGE_RECORDED,
                fam.agent,
                MemoryDreamStageRecorded(
                    dream_run_id="2" * 64,
                    stage=DreamStage.ORIENT,
                    output_digest="0" * 64,
                    item_count=0,
                ),
            )
        )


def test_template_consolidation_commits_and_is_idempotent(tmp_path: Path) -> None:
    stack, _ladder = _stack(tmp_path, "dream-template")
    fam = stack.fam
    first = run_consolidation(stack.pipeline(), stack.committer, fam.child_id)
    assert len(first.committed) == 2 and not first.rejected
    assert sorted(p.split("/")[0] for p in stack.repo.list_paths("")) == ["learnings", "patterns"]
    second = run_consolidation(stack.pipeline(), stack.committer, fam.child_id)
    assert second.dream.proposed == [] and len(second.dream.unchanged) == 2


def test_dreamer_inventions_and_overreach_never_become_memory(tmp_path: Path) -> None:
    stack, ladder = _stack(tmp_path, "dream-overreach")
    fam = stack.fam
    dreamer = ScriptedModelDreamer(
        fam.agent,
        [
            DreamDraft(
                fam.new_id("lrn"), "learnings/invented.md", "Invented", "Not in the ledger."
            ),
            DreamDraft(ladder["learning"].learning_id, "../escape.md", "Escape", "Path traversal."),
            # A hypothesis is not a learning: refused at proposal admission already...
            DreamDraft(ladder["hypothesis"].hypothesis_id, "learnings/hyp.md", "Hyp", "Overreach."),
            # ...and not a pattern either: refused by the Critic's gate.
            DreamDraft(ladder["hypothesis"].hypothesis_id, "patterns/hyp.md", "Hyp", "Overreach."),
        ],
    )
    result = run_consolidation(stack.pipeline(dreamer), stack.committer, fam.child_id)
    assert sorted(result.dream.dropped) == ["DROPPED_INVALID_PATH", "DROPPED_UNKNOWN_SUBJECT"]
    ((refused_path, refused_codes),) = result.dream.refused
    assert refused_path == "learnings/hyp.md" and "REQUIRES_ACTIVE_LEARNING" in refused_codes
    (rejected,) = result.rejected
    assert "SUBJECT_KIND_NOT_ALLOWED:hyp" in rejected.reason_codes
    assert stack.repo.list_paths("") == ()
    propose_stage = result.dream.stage_events[-1].payload
    assert "PROPOSAL_REFUSED:REQUIRES_ACTIVE_LEARNING" in propose_stage["reason_codes"]


def test_stale_learning_is_withdrawn_from_memory_and_never_retrieved(tmp_path: Path) -> None:
    stack, ladder = _stack(tmp_path, "dream-stale")
    fam = stack.fam
    run_consolidation(stack.pipeline(), stack.committer, fam.child_id)
    now = fam.clock.now()
    assert [r.doc.front.subject for r in active_learnings(stack.repo, fam.state(), now)] == [
        ladder["learning"].learning_id
    ]

    fam.clock.advance(timedelta(days=61))
    # Even before any job runs, retrieval refuses to surface the overdue learning.
    assert active_learnings(stack.repo, fam.state(), fam.clock.now()) == []
    ExperimentLifecycleService(fam.ledger, fam.clock, ctx(fam)).run_timers(fam.child_id)
    result = run_consolidation(stack.pipeline(), stack.committer, fam.child_id)
    (withdrawn,) = result.committed
    assert (
        withdrawn.receipt is not None and withdrawn.receipt.operation is MemoryOperation.DEPRECATE
    )
    doc = parse(stack.repo.read(withdrawn.receipt.target_path).content)  # type: ignore[union-attr]
    assert doc.front.status is LearningStatus.NEEDS_REVIEW
    assert active_learnings(stack.repo, fam.state(), fam.clock.now()) == []


# ------------------------------------------------------------------ layer separation (#29)
def test_belief_is_rebuilt_from_the_ledger_never_from_memory(tmp_path: Path) -> None:
    import inspect

    stack, _ladder = _stack(tmp_path, "layers")
    fam = stack.fam
    now = fam.clock.now()
    before = build_causal_twin(fam.state(), now)
    run_consolidation(stack.pipeline(), stack.committer, fam.child_id)
    (tmp_path / "layers" / "learnings" / "planted.md").write_text(
        "belief: certain\n", encoding="utf-8"
    )
    after = build_causal_twin(fam.state(), now)
    # Committing memory moved the ledger head but changed no belief, and a planted
    # memory file cannot reach belief: the twin has no memory input at all.
    assert after.ledger_head != before.ledger_head
    assert canonical_digest(after.edges) == canonical_digest(before.edges)
    assert set(inspect.signature(build_causal_twin).parameters) == {"state", "now", "labels"}


def test_belief_cannot_be_persisted_as_raw_experience(tmp_path: Path) -> None:
    from serene.domain.events import ObservationReported

    stack, ladder = _stack(tmp_path, "layers-experience")
    fam = stack.fam
    evidence = ladder["observations"][0]
    raw = fam.state().entities[evidence.evidence_ids[0]].entity
    forged = raw.model_copy(
        update={"evidence_id": fam.new_id("evd"), "content": ladder["hypothesis"].statement}
    )
    with pytest.raises(AdmissionRejected, match="ACTOR_NOT_PERMITTED:AGENT"):
        fam.append(
            fam.draft(
                EventType.OBSERVATION_REPORTED, fam.agent, ObservationReported(evidence=forged)
            )
        )


def test_experience_is_not_silently_rewritten_into_memory(tmp_path: Path) -> None:
    stack, _ladder = _stack(tmp_path, "layers-silent")
    head = stack.repo.head()
    stack.fam.observe("A brand-new parent report", day=40)
    stack.pipeline().run(stack.fam.child_id)  # Dream without the committer
    assert stack.repo.head() == head and stack.repo.list_paths("") == ()
