"""Reproduce the synthetic #55 scenario and safe decision evidence, offline.

uv run python scripts/economics_report.py
uv run python scripts/economics_report.py --check
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from serene.adapters.cfoai import pickup_confirmation_decision
from serene.economics import Assumption, EconomicsInputs, evaluate, sensitivity
from serene.observability.telemetry import RecordingSink, SafeTelemetry

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "docs/economics/inputs.json"
REPORT = ROOT / "docs/economics/local-report.json"


def report() -> dict[str, Any]:
    document = json.loads(INPUTS.read_text(encoding="utf-8"))
    inputs = EconomicsInputs.model_validate_json(json.dumps(document["inputs"]))
    caregiver = {k: Assumption.model_validate(v) for k, v in document["caregiver_usage"].items()}
    sink = RecordingSink()
    decision = pickup_confirmation_decision(
        inputs,
        caregiver,
        eligible_options=frozenset({"ask_parent_telegram", "ask_caregiver_telegram"}),
        required_parent_question=False,
        telemetry=SafeTelemetry(sink),
    )
    return {
        "origin": "local deterministic calculation; NOT a cfo.ai response",
        "operating_scenario": "400 assumed families; optional pickup confirmation",
        "baseline": evaluate(inputs).model_dump(mode="json"),
        "sensitivity": [
            {
                "assumed_revenue_micro_usd": price,
                "assumed_llm_usage_bps": multiplier,
                "result": sensitivity(
                    inputs, revenue_micro_usd=price, llm_usage_bps=multiplier
                ).model_dump(mode="json"),
            }
            for price, multiplier in (
                (8_000_000, 10_000),
                (12_000_000, 20_000),
                (16_000_000, 10_000),
            )
        ],
        "decision": asdict(decision),
        "safe_trace": [{"name": name, "attributes": attrs} for name, attrs in sink.records],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = report()
    if args.check:
        expected = json.loads(REPORT.read_text(encoding="utf-8"))
        actual = json.loads(json.dumps(result))
        if actual != expected:
            print("economics report differs from reviewed fixture")
            return 1
        print("economics report reproducible")
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
