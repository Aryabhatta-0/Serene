"""Controlled live A/B of the browse prompt: serene-browse/1 (recorded) vs the current one.

    set -a; . ./.env.local; set +a          # HERMES_API_SERVER_KEY (+ NEATLOGS_API_KEY)
    uv run python eval/runners/browse_prompt_ab.py --label browse-ab --repeats 2 \
        eval/reports/local/live/<live run dir> [...]

Issue #53. Live Serene runs showed browse replies that were a valid capture object
followed by a prose note, rejected by the strict wire (WIRE_NOT_JSON). End-to-end
reruns rarely reach the browse step, so this isolates it: every browse request
recorded in the given runs (raw/serene__*.jsonl, purpose=browse) is replayed
through the production `HermesBrowser` against the live model, once with the
recorded input verbatim ("before") and once with the current `_render_request` of
the same bounds ("after"), interleaved and alternating which arm goes first. Same
model, endpoint, pinned page and browser policy; only the prompt differs.

Telemetry passes through `SafeTelemetry` (central redaction) and goes to neatlogs
as two sessions, <run>__before and <run>__after. Writes, under
eval/reports/local/live/<label>-<utc>/: manifest.json, results.json and
raw_<arm>.jsonl (every exchange, verbatim).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import serene.adapters.browser.hermes_browser as hb  # noqa: E402
from eval.runners.runtime_live_compare import _git, _neatlogs  # noqa: E402
from eval.scenarios.runtime_live import LIVE_SOURCES, RecordingTransport  # noqa: E402
from serene.adapters.hermes import transport_from_env  # noqa: E402
from serene.observability.telemetry import SafeTelemetry  # noqa: E402
from serene.ports.evidence import EvidenceBrowseRequest  # noqa: E402
from serene.testing import SyntheticFamily  # noqa: E402

ARMS = ("before", "after")


class _Collect:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []

    def emit(self, name: str, attributes: Mapping[str, Any]) -> None:
        self.records.append((name, dict(attributes)))


def recorded_browse_inputs(run_dirs: list[str]) -> list[str]:
    inputs: list[str] = []
    for run_dir in run_dirs:
        for path in sorted((Path(run_dir) / "raw").glob("serene__*.jsonl")):
            for line in path.read_text("utf-8").splitlines():
                exchange = json.loads(line)
                if exchange["purpose"] == "browse":
                    inputs.append(exchange["input"])
    return inputs


def request_from(recorded: str, fam: SyntheticFamily) -> EvidenceBrowseRequest:
    bounds = json.loads(recorded.splitlines()[1])  # line 2 of a browse prompt is its bounds
    return EvidenceBrowseRequest(
        request_id=fam.new_id("erq"),
        child_id=fam.child_id,
        goal=bounds["goal"],
        subject=bounds["subject"],
        requested_fields=tuple(bounds["requested_fields"]),
        allowed_domains=tuple(bounds["allowed_domains"]),
        max_actions=bounds["max_actions"],
        forbidden_actions=tuple(bounds["forbidden_actions"]),
        max_age_days=bounds["max_age_days"],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("runs", nargs="+")
    args = parser.parse_args(argv)
    recorded = recorded_browse_inputs(args.runs)
    live = transport_from_env()
    if live is None or not recorded:
        print("UNAVAILABLE: no HERMES_API_SERVER_KEY or no recorded browse requests.")
        return 2
    fam = SyntheticFamily(seed="browse-ab")
    current = hb._render_request
    out = ROOT / "eval" / "reports" / "local" / "live"
    out = out / f"{args.label}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    out.mkdir(parents=True)
    rows: list[dict[str, Any]] = []
    sinks = {arm: _Collect() for arm in ARMS}
    raw: dict[str, list[dict[str, Any]]] = {arm: [] for arm in ARMS}
    for rep in range(args.repeats):
        for i, old in enumerate(recorded):
            for arm in ARMS if (rep + i) % 2 == 0 else ARMS[::-1]:
                request = request_from(old, fam)
                if arm == "after":
                    rendered = current(request, tuple(LIVE_SOURCES))
                    assert rendered.splitlines()[1] == old.splitlines()[1]  # same bounds
                # "before" sends the recorded prompt verbatim; nothing else differs.
                hb._render_request = (lambda _r, _p=(), _o=old: _o) if arm == "before" else current  # type: ignore[assignment]
                recording = RecordingTransport(live, system=f"browse-{arm}")
                browser = hb.HermesBrowser(
                    recording,
                    clock=fam.clock,
                    observer=fam.system,
                    telemetry=SafeTelemetry(sinks[arm]),
                    new_entity_id=fam.new_id,
                    pinned_sources=LIVE_SOURCES,
                )
                started = time.monotonic()
                try:
                    result = browser.acquire(request)
                finally:
                    hb._render_request = current
                ok = [x["response"] for x in recording.exchanges if "response" in x]
                rows.append(
                    {
                        "arm": arm,
                        "rep": rep,
                        "request": i,
                        "status": result.status,
                        "reason_codes": list(result.reason_codes),
                        "evidence": len(result.evidence),
                        "actions": result.actions_used,
                        "input_tokens": sum(r["usage"]["input_tokens"] or 0 for r in ok),
                        "output_tokens": sum(r["usage"]["output_tokens"] or 0 for r in ok),
                        "wall_ms": int((time.monotonic() - started) * 1000),
                        "transport_errors": sum(1 for x in recording.exchanges if "error" in x),
                    }
                )
                raw[arm].extend(recording.exchanges)
                print(arm, rep, i, result.status, result.reason_codes, flush=True)
    summary: dict[str, Any] = {}
    for arm in ARMS:
        with (out / f"raw_{arm}.jsonl").open("w", encoding="utf-8") as fh:
            for exchange in raw[arm]:
                fh.write(json.dumps(exchange, ensure_ascii=False) + "\n")
        mine = [r for r in rows if r["arm"] == arm]
        summary[arm] = {
            "calls": len(mine),
            "status": dict(Counter(r["status"] for r in mine)),
            "wire_not_json": sum("WIRE_NOT_JSON" in r["reason_codes"] for r in mine),
            "acquired_with_evidence": sum(
                r["status"] == "ACQUIRED" and r["evidence"] > 0 for r in mine
            ),
            "transport_errors": sum(r["transport_errors"] for r in mine),
            "tokens": sum(r["input_tokens"] + r["output_tokens"] for r in mine),
            "wall_s": round(sum(r["wall_ms"] for r in mine) / 1000, 1),
            "neatlogs": _neatlogs(
                f"{out.name}__{arm}",
                SimpleNamespace(traces=sinks[arm].records),  # type: ignore[arg-type]
            ),
        }
    manifest = {
        "label": args.label,
        "repeats": args.repeats,
        "recorded_requests": len(recorded),
        "sources": args.runs,
        "git": _git(),
        "prompts": {
            "before": "serene-browse/1 (recorded input, verbatim)",
            "after": hb.BROWSER_PROMPT_VERSION,
        },
        "pinned": list(LIVE_SOURCES),
        "order": "interleaved; the arm that goes first alternates",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), "utf-8")
    report = {"rows": rows, "summary": summary}
    (out / "results.json").write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps(summary, indent=2))
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
