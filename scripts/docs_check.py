"""Check local Markdown targets; optionally verify GitHub issue references (#60)."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
CORE_DOCS = tuple(
    ROOT / "docs" / f"{name}.md"
    for name in ("architecture", "evidence-model", "safety", "privacy", "evaluation")
)
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def check_links(paths: tuple[Path, ...]) -> list[str]:
    """Check file targets, excluding external URLs and same-document anchors."""
    failures = []
    for path in paths:
        for target in LINK.findall(path.read_text(encoding="utf-8")):
            target = target.strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or target.startswith("#"):
                continue
            resolved = path.parent / unquote(parsed.path)
            if not resolved.exists():
                failures.append(f"{path.relative_to(ROOT)}: missing {target}")
    return failures


def issue_numbers(paths: tuple[Path, ...]) -> set[int]:
    numbers: set[int] = set()
    for path in paths:
        text = path.read_text(encoding="utf-8")
        numbers.update(int(n) for n in re.findall(r"#(\d+)", text))
        for first, last in re.findall(r"#(\d+)[\u2013-]#?(\d+)", text):
            numbers.update(range(int(first), int(last) + 1))
    return numbers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--github", action="store_true", help="Verify refs with gh read-only API")
    args = parser.parse_args()
    paths = tuple(p.resolve() for p in args.paths) or CORE_DOCS
    failures = check_links(paths)
    if args.github:
        # No shell interpolation, credentials or issue content in the output.
        gh = shutil.which("gh")
        if gh is None:
            parser.error("--github requires the gh CLI")
        response = subprocess.run(  # noqa: S603 - resolved gh, fixed public read-only API
            [
                gh,
                "api",
                "--paginate",
                "repos/Sathvikar01/morrow/issues?state=all&per_page=100",
                "--jq",
                ".[].number",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        known = {int(number) for number in response.stdout.splitlines()}
        failures.extend(
            f"missing GitHub reference #{n}" for n in sorted(issue_numbers(paths) - known)
        )
    for failure in failures:
        print(failure)
    print(
        f"Docs: {len(paths)}; failures: {len(failures)}; references: {sorted(issue_numbers(paths))}"
    )
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
