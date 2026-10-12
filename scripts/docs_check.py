"""Validate final documentation links, anchors, paths and GitHub references.

The canonical docs and final README/checklist use inline links and repository paths.
External GitHub issue/PR and blob links are checked only with --github (read-only).
No eval, provider, holdout or product code is executed.
"""

from __future__ import annotations

import argparse
import json
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
FINAL_DOCS = (
    *CORE_DOCS,
    ROOT / "README.md",
    ROOT / "docs" / "final-demo-checklist.md",
    ROOT / "docs" / "final-docs-validation.md",
)
REPOSITORY = "Sathvikar01/morrow"
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
INLINE_PATH = re.compile(
    r"`((?:serene|docs|tests|scripts|eval|app|supabase|memory_repo|\.entire|\.github)/"
    r"[^`\s]+|\.env\.example)`"
)
GITHUB_REF = re.compile(r"https://github\.com/Sathvikar01/morrow/(issues|pull)/(\d+)")
GITHUB_BLOB = re.compile(r"https://github\.com/Sathvikar01/morrow/blob/([^/]+)/([^#?\s)]+)")


def prose(path: Path) -> str:
    """Ignore fenced code examples, where output paths need not already exist."""
    return re.sub(
        r"^```[^\n]*\n.*?^```\s*$", "", path.read_text(encoding="utf-8"), flags=re.M | re.S
    )


def anchors(path: Path) -> set[str]:
    """GitHub heading slugs for these docs, including duplicate-heading suffixes."""
    found: set[str] = set()
    counts: dict[str, int] = {}
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", prose(path), flags=re.M):
        heading = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", heading)
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        found.add(f"{slug}-{count}" if count else slug)
    return found


def check_links(paths: tuple[Path, ...]) -> list[str]:
    failures: list[str] = []
    for path in paths:
        if not path.is_file():
            failures.append(f"missing document: {path.name}")
            continue
        contents = prose(path)
        targets = [(target.strip("<>"), path.parent) for target in LINK.findall(contents)]
        targets.extend((target, ROOT) for target in INLINE_PATH.findall(contents))
        for target, base in targets:
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc:
                continue
            resolved = (base / unquote(parsed.path)).resolve() if parsed.path else path
            if not resolved.is_relative_to(ROOT):
                failures.append(f"{path.name}: outside repository: {target}")
            elif not resolved.exists():
                failures.append(f"{path.name}: missing {target}")
            elif (
                parsed.fragment
                and resolved.suffix == ".md"
                and unquote(parsed.fragment) not in anchors(resolved)
            ):
                failures.append(f"{path.name}: missing heading: {target}")
    return failures


def issue_numbers(paths: tuple[Path, ...]) -> set[int]:
    numbers: set[int] = set()
    for path in paths:
        contents = prose(path)
        # Local heading fragments (e.g. setup.md#5-merge-gates) are not issue #5.
        visible = re.sub(r"\]\([^)]+\)", "]", contents)
        numbers.update(int(n) for n in re.findall(r"#(\d+)", visible))
        numbers.update(int(n) for _, n in GITHUB_REF.findall(contents))
        for first, last in re.findall(r"#(\d+)[\u2013-]#?(\d+)", visible):
            numbers.update(range(int(first), int(last) + 1))
    return numbers


def validate_github_refs(paths: tuple[Path, ...], known: dict[int, str]) -> list[str]:
    """The issues API includes PRs; require URL kinds to match, not just numbers."""
    failures = [
        f"missing GitHub reference #{n}" for n in sorted(issue_numbers(paths) - known.keys())
    ]
    for path in paths:
        for kind, number in GITHUB_REF.findall(prose(path)):
            if int(number) in known and known[int(number)] != kind:
                failures.append(f"{path.name}: wrong GitHub URL kind for #{number}: {kind}")
    return failures


def github_check(paths: tuple[Path, ...]) -> list[str]:
    gh = shutil.which("gh")
    if gh is None:
        return ["--github requires the gh CLI"]
    # Fixed repository/read-only API; no shell, credentials or response bodies printed.
    response = subprocess.run(  # noqa: S603 - resolved gh, read-only API
        [
            gh,
            "api",
            "--paginate",
            "--slurp",
            f"repos/{REPOSITORY}/issues?state=all&per_page=100",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if response.returncode:
        return ["GitHub reference lookup failed (check gh authentication/network)"]
    known = {
        item["number"]: "pull" if "pull_request" in item else "issues"
        for page in json.loads(response.stdout)
        for item in page
    }
    failures = validate_github_refs(paths, known)
    blobs = {blob for path in paths for blob in GITHUB_BLOB.findall(prose(path))}
    for revision, filename in sorted(blobs):
        # Validate the actual remote file at its cited revision, including unmerged
        # protocol history explicitly labelled as such in evaluation.md.
        response = subprocess.run(  # noqa: S603 - resolved gh, read-only API
            [gh, "api", f"repos/{REPOSITORY}/contents/{filename}?ref={revision}", "--jq", ".path"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if response.returncode or response.stdout.strip() != filename:
            failures.append(f"missing GitHub blob: {revision}:{filename}")
    print(
        f"GitHub: {len(issue_numbers(paths))} issue/PR references; "
        f"{len(blobs)} pinned files checked"
    )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--github", action="store_true", help="Read-only issue/PR/blob validation")
    args = parser.parse_args()
    paths = tuple(p.resolve() for p in args.paths) or FINAL_DOCS
    failures = check_links(paths)
    if not failures and args.github:
        failures.extend(github_check(paths))
    for failure in failures:
        print(failure)
    count = sum(
        len(LINK.findall(prose(p))) + len(INLINE_PATH.findall(prose(p)))
        for p in paths
        if p.is_file()
    )
    print(f"Docs: {len(paths)}; link/path references: {count}; failures: {len(failures)}")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
