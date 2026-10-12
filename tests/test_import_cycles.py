"""Each runtime entry point must import on its own in a fresh interpreter (issue #35).

`serene.policies.investigation` reads `serene.projections.state`, and the
`investigations` projection reads the policy back. That is a DAG only while the
`serene.projections` package does not eagerly import its views: importing the
policy first (as the Inspect `runtime_investigation` task does) must not loop.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# The import path of eval/tasks/runtime_investigation.py, lowest layer first.
ENTRY_POINTS = (
    "serene.projections.state",
    "serene.policies.investigation",
    "serene.projections.investigations",
    "serene.projections.views",
    "serene.projections",
    "eval.scenarios.runtime_scenarios",
    "eval.tasks.runtime_investigation",
)


@pytest.mark.parametrize("module", ENTRY_POINTS)
def test_module_imports_first_in_a_fresh_process(module: str) -> None:
    if module.startswith("eval.tasks.") and importlib.util.find_spec("inspect_ai") is None:
        pytest.skip("inspect_ai is not installed (eval extra)")
    result = subprocess.run(  # noqa: S603 - fixed interpreter and code
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stderr
