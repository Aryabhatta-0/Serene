"""The hidden holdout split (#45): explicit, withheld by default, never named by dev configs."""

from __future__ import annotations

import json
from pathlib import Path

from eval.holdout.live_holdout import HOLDOUT, HOLDOUT_PAGES_SHA
from eval.runners.runtime_live_compare import holdout_refusal, scenarios_for
from eval.scenarios.runtime_live import DEV
from serene.domain.canonical import sha256_hex
from serene.policies.external_evidence import host_of

ROOT = Path(__file__).resolve().parents[1]
# sha256 of each holdout page at HOLDOUT_PAGES_SHA, as served by raw.githubusercontent.com
# on 2026-10-11. Editing a page needs a new pin.
PINNED = {
    "eval/holdout/pages/preschool-daily-schedule.html": (
        "b2f6cbd0abbbc4d43129bfcae9d9747dc632e4e223783579e55ec4f5f2adf6e6"
    ),
    "eval/holdout/pages/preschool-dropoff-procedure.html": (
        "048281801dd06ac5da53cddc1f1c4cecf2fc86f8a67463d9c137a51bb7609afd"
    ),
}


def test_the_split_is_explicit_and_sized_as_documented() -> None:
    assert 6 <= len(DEV) <= 7 and 2 <= len(HOLDOUT) <= 3
    assert {s.split for s in DEV.values()} == {"dev"}
    assert {s.split for s in HOLDOUT.values()} == {"holdout"}
    assert not set(DEV) & set(HOLDOUT)


def test_the_holdout_is_a_different_situation_not_a_copy_of_dev() -> None:
    dev_questions = {s.question for s in DEV.values()}
    dev_reports = {text for s in DEV.values() for text, _ in s.reports}
    for spec in HOLDOUT.values():
        assert spec.question not in dev_questions
        assert not {text for text, _ in spec.reports} & dev_reports


def test_default_runs_withhold_the_holdout() -> None:
    assert scenarios_for("dev") == DEV
    assert set(scenarios_for("holdout")) == set(HOLDOUT)


def test_no_development_config_names_a_holdout_scenario() -> None:
    allowed = {ROOT / "eval" / "holdout" / "live_holdout.py"}
    searched = [
        *(ROOT / "eval").rglob("*.py"),
        *(ROOT / "serene").rglob("*.py"),
        *(ROOT / "eval").rglob("*.json"),
    ]
    for path in searched:
        if path in allowed or "reports" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for sid in HOLDOUT:
            assert sid not in text, f"{path.relative_to(ROOT)} names holdout scenario {sid}"
    # Production code never imports the holdout; only the runner does, lazily, on request.
    for path in (ROOT / "serene").rglob("*.py"):
        assert "live_holdout" not in path.read_text(encoding="utf-8", errors="replace")


def test_holdout_pages_are_sha_pinned_and_byte_identical_to_the_fixtures() -> None:
    prefix = f"https://raw.githubusercontent.com/Sathvikar01/morrow/{HOLDOUT_PAGES_SHA}/"
    assert len(HOLDOUT_PAGES_SHA) == 40
    for spec in HOLDOUT.values():
        for url in spec.sources:
            assert url.startswith(prefix) and host_of(url) in spec.allowed
            relative = url.removeprefix(prefix)
            assert sha256_hex((ROOT / relative).read_bytes()) == PINNED[relative]


def test_the_holdout_runs_once_per_commit_from_a_clean_tree(tmp_path: Path) -> None:
    head = "a" * 40
    assert holdout_refusal({"head": head, "dirty": True}, tmp_path) is not None
    assert holdout_refusal({"head": head, "dirty": False}, tmp_path) is None
    done = tmp_path / "holdout-before-20261011T000000Z"
    done.mkdir()
    (done / "manifest.json").write_text(
        json.dumps({"split": "holdout", "git": {"head": head}}), "utf-8"
    )
    assert "already exists" in str(holdout_refusal({"head": head, "dirty": False}, tmp_path))
    assert holdout_refusal({"head": "b" * 40, "dirty": False}, tmp_path) is None
