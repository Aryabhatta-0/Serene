"""The Inspect AI trust scenarios produce their expected, deterministic outcomes."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("inspect_ai")

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "trust_invariants", ROOT / "eval" / "tasks" / "trust_invariants.py"
)
assert _spec and _spec.loader
trust_invariants = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(trust_invariants)


@pytest.mark.parametrize("name", sorted(trust_invariants.SCENARIOS))
def test_trust_scenario_matches_frozen_expectation(name: str) -> None:
    run, expected = trust_invariants.SCENARIOS[name]
    assert run() == expected
    assert run() == expected  # repeatable


def test_trust_task_builds() -> None:
    task = trust_invariants.trust_invariants()
    assert len(task.dataset) == len(trust_invariants.SCENARIOS)
