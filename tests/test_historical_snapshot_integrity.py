"""The historical snapshot retains real byte-integrity validation."""

from __future__ import annotations

import importlib

import pytest

from tests.frozen_contract import (
    MODULES,
    frozen_contract_root,  # noqa: F401 - pytest fixture
)

pytestmark = pytest.mark.usefixtures("frozen_contract_root")


@pytest.mark.parametrize("name", MODULES)
@pytest.mark.parametrize(
    "path",
    (
        "serene/observability/telemetry.py",
        "eval/fixtures/pages/daycare-pickup-policy.html",
    ),
)
def test_snapshot_tampering_still_fails_closed(name: str, path: str) -> None:
    module = importlib.import_module(name)
    manifest = module.load(module.MANIFEST)
    module.check_experiment(manifest)
    target = module.ROOT / path
    original = target.read_bytes()
    try:
        target.write_bytes(original + b"\nTAMPERED_SYNTHETIC_TEST\n")
        with pytest.raises(module.Refused, match=r"^PROTECTED_RUNTIME_DRIFT$"):
            module.check_experiment(manifest)
    finally:
        target.write_bytes(original)
    module.check_experiment(manifest)
