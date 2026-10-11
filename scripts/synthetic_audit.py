"""Check the reviewed synthetic corpus without rewriting or executing evals (#59).

Hashes bind human-reviewed provenance to exact bytes; they cannot infer whether
arbitrary prose is real. New/changed assets require provenance review, not rename.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "synthetic-data-manifest.json"
DATA_ROOTS = (
    "eval/fixtures/",
    "eval/reports/",
    "eval/holdout/pages/",
    "tests/fixtures/",
    "app/web/fixtures/",
)
GENERATORS = ("serene/testing/", "serene/demo/", "eval/scenarios/", "eval/tasks/")


def inventory(root: Path = ROOT) -> dict[str, str]:
    names = (
        subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],  # noqa: S607
            cwd=root,
            capture_output=True,
            check=True,
        )
        .stdout.decode("utf-8")
        .split("\0")
    )
    selected = {
        name
        for name in names
        if (
            name.startswith(DATA_ROOTS)
            and Path(name).suffix in {".json", ".jsonl", ".csv", ".html", ".md"}
        )
        or (name.startswith(GENERATORS) and name.endswith(".py"))
        or (name.startswith("tests/") and name.endswith(("_support.py", "_helpers.py")))
        or name
        in {
            "tests/conftest.py",
            "tests/test_maya_demo.py",
            "tests/test_demo_reset.py",
            "scripts/maya_demo.py",
            "scripts/demo_reset.py",
            "docs/maya-demo.md",
        }
    }
    return {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sorted(selected)
    }


def audit(root: Path = ROOT) -> list[str]:
    manifest = json.loads((root / "docs/synthetic-data-manifest.json").read_text("utf-8"))
    expected = manifest["sha256"]
    actual = inventory(root)
    errors = [
        f"{name}: synthetic provenance review required"
        for name in sorted(actual.keys() ^ expected.keys())
    ]
    errors.extend(
        f"{name}: reviewed synthetic bytes changed"
        for name in sorted(actual.keys() & expected.keys())
        if actual[name] != expected[name]
    )
    if manifest["classification"] != "SYNTHETIC" or not manifest["provenance"]:
        errors.append("missing synthetic provenance declaration")
    return errors


def main() -> int:
    errors = audit()
    for error in errors:
        print(error)
    print(
        f"synthetic data: {len(errors)} finding(s); {len(inventory())} reviewed assets/generators"
    )
    return bool(errors)


if __name__ == "__main__":
    sys.exit(main())
