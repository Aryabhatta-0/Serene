"""Run Serene and Baselines A/B over the runtime scenarios; write the standard report.

    uv run python eval/runners/runtime_compare.py

Serene rows come from the frozen scripted scenarios (architecture behaviour).
Baseline rows need a live model: they run only when HERMES_API_SERVER_KEY (and
HERMES_API_BASE_URL) point at a Hermes API server; otherwise they are recorded
as UNAVAILABLE - never filled with scripted replies, which would be an invented
baseline. Live baselines browse through the same bounded browser and allowlist;
the scenarios' fake web is not served to a live model, so browse-dependent
baseline rows are labelled accordingly.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.baselines.runtime_baselines import (  # noqa: E402
    MatchedBudget,
    baseline_a,
    baseline_b,
)
from eval.scenarios.runtime_scenarios import QUESTION, REPORTS, SCENARIOS  # noqa: E402
from eval.scorers.runtime_scorers import SCORER_VERSION, report_row  # noqa: E402
from serene.adapters.hermes import transport_from_env  # noqa: E402


def main() -> int:
    rows = []
    for scenario in SCENARIOS.values():
        row = report_row(scenario.run_serene(), scenario.oracle)
        row["mode"] = "scripted-model"
        rows.append(row)
    transport = transport_from_env()
    for factory in (baseline_a, baseline_b):
        for sid, scenario in SCENARIOS.items():
            if transport is None:
                rows.append(
                    {
                        "system": factory.__name__,
                        "scenario": sid,
                        "mode": "UNAVAILABLE",
                        "reason": "no live Hermes API server configured",
                    }
                )
                continue
            agent = factory(transport)
            t = agent.run(scenario, tuple(text for text, _ in REPORTS), QUESTION, seed=sid)
            row = report_row(t, scenario.oracle)
            row["mode"] = "live-model"
            rows.append(row)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "scorer_version": SCORER_VERSION,
        "matched_budget": MatchedBudget.from_serene().__dict__,
        "rows": rows,
    }
    out = ROOT / "eval" / "reports" / "local" / "runtime_compare.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
