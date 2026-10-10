"""Repository secret / PII scan (issue #59). Exit code 1 on any finding.

Scans tracked and untracked-but-not-ignored text files. Patterns cover common
credential formats and personal contact data. Allow-listed values are
placeholders and documentation addresses only.

    uv run python scripts/secret_scan.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_SUFFIXES = {".png", ".jpg", ".ico", ".woff", ".woff2", ".lock", ".pack"}
SKIP_FILES = {"package-lock.json", "uv.lock", "scripts/secret_scan.py"}

# Built from fragments so this file never matches its own patterns.
PATTERNS: dict[str, re.Pattern[str]] = {
    "aws_access_key": re.compile("AK" + r"IA[0-9A-Z]{16}"),
    "github_token": re.compile("gh" + r"[pousr]_[A-Za-z0-9]{36,}"),
    "slack_token": re.compile("xo" + r"x[abprs]-[A-Za-z0-9-]{10,}"),
    "private_key": re.compile("-----BEGIN " + r"(RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    "openai_style_key": re.compile(r"\bsk-" + r"(proj-|ant-)?[A-Za-z0-9_-]{24,}"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "telegram_bot_token": re.compile(r"\b\d{8,10}:" + r"AA[A-Za-z0-9_-]{33}\b"),
    "db_url_with_password": re.compile(
        r"postgres(ql)?://[^:\s/]+:(?!password@|postgres@)[^@\s]{4,}@"
    ),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
}
# Placeholders only: RFC 2606 example domains, Supabase's generated config sample
# (admin@email.com), commit attribution and GitHub noreply addresses.
ALLOWED_EMAILS = re.compile(
    r"@(example\.(com|org|net)|email\.com|anthropic\.com|users\.noreply\.github\.com)$"
)


def candidate_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    files = []
    for rel in out:
        path = ROOT / rel
        if rel in SKIP_FILES or path.name in SKIP_FILES or path.suffix in SKIP_SUFFIXES:
            continue
        if path.is_file():
            files.append(path)
    return files


def scan_text(text: str) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for name, pattern in PATTERNS.items():
            for match in pattern.finditer(line):
                if name == "email" and ALLOWED_EMAILS.search(match.group(0)):
                    continue
                findings.append((lineno, name))
    return findings


def scan(paths: Iterable[Path]) -> list[str]:
    report = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, name in scan_text(text):
            report.append(f"{path.relative_to(ROOT)}:{lineno}: {name}")
    return report


def main() -> int:
    report = scan(candidate_files())
    for line in report:
        print(line)
    print(f"secret/PII scan: {len(report)} finding(s)")
    return 1 if report else 0


if __name__ == "__main__":
    sys.exit(main())
