"""Fail unless an Inspect run finished cleanly with every sample CORRECT.

    uv run python scripts/inspect_gate.py <log_dir> <task_name> [<task_name> ...]

`inspect eval` exits 0 when samples are scored INCORRECT, so on its own it is not a
gate. This reads the logs in <log_dir> and requires, for every named task: exactly
the latest log has status "success", at least one sample, every sample completed,
and accuracy 1.0. Anything missing or unreadable fails closed.
"""

from __future__ import annotations

import sys

from inspect_ai.log import list_eval_logs, read_eval_log


def _task_problems(name: str, log: object | None, log_dir: str) -> list[str]:
    if log is None:
        return [f"{name}: no log in {log_dir}"]
    status = getattr(log, "status", None)
    results = getattr(log, "results", None)
    if status != "success" or results is None:
        return [f"{name}: status {status}"]
    total, done = results.total_samples, results.completed_samples
    accuracy = next(
        (
            m.value
            for score in results.scores
            for key, m in score.metrics.items()
            if key == "accuracy"
        ),
        None,
    )
    problems = []
    if total == 0 or done != total:
        problems.append(f"{name}: {done}/{total} samples completed")
    if accuracy != 1.0:
        problems.append(f"{name}: accuracy {accuracy} (every sample must be CORRECT)")
    if not problems:
        print(f"{name}: {done}/{total} CORRECT")
    return problems


def check(log_dir: str, tasks: list[str]) -> list[str]:
    latest: dict[str, object] = {}
    for info in list_eval_logs(log_dir):  # newest first
        log = read_eval_log(info, header_only=True)
        latest.setdefault(log.eval.task.split("/")[-1], log)
    return [p for name in tasks for p in _task_problems(name, latest.get(name), log_dir)]


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    problems = check(argv[1], argv[2:])
    for problem in problems:
        print(f"INSPECT GATE FAILED: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
