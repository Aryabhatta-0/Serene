"""Inspect AI task: Serene investigation/evidence runtime scenarios (#48, #49, #50).

    uv run inspect eval eval/tasks/runtime_investigation.py --model mockllm/model

The solver drives the production Serene stack through each frozen scenario
with a scripted Hermes wire (no credentials, byte-reproducible); the scorer is
external and deterministic (eval/scorers/runtime_scorers.py) and compares the
run with a grader-only oracle. A sample is CORRECT only if all three runtime
scorers pass with no critical finding.
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

from eval.scenarios.runtime_scenarios import SCENARIOS  # noqa: E402
from eval.scorers.runtime_scorers import SCORER_VERSION, report_row  # noqa: E402


@solver
def drive_serene():  # type: ignore[no-untyped-def]
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        scenario = SCENARIOS[state.sample_id]  # type: ignore[index]
        trajectory = scenario.run_serene()
        state.metadata["trajectory"] = trajectory.to_json()
        state.output = ModelOutput.from_content(model="serene", content=trajectory.terminal)
        return state

    return solve


@scorer(metrics=[accuracy()])
def runtime_scorers():  # type: ignore[no-untyped-def]
    async def score(state: TaskState, target: Target) -> Score:
        from eval.scorers.runtime_scorers import EvidenceUse, Trajectory

        data = json.loads(state.metadata["trajectory"])
        data["evidence"] = tuple(EvidenceUse(**e) for e in data["evidence"])
        for key in ("questions",):
            data[key] = tuple(tuple(q) for q in data[key])
        for key in ("hypotheses_retained", "failures_recorded"):
            data[key] = tuple(data[key])
        row = report_row(Trajectory(**data), SCENARIOS[state.sample_id].oracle)  # type: ignore[index]
        passed = all(not s["critical"] for s in row["scores"].values()) and all(
            s["value"] >= float(target.text) for s in row["scores"].values()
        )
        return Score(
            value=CORRECT if passed else INCORRECT,
            answer=state.output.completion,
            explanation=json.dumps(row["scores"], sort_keys=True),
            metadata={"scorer_version": SCORER_VERSION, "budget": row["budget"]},
        )

    return score


# Minimum per-scorer value; frozen alongside the scenarios (critical findings always fail).
THRESHOLD = "0.75"


@task
def runtime_investigation() -> Task:
    return Task(
        dataset=MemoryDataset(
            [Sample(id=sid, input=sid, target=THRESHOLD) for sid in sorted(SCENARIOS)]
        ),
        solver=drive_serene(),
        scorer=runtime_scorers(),
    )
