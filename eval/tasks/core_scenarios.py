"""Inspect AI task: the ten frozen core failure-mode scenarios (issue #44).

    uv run inspect eval eval/tasks/core_scenarios.py --model mockllm/model

Each sample is one scenario from eval/fixtures/core-scenarios-v1.json (hash-pinned).
The solver runs the production Serene stack on synthetic data with a scripted
model wire (no credentials, byte-reproducible); the scorer compares the
observations with the frozen expectation, outside the evaluated system. A sample is
CORRECT only if every expectation holds. Failing samples are real findings and are
kept; this task is reported, not tuned against (docs/core-scenarios.md).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from inspect_ai import Task, task  # noqa: E402
from inspect_ai.dataset import MemoryDataset, Sample  # noqa: E402
from inspect_ai.model import ModelOutput  # noqa: E402
from inspect_ai.scorer import CORRECT, INCORRECT, Score, Target, accuracy, scorer  # noqa: E402
from inspect_ai.solver import Generate, TaskState, solver  # noqa: E402

from eval.scenarios.core_scenarios import DRIVERS, grade, load_frozen  # noqa: E402


@solver
def run_core_scenario():  # type: ignore[no-untyped-def]
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        observed = DRIVERS[str(state.sample_id)]()
        state.metadata["observed"] = observed
        state.output = ModelOutput.from_content(
            model="serene", content=json.dumps(observed, sort_keys=True)
        )
        state.completed = True
        return state

    return solve


@scorer(metrics=[accuracy()])
def frozen_expectation():  # type: ignore[no-untyped-def]
    async def score(state: TaskState, target: Target) -> Score:
        passed, misses = grade(json.loads(target.text), state.metadata["observed"])
        return Score(
            value=CORRECT if passed else INCORRECT,
            answer=state.output.completion,
            explanation="PASS" if passed else "FAIL: " + "; ".join(misses),
        )

    return score


@task
def core_scenarios() -> Task:
    frozen = load_frozen()
    return Task(
        dataset=MemoryDataset(
            [
                Sample(
                    id=s["scenario_id"],
                    input=s["model_mistake"],
                    target=json.dumps(s["expected"], sort_keys=True),
                    metadata={
                        "version": s["version"],
                        "target_failure_mode": s["target_failure_mode"],
                        "expected_behaviour": s["expected_behaviour"],
                    },
                )
                for s in frozen["scenarios"]
            ]
        ),
        solver=run_core_scenario(),
        scorer=frozen_expectation(),
        version=1,
    )
