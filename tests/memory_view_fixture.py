"""The synthetic memory / Dream review fixture the web surface is tested with (issue #36).

It is produced by running the real kernel, not written by hand: a synthetic
family, a scripted Dreamer whose patch A is committed and patch B is rejected
for insufficient evidence, then a template Dream run whose new pattern patch is
still awaiting the committer. `tests/test_memory_view.py` checks that the
checked-in JSON is exactly what this produces. To regenerate it:

    uv run python -m tests.memory_view_fixture
"""

from __future__ import annotations

import tempfile
from datetime import timedelta
from pathlib import Path

from serene.memory.consolidation import run_consolidation
from serene.memory.dream import DreamDraft
from serene.memory.view import MemoryDreamView, build_memory_dream_view
from serene.testing import build_full_ladder

from .memory_helpers import ScriptedModelDreamer, memory_stack

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "app" / "web" / "fixtures" / "synthetic-memory-dream.json"
PATCH_A = "learnings/pickup-heads-up.md"
PATCH_B = "child/needs-warning-before-every-transition.md"


def build_fixture_view(workdir: Path) -> MemoryDreamView:
    ladder = build_full_ladder(seed="memory-dream-fixture")
    stack = memory_stack(ladder["family"], workdir / "memory")
    fam = stack.fam
    dreamer = ScriptedModelDreamer(
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
    run_consolidation(stack.pipeline(dreamer), stack.committer, fam.child_id)
    fam.clock.advance(timedelta(days=1))
    stack.pipeline().run(fam.child_id)  # proposes only: left for the committer
    return build_memory_dream_view(fam.state(), stack.repo)


def fixture_json(view: MemoryDreamView) -> str:
    return view.model_dump_json(indent=2) + "\n"


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        text = fixture_json(build_fixture_view(Path(tmp)))
    FIXTURE.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {FIXTURE.relative_to(ROOT)}")
