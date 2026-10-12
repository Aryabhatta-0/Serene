"""The ten frozen core failure-mode scenarios (#44): complete, declared, synthetic, pinned.

These tests check the scenario set itself and that the harness can run every
scenario. They deliberately do not assert PASS: a scenario that exposes a real
failure stays failing (docs/core-scenarios.md).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from eval.scenarios import core_scenarios as core

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FAILURE_MODES = {
    "premature_causation": "PREMATURE_CAUSATION",
    "hidden_confounder": "HIDDEN_CONFOUNDER",
    "missing_evidence": "MISSING_EVIDENCE",
    "conflicting_caregivers": "CONFLICTING_CAREGIVERS",
    "stale_learning": "STALE_LEARNING",
    "wrong_source": "WRONG_SOURCE",
    "browser_failure": "BROWSER_FAILURE",
    "unsafe_experiment": "UNSAFE_EXPERIMENT",
    "no_effect_intervention": "NO_EFFECT_INTERVENTION",
    "valid_contextual_learning": "VALID_CONTEXTUAL_LEARNING",
}
PINNED_SHA256 = "bdbbc1ad63c727ecf0f17ebe98d33ce5b5ae85d4ac46e7adb489ddf9c335225b"


@pytest.fixture(scope="module")
def frozen() -> dict[str, Any]:
    return core.load_frozen()


def test_exactly_ten_core_scenarios_exist(frozen: dict[str, Any]) -> None:
    ids = [s["scenario_id"] for s in frozen["scenarios"]]
    assert len(ids) == 10 == len(set(ids))
    assert set(ids) == set(REQUIRED_FAILURE_MODES) == set(core.DRIVERS)


def test_every_scenario_declares_its_target_failure_mode(frozen: dict[str, Any]) -> None:
    for s in frozen["scenarios"]:
        assert s["target_failure_mode"] == REQUIRED_FAILURE_MODES[s["scenario_id"]]
        assert s["model_mistake"].strip() and s["expected_behaviour"].strip()
        assert s["expected"], s["scenario_id"]
    declared = [s["target_failure_mode"] for s in frozen["scenarios"]]
    assert sorted(declared) == sorted(frozen["failure_modes"])
    assert len(set(declared)) == 10


def test_scenarios_are_frozen_and_versioned(frozen: dict[str, Any]) -> None:
    raw = core.FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PINNED_SHA256
    assert core.FIXTURE_SHA256.read_text("utf-8").split()[0] == PINNED_SHA256
    assert frozen["version"] == "core-scenarios/1"
    assert {s["version"] for s in frozen["scenarios"]} == {"core-scenarios/1"}


def test_a_changed_fixture_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    edited = core.FIXTURE.read_text("utf-8").replace('"DENIED"', '"GRANTED"', 1)
    (tmp_path / "core-scenarios-v1.json").write_text(edited, "utf-8")
    (tmp_path / "core-scenarios-v1.sha256").write_bytes(core.FIXTURE_SHA256.read_bytes())
    monkeypatch.setattr(core, "FIXTURE", tmp_path / "core-scenarios-v1.json")
    monkeypatch.setattr(core, "FIXTURE_SHA256", tmp_path / "core-scenarios-v1.sha256")
    with pytest.raises(ValueError, match="fixture changed"):
        core.load_frozen()


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"(?<![\d-])(?:\+\d{1,3}[ -]?)?\(?\d{3}\)?[ -]?\d{3}[ -]?\d{4}(?![\d-])")
_URL_HOST = re.compile(r"https?://([^/\s\"']+)")
# RFC 2606 reserved names only: nothing here can point at a real site.
_RESERVED = re.compile(r"(^|\.)example\.(org|net|com)$")


def test_no_real_child_or_family_data(frozen: dict[str, Any]) -> None:
    assert frozen["classification"] == "SYNTHETIC"
    texts = {
        "fixture": core.FIXTURE.read_text("utf-8"),
        "drivers": Path(core.__file__).read_text("utf-8"),
    }
    for name, text in texts.items():
        assert not _EMAIL.search(text), name
        assert not _PHONE.search(text), name
        for host in _URL_HOST.findall(text):
            assert _RESERVED.search(host), f"{name}: non-reserved host {host}"
    for s in frozen["scenarios"]:
        assert s["synthetic_child"].startswith("unnamed synthetic child")
        assert s["synthetic_seed"].startswith("core-")
    manifest = json.loads((ROOT / "docs" / "synthetic-data-manifest.json").read_text("utf-8"))
    for path in (
        "eval/fixtures/core-scenarios-v1.json",
        "eval/scenarios/core_scenarios.py",
        "eval/tasks/core_scenarios.py",
    ):
        assert path in manifest["sha256"], path


@pytest.mark.parametrize("scenario_id", sorted(REQUIRED_FAILURE_MODES))
def test_harness_runs_every_scenario_and_observes_each_expectation(
    frozen: dict[str, Any], scenario_id: str
) -> None:
    (spec,) = (s for s in frozen["scenarios"] if s["scenario_id"] == scenario_id)
    observed = core.DRIVERS[scenario_id]()
    assert set(spec["expected"]) <= set(observed)
    assert core.DRIVERS[scenario_id]() == observed  # deterministic


def test_grading_is_strict() -> None:
    assert core.grade({"a": 0}, {"a": 0}) == (True, [])
    assert not core.grade({"a": 0}, {"a": 1})[0]
    assert not core.grade({"a": 0}, {})[0]
    assert core.grade({"t": {"one_of": ["X", "Y"]}}, {"t": "Y"})[0]
    assert not core.grade({"t": {"one_of": ["X"]}}, {"t": "WAITING"})[0]
    assert core.grade({"f": {"contains": "B"}}, {"f": ["A", "B"]})[0]
    assert not core.grade({"f": {"contains": "B"}}, {"f": "B"})[0]
