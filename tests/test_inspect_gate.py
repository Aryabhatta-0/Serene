"""The CI Inspect gate fails closed: an INCORRECT sample or a missing task fails it."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from inspect_ai import Task, eval
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import CORRECT, INCORRECT, Score, Target, accuracy, scorer
from inspect_ai.solver import TaskState

_spec = importlib.util.spec_from_file_location(
    "inspect_gate", Path(__file__).resolve().parents[1] / "scripts" / "inspect_gate.py"
)
assert _spec is not None and _spec.loader is not None
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


@scorer(metrics=[accuracy()])
def _by_target():  # type: ignore[no-untyped-def]
    async def score(state: TaskState, target: Target) -> Score:
        return Score(value=CORRECT if target.text == "ok" else INCORRECT)

    return score


def _run(log_dir: Path, name: str, targets: list[str]) -> None:
    samples = [Sample(id=str(i), input="x", target=t) for i, t in enumerate(targets)]
    task = Task(dataset=MemoryDataset(samples), scorer=_by_target(), name=name)
    eval(task, model="mockllm/model", log_dir=str(log_dir), display="none")


def test_gate_passes_only_when_every_sample_is_correct(tmp_path: Path) -> None:
    _run(tmp_path, "all_good", ["ok", "ok"])
    _run(tmp_path, "one_bad", ["ok", "bad"])
    assert gate.check(str(tmp_path), ["all_good"]) == []
    (problem,) = gate.check(str(tmp_path), ["one_bad"])
    assert "accuracy 0.5" in problem
    assert gate.check(str(tmp_path), ["never_ran"]) == [f"never_ran: no log in {tmp_path}"]
    assert gate.main(["inspect_gate.py", str(tmp_path), "all_good", "one_bad"]) == 1
