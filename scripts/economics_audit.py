"""Mechanically check #55's acceptance map against a fresh pytest JUnit report."""

from __future__ import annotations

import argparse
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("junit", type=Path)
    args = parser.parse_args()
    audit = json.loads((ROOT / "docs/economics/acceptance-audit.json").read_text(encoding="utf-8"))
    xml = args.junit.read_text(encoding="utf-8")
    if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
        raise ValueError("JUnit entity declarations are not accepted")
    # This is a local pytest result; entity/doctype declarations are refused above.
    cases = list(ET.fromstring(xml).iter("testcase"))  # noqa: S314
    failures: list[str] = []
    for criterion in audit["criteria"]:
        for selector in criterion["tests"]:
            file, function = selector.split("::")
            classname = file.removesuffix(".py").replace("/", ".")
            matches = [
                c
                for c in cases
                if c.get("classname") == classname and c.get("name", "").split("[")[0] == function
            ]
            if not matches or any(
                any(c.find(tag) is not None for tag in ("failure", "error", "skipped"))
                for c in matches
            ):
                failures.append(f"{criterion['id']}: {selector}")
        for artifact in criterion["artifacts"]:
            if not (ROOT / artifact).is_file():
                failures.append(f"{criterion['id']}: missing {artifact}")
    changed = subprocess.run(  # noqa: S603 - fixed git operation, local reviewed commit
        ["git", "diff", "--name-only", audit["base_commit"]],  # noqa: S607
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],  # noqa: S607
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    for file in set(changed + untracked):
        if file.startswith(("eval/", "app/web/", "serene/adapters/hermes/")):
            failures.append(f"FORBIDDEN_SCOPE: {file}")
    for failure in failures:
        print(failure)
    print(f"#55 acceptance audit: {len(audit['criteria'])} criteria, {len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
