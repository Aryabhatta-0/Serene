"""Rescore a stored live run under the current runtime scorers, without calling a model.

    uv run python eval/runners/rescore_live.py --replayed <dir>/replayed.json \\
        --scores eval/reports/local/live/<run>/scores.json --out <dir>

`replayed.json` comes from `replay_live.py` (the run's ledgers, rebuilt at the run's
commit). Each trajectory is completed with what the current reducer reads from the
rebuilt ledger (`acquisitions_from_events`) and scored with this checkout's scorers.
Fails closed unless the frozen runtime-scorers/1 rule still reproduces the stored
investigation scores. Writes `scores.json` in the runner's row format (the gate's
input; only `scores`, `scorer_version`, `oracle_sha256` and `trajectory` change, and
`rescored` says from what) and `rescore.md` (old -> new per dimension).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.holdout.live_holdout import HOLDOUT  # noqa: E402
from eval.scenarios.runtime_live import DEV  # noqa: E402
from eval.scenarios.runtime_scenarios import acquisitions_from_events  # noqa: E402
from eval.scorers.runtime_scorers import (  # noqa: E402
    SCORER_VERSION,
    Trajectory,
    report_row,
    score_investigation_v1,
)
from serene.domain.events import DomainEvent  # noqa: E402
from serene.projections.state import replay  # noqa: E402


def rescore(stored: dict[str, Any], replayed: dict[str, Any]) -> dict[str, Any]:
    spec = (HOLDOUT if stored.get("split") == "holdout" else DEV)[stored["scenario"]]
    events = [DomainEvent.model_validate_json(json.dumps(e)) for e in replayed["events"]]
    (inv,) = replay(events).investigations  # one investigation per live run
    old = Trajectory.from_json(json.dumps(replayed["trajectory"]))
    frozen = score_investigation_v1(old, spec.oracle).dimensions
    if frozen != stored["scores"]["investigation_success"]["dimensions"]:
        raise SystemExit(f"{stored['scenario']}: runtime-scorers/1 no longer reproduces the run")
    trajectory = dataclasses.replace(old, acquisitions=acquisitions_from_events(events, inv))
    row = report_row(trajectory, spec.oracle)
    return {
        **stored,
        "scores": row["scores"],
        "scorer_version": SCORER_VERSION,
        "oracle_sha256": row["oracle_sha256"],
        "trajectory": json.loads(trajectory.to_json()),
        "rescored": {"from": stored["scorer_version"], "replayed_run": replayed["run_id"]},
    }


def rescore_md(name: str, before: list[dict[str, Any]], after: list[dict[str, Any]]) -> str:
    old = {r["scenario"]: r for r in before}
    lines = [
        f"# Rescore of `{name}`",
        "",
        "| scenario | scorer | value | retention | high_value | resolution | burden | notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in after:
        for source in (old[row["scenario"]], row):
            s = source["scores"]["investigation_success"]
            d = s["dimensions"]
            lines.append(
                f"| {row['scenario']} | {source['scorer_version']} | {s['value']} | "
                + " | ".join(str(d[k]) for k in ("retention", "high_value", "resolution", "burden"))
                + f" | {', '.join(s['notes']) or '-'} |"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--replayed", type=Path, required=True)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    replayed = json.loads(args.replayed.read_text("utf-8"))
    report = json.loads(args.scores.read_text("utf-8"))
    serene = [r for r in report["rows"] if r["system"] == "serene"]
    if {r["scenario"] for r in serene} != set(replayed["scenarios"]):
        raise SystemExit("the replay does not cover the same scenarios as the stored run")
    rows = [rescore(r, replayed["scenarios"][r["scenario"]]) for r in serene]
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "scores.json").write_text(
        json.dumps({"rows": rows, "rescored_from": str(args.scores)}, indent=1, sort_keys=True),
        "utf-8",
    )
    md = rescore_md(replayed["run"], serene, rows)
    (args.out / "rescore.md").write_text(md, "utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
