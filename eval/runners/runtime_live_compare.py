"""Run the frozen runtime scenarios against a LIVE Hermes for Serene and Baselines A/B.

    set -a; . ./.env.local; set +a          # HERMES_API_SERVER_KEY, HERMES_API_BASE_URL
    uv run python eval/runners/runtime_live_compare.py --label before

No scripted replies: every model call goes to the Hermes API server. Writes,
under eval/reports/local/live/<label>-<utc>/:

    manifest.json           versions, budget, faults, endpoint health, git state
    scores.json             deterministic scorer rows (standard format) + summary
    raw/<system>__<scenario>.jsonl     every model exchange, verbatim
    traces/serene__<scenario>.jsonl    SafeTelemetry records (already redacted)

When NEATLOGS_API_KEY is set the same redacted records are also sent to
neatlogs through the committed `serene.adapters.neatlogs_sink.NeatlogsSink`, which
packs them into traces under the ingest body limit that share one session id: the
run id is the neatlogs session handle, and the flush report is kept in scores.json.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.baselines.runtime_baselines import BASELINE_PROMPT_VERSION, MatchedBudget  # noqa: E402
from eval.scenarios.runtime_live import (  # noqa: E402
    FAULTS,
    LIVE_ALLOWED,
    LIVE_SOURCES,
    PARENT_FACTS,
    SYSTEMS,
    LiveResult,
    live_oracle,
)
from eval.scenarios.runtime_scenarios import SCENARIOS  # noqa: E402
from eval.scorers.runtime_scorers import SCORER_VERSION, Oracle, report_row  # noqa: E402
from serene.adapters.browser.hermes_browser import BROWSER_PROMPT_VERSION  # noqa: E402
from serene.adapters.hermes import transport_from_env  # noqa: E402
from serene.adapters.hermes.runtime import PROMPT_VERSION  # noqa: E402
from serene.policies.scorers import SCORER_VERSION as TRUST_SCORER_VERSION  # noqa: E402
from serene.policies.scorers import (  # noqa: E402
    EpistemicClaim,
    EpistemicError,
    score_authority,
    score_epistemic,
)


def _git() -> dict[str, Any]:
    def run(*args: str) -> str:
        return subprocess.run(  # noqa: S603 - fixed git read-only arguments
            ["git", *args],  # noqa: S607 - git from PATH, as every developer command
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()

    return {"head": run("rev-parse", "HEAD"), "dirty": bool(run("status", "--porcelain"))}


def _health() -> Any:
    base = (os.environ.get("HERMES_API_BASE_URL") or "http://127.0.0.1:8642/v1").rstrip("/")
    url = base.removesuffix("/v1") + "/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310 - loopback/https only
            return json.loads(resp.read(65_536).decode("utf-8"))
    except Exception as exc:  # health is informational only
        return {"error": type(exc).__name__}


def _neatlogs(run_id: str, result: LiveResult) -> dict[str, Any]:
    """Send one run's redacted records as one neatlogs session (the run id)."""
    if not result.traces:
        return {"sent": False, "reason": "no traces"}
    from serene.adapters.neatlogs_sink import NeatlogsSink, build_sink

    sink = build_sink("serene-live-eval", session_id=run_id)
    if not isinstance(sink, NeatlogsSink):
        return {"sent": False, "reason": "NEATLOGS_API_KEY unset"}
    for name, attrs in result.traces:  # already redacted by SafeTelemetry
        sink.emit(name, attrs)
    report = sink.flush()
    return {
        "sent": report.ok,
        "session_id": report.session_id,
        "spans": report.spans,
        "batches": report.batches,
        "batches_sent": report.batches_sent,
        "dropped_spans": report.dropped_spans,
        "errors": list(report.errors),
    }


def _trust_scores(result: LiveResult, oracle: Oracle) -> dict[str, Any]:
    """The merged deterministic trust scorers (#46, #47), where they apply.

    Epistemic (#47) scores every system's final claim: a single asserted cause is a
    causal claim, parking is an abstention, and the oracle's expected terminal is the
    gold abstention label; Serene's own ledger is also replayed for invalid promotions.
    Authority (#46) needs a ledger trajectory, so it is scored for Serene only and is
    None (not measured) for the baselines, which keep no ledger.
    """
    t = result.trajectory
    claim = EpistemicClaim(
        subject_id=None,
        causal=t.conclusion is not None,
        abstained=t.terminal not in {"COMPLETE", "CLAIMED_COMPLETE"},
        expected_abstain=oracle.expected_terminal == "PARKED_UNRESOLVED",
    )
    epistemic = score_epistemic(result.ledger_events, [claim])
    authority = score_authority(result.ledger_events) if result.ledger_events else None
    return {
        "scorer_version": TRUST_SCORER_VERSION,
        "epistemic_errors": {e.value: epistemic.counts[e.value] for e in EpistemicError},
        "correct_abstentions": epistemic.correct_abstentions,
        "unnecessary_abstentions": epistemic.unnecessary_abstentions,
        "authority_violations": None if authority is None else authority.counts,
        "ledger_events": len(result.ledger_events),
    }


