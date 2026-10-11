"""Historical gate tests need their pinned runtime, not the current application.

Only source bytes used for runtime integrity checks come from the pre-audit Git
revision. Manifests, gates, tapes, scorers and archived evidence remain the current
files, so their existing hash checks still detect any change. No archived source
is imported or executed, and no provider is contacted.
"""

from __future__ import annotations

import importlib
import io
import json
import shutil
import subprocess
import tarfile
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_REVISION = "be0cd9c8dfee04458d399b656a561b14126ab71f"
MODULES = (
    "eval.runners.shared_prefix_experiment",
    "eval.runners.live_gate4_experiment",
    "eval.runners.live_gate5_experiment",
)


@pytest.fixture(scope="module")
def frozen_contract_root(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    snapshot = tmp_path_factory.mktemp("frozen-contract-runtime")
    git = shutil.which("git")
    assert git is not None, "Historical contract tests require Git"
    archive = subprocess.run(  # noqa: S603 - resolved Git, fixed revision/path, no shell
        [git, "-C", str(ROOT), "archive", RUNTIME_REVISION, "--", "serene"],
        capture_output=True,
        check=True,
    )
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as source:
        source.extractall(snapshot, filter="data")

    modules = [importlib.import_module(name) for name in MODULES]
    names = {"uv.lock"}
    for module in modules:
        manifest = json.loads(module.MANIFEST.read_text("utf-8"))
        for key in (
            "implementation_sha256",
            "historical_files_sha256",
            "v3_files_sha256",
            "v4_files_sha256",
        ):
            names.update(manifest.get(key, {}))
        names.update(manifest["arms"]["A"]["protected_sha256"])
        names.update(
            str(p.relative_to(ROOT)) for p in (ROOT / "eval/fixtures").glob("hermes-v*.json")
        )
    for name in sorted(names):
        if name.startswith("serene/"):
            continue
        destination = snapshot / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, destination)

    with pytest.MonkeyPatch.context() as patch:
        for module in modules:
            patch.setattr(module, "ROOT", snapshot)
        yield snapshot
