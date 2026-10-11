"""A historical test context must never authorize a changed live runtime."""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path

import pytest

from tests.frozen_contract import MODULES

ROOT = Path(__file__).resolve().parents[1]
PRIVACY_CHANGED = {
    "serene/observability/telemetry.py",
    "serene/adapters/neatlogs_sink.py",
}


@pytest.mark.parametrize("name", MODULES)
def test_historical_gate_still_refuses_current_runtime(name: str) -> None:
    module = importlib.import_module(name)
    assert module.ROOT == ROOT  # historical fixture cannot leak into other tests
    manifest = module.load(module.MANIFEST)
    drift = {
        path
        for path, expected in manifest["arms"]["A"]["protected_sha256"].items()
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected
    }
    assert drift == PRIVACY_CHANGED
    with pytest.raises(module.Refused, match=r"^PROTECTED_RUNTIME_DRIFT$"):
        module.check_experiment(manifest)