def _findings(row: dict[str, Any]) -> dict[str, int]:
    """Exact runtime-scorer findings, by the name each scorer gives them."""
    scores = row["scores"]
    critical = [c.split(":", 1)[0] for s in scores.values() for c in s["critical"]]
    notes = [n.split(":", 1) for s in scores.values() for n in s["notes"]]
    return {
        "off_allowlist_evidence_used": critical.count("USED_OFF_ALLOWLIST_SOURCE"),
        "rejected_evidence_used": critical.count("USED_REJECTED_EVIDENCE"),
        "false_completions": critical.count("FALSE_COMPLETION"),
        "wrong_cause_concluded": sum(1 for n in notes if n[0] == "CONCLUDED_WRONG_CAUSE"),
        "unnecessary_questions": sum(
            int(n[1]) for n in notes if n[0] == "UNNECESSARY_QUESTIONS" and len(n) == 2
        ),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_system: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_system[row["system"]].append(row)
    out: dict[str, Any] = {}
    for system, items in by_system.items():
        dims = sorted({d for r in items for d in r["scores"]})
        findings = [_findings(r) for r in items]
        trust = [r["trust_scorers"] for r in items]
        authority = [t["authority_violations"] for t in trust]
        out[system] = {
            "runs": len(items),
            "all_runtime_scorers_passed": sum(
                1 for r in items if all(s["passed"] for s in r["scores"].values())
            ),
            "mean": {
                d: round(sum(r["scores"][d]["value"] for r in items) / len(items), 4) for d in dims
            },
            "passed": {d: sum(1 for r in items if r["scores"][d]["passed"]) for d in dims},
            "runtime_findings": {k: sum(f[k] for f in findings) for k in findings[0]},
            "evidence_used": sum(r["evidence_use"]["used"] for r in items),
            "evidence_used_verified": sum(r["evidence_use"]["verified"] for r in items),
            "trust_epistemic_errors": {
                k: sum(t["epistemic_errors"][k] for t in trust)
                for k in trust[0]["epistemic_errors"]
            },
            "trust_unnecessary_abstentions": sum(t["unnecessary_abstentions"] for t in trust),
            "trust_authority_violations": (
                None
                if any(a is None for a in authority)
                else {k: sum(a[k] for a in authority) for k in authority[0]}
            ),
            "terminal": dict(Counter(r["terminal"] for r in items)),
            "model_calls": sum(r["budget"]["model_calls"] for r in items),
            "browse_actions": sum(r["budget"]["browse_actions"] for r in items),
            "input_tokens": sum(r["live"]["input_tokens"] for r in items),
            "output_tokens": sum(r["live"]["output_tokens"] for r in items),
            "transport_errors": sum(r["live"]["transport_errors"] for r in items),
            "wall_ms": sum(r["live"]["wall_ms"] for r in items),
        }
    return out


TABLE_COLUMNS: Final = (
    "system",
    "runs",
    "all 3 runtime scorers passed",
    "used evidence verified",
    "off-allowlist evidence used",
    "rejected evidence used",
    "false completions",
    "wrong cause concluded",
    "#47 missing abstention",
    "#47 premature causality",
    "#46 authority violations",
    "unnecessary questions",
    "investigation score",
    "recovery score",
    "model calls",
    "tokens",
    "wall s",
)


def table(summary: dict[str, Any]) -> str:
    """Markdown summary whose column names say exactly what each number counts."""
    lines = ["| " + " | ".join(TABLE_COLUMNS) + " |", "|" + "---|" * len(TABLE_COLUMNS)]
    for system, s in summary.items():
        f, e = s["runtime_findings"], s["trust_epistemic_errors"]
        authority = s["trust_authority_violations"]
        used = s["evidence_used"]
        cells = [
            system,
            s["runs"],
            f"{s['all_runtime_scorers_passed']}/{s['runs']}",
            f"{s['evidence_used_verified']}/{used}" if used else "n/a (none used)",
            f["off_allowlist_evidence_used"],
            f["rejected_evidence_used"],
            f["false_completions"],
            f["wrong_cause_concluded"],
            e["MISSING_ABSTENTION"],
            e["PREMATURE_CAUSALITY"],
            "n/a (no ledger)" if authority is None else sum(authority.values()),
            f["unnecessary_questions"],
            f"{s['mean']['investigation_success']:.2f}",
            f"{s['mean']['recovery_state']:.2f}",
            s["model_calls"],
            f"{s['input_tokens'] + s['output_tokens']:,}",
            round(s["wall_ms"] / 1000),
        ]
        lines.append("| " + " | ".join(str(c) for c in cells) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--systems", default=",".join(SYSTEMS))
    parser.add_argument("--scenarios", default=",".join(SCENARIOS))
    args = parser.parse_args(argv)
    live = transport_from_env()
    if live is None:
        print("UNAVAILABLE: HERMES_API_SERVER_KEY is not set; no live run, no numbers.")
        return 2
    started = datetime.now(UTC)
    out = ROOT / "eval" / "reports" / "local" / "live" / f"{args.label}-{started:%Y%m%dT%H%M%SZ}"
    (out / "raw").mkdir(parents=True)
    (out / "traces").mkdir()
    rows: list[dict[str, Any]] = []
    models: set[str] = set()
    for sid in args.scenarios.split(","):
        for system in args.systems.split(","):
            run_id = f"{out.name}__{system}__{sid}"
            result = SYSTEMS[system](sid, live)
            row = report_row(result.trajectory, live_oracle(sid))
            ok = [e["response"] for e in result.exchanges if "response" in e]
            models |= {str(r["model"]) for r in ok if r["model"]}
            row["mode"] = "live-model"
            row["run_id"] = run_id
            row["terminal"] = result.trajectory.terminal
            row["failures_recorded"] = list(result.trajectory.failures_recorded)
            row["notes"] = result.notes
            row["live"] = {
                "exchanges": len(result.exchanges),
                "transport_errors": sum(1 for e in result.exchanges if "error" in e),
                "input_tokens": sum(r["usage"]["input_tokens"] or 0 for r in ok),
                "output_tokens": sum(r["usage"]["output_tokens"] or 0 for r in ok),
                "wall_ms": result.wall_ms,
            }
            row["evidence_use"] = {
                "used": sum(1 for e in result.trajectory.evidence if e.used),
                "verified": sum(
                    1 for e in result.trajectory.evidence if e.used and e.verification == "VERIFIED"
                ),
            }
            row["trust_scorers"] = _trust_scores(result, live_oracle(sid))
            row["neatlogs"] = _neatlogs(run_id, result)
            rows.append(row)
            stem = f"{system}__{sid}"
            with (out / "raw" / f"{stem}.jsonl").open("w", encoding="utf-8") as fh:
                for exchange in result.exchanges:
                    fh.write(json.dumps(exchange, ensure_ascii=False) + "\n")
            if result.traces:
                with (out / "traces" / f"{stem}.jsonl").open("w", encoding="utf-8") as fh:
                    for name, attrs in result.traces:
                        record = {"name": name, "attributes": attrs}
                        fh.write(json.dumps(record, default=str) + "\n")
            print(
                f"{system:<30} {sid:<26} terminal={row['terminal']:<18} "
                + " ".join(f"{k}={v['value']:.2f}" for k, v in row["scores"].items())
                + f" calls={row['budget']['model_calls']} errors={row['live']['transport_errors']}"
            )
    manifest = {
        "label": args.label,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "git": _git(),
        "hermes": {
            "base_url": os.environ.get("HERMES_API_BASE_URL"),
            "health": _health(),
            "served_models": sorted(models),
        },
        "versions": {
            "scorer": SCORER_VERSION,
            "trust_scorer": TRUST_SCORER_VERSION,
            "runtime_prompt": PROMPT_VERSION,
            "browser_prompt": BROWSER_PROMPT_VERSION,
            "baseline_prompt": BASELINE_PROMPT_VERSION,
        },
        "matched_budget": MatchedBudget.from_serene().__dict__,
        "faults": {sid: FAULTS[sid].__dict__ for sid in args.scenarios.split(",")},
        "parent_facts": {sid: PARENT_FACTS[sid] for sid in args.scenarios.split(",")},
        "evidence_sources": list(LIVE_SOURCES),
        "browse_allowlist": list(LIVE_ALLOWED),
        "sampling": "Hermes server defaults (not pinned by the client)",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), "utf-8")
    report: dict[str, Any] = {"rows": rows, "summary": _summary(rows)}
    (out / "scores.json").write_text(json.dumps(report, indent=2, sort_keys=True), "utf-8")
    (out / "table.md").write_text(table(report["summary"]) + "\n", "utf-8")
    print(table(report["summary"]))
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
