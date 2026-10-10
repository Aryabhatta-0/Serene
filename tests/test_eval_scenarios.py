"""The frozen Inspect AI kernel scenarios produce their expected outcomes (issue #41 scaffold)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("inspect_ai")

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "kernel_invariants", ROOT / "eval" / "tasks" / "kernel_invariants.py"
)
assert _spec and _spec.loader
kernel_invariants = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kernel_invariants)


@pytest.mark.parametrize("name", sorted(kernel_invariants.SCENARIOS))
def test_scenario_matches_frozen_expectation(name: str) -> None:
    run, expected = kernel_invariants.SCENARIOS[name]
    assert run() == expected
    assert run() == expected  # repeatable


def test_task_builds_with_external_scorer() -> None:
    task = kernel_invariants.kernel_invariants()
    assert len(task.dataset) == len(kernel_invariants.SCENARIOS)
