"""Report the latest core_scenarios Inspect run (issue #44) as a PASS/FAIL table.

    uv run python eval/runners/core_scenarios_report.py <log_dir> [--json out.json]

Fails (exit 1) if the run is missing, did not finish, did not score exactly the ten
frozen scenarios, or any sample errored. A scenario scored FAIL does not fail this
report: those are findings, recorded as they are (docs/core-scenarios.md). The
all-CORRECT gate for the other tasks (scripts/inspect_gate.py) is unchanged.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from inspect_ai.log import list_eval_logs, read_eval_log  # noqa: E402

from eval.scenarios.core_scenarios import load_frozen  # noqa: E402


def rows(log_dir: str) -> tuple[str, list[dict[str, Any]], list[str]]:
    infos = [
        i
        for i in list_eval_logs(log_dir)  # newest first
        if read_eval_log(i, header_only=True).eval.task.split("/")[-1] == "core_scenarios"
    ]
    if not infos:
        return "", [], [f"no core_scenarios log in {log_dir}"]
    log = read_eval_log(infos[0])
    problems = [] if log.status == "success" else [f"status {log.status}"]
    frozen = {s["scenario_id"]: s for s in load_frozen()["scenarios"]}
    out = []
    for sample in log.samples or []:
        if sample.error is not None:
            problems.append(f"{sample.id}: errored")
            continue
        score = next(iter((sample.scores or {}).values()))
        spec = frozen[str(sample.id)]
        out.append(
            {
                "scenario_id": sample.id,
                "target_failure_mode": spec["target_failure_mode"],
                "expected_behaviour": spec["expected_behaviour"],
                "observed": sample.metadata.get("observed"),
                "verdict": "PASS" if score.value == "C" else "FAIL",
                "reason": score.explanation,
            }
        )
    if sorted(r["scenario_id"] for r in out) != sorted(frozen):
        problems.append(f"scored {len(out)} samples, expected the 10 frozen scenarios")
    return infos[0].name, out, problems


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    log_name, table, problems = rows(argv[1])
    print(f"core_scenarios log: {log_name}")
    print("| Scenario | Failure mode | Verdict | Reason |")
    print("| --- | --- | --- | --- |")
    for r in table:
        cells = (r["scenario_id"], r["target_failure_mode"], r["verdict"], r["reason"])
        print("| " + " | ".join(str(c) for c in cells) + " |")
    passed = sum(r["verdict"] == "PASS" for r in table)
    print(f"\n{passed}/{len(table)} PASS")
    if "--json" in argv:
        Path(argv[argv.index("--json") + 1]).write_text(
            json.dumps({"log": log_name, "results": table}, indent=2, sort_keys=True) + "\n",
            "utf-8",
        )
    for problem in problems:
        print(f"CORE SCENARIO RUN INCOMPLETE: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
