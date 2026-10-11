"""Repository secret / PII scan (issue #59). Exit code 1 on any finding.

Scans tracked and untracked-but-not-ignored text files. Patterns cover common
credential formats and personal contact data. Allow-listed values are
placeholders and documentation addresses only.

    uv run python scripts/secret_scan.py
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Built from fragments so this file never matches its own patterns.
PATTERNS: dict[str, re.Pattern[str]] = {
    "aws_access_key": re.compile("AK" + r"IA[0-9A-Z]{16}"),
    "github_token": re.compile("gh" + r"[pousr]_[A-Za-z0-9]{36,}"),
    "github_fine_grained_token": re.compile("github_" + r"pat_[A-Za-z0-9_]{22,}"),
    "aws_temporary_key": re.compile("AS" + r"IA[0-9A-Z]{16}"),
    "slack_token": re.compile("xo" + r"x[abprs]-[A-Za-z0-9-]{10,}"),
    "private_key": re.compile("-----BEGIN " + r"(?:RSA |EC |OPENSSH |ENCRYPTED |)PRIVATE KEY-----"),
    "openai_style_key": re.compile(r"\bsk-" + r"(proj-|ant-)?[A-Za-z0-9_-]{24,}"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "telegram_bot_token": re.compile(r"\b\d{8,10}:" + r"AA[A-Za-z0-9_-]{33}\b"),
    "db_url_with_password": re.compile(
        r"postgres(ql)?://[^:\s/]+:(?!password@|postgres@)[^@\s]{4,}@"
    ),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "bearer_token": re.compile(r"\bBearer\s+([A-Za-z0-9_.~-]{12,})", re.IGNORECASE),
    "credential_literal": re.compile(
        r"""["']?\b(?:[A-Za-z0-9_]*(?:api_key|access_token|auth_token|secret|password)|token)"""
        r"""["']?\s*[:=]\s*["']([^"'\s]{8,})["']""",
        re.IGNORECASE,
    ),
}
PLACEHOLDER = re.compile(r"^(?:test|fake|dummy|example|placeholder|not[-_]a[-_]real)[-_]", re.I)
# Exact reviewed offline stand-ins in frozen eval/tests. No file is excluded.
# Values are fingerprints to keep reports and the allowlist free of credentials.
SYNTHETIC_LITERALS = {
    "serene/demo/maya.py": {"1f7bd41190e2"},  # offline synthetic webhook stand-in (#56)
    "eval/runners/live_gate4_probe.py": {"f0a838421d24"},
    "eval/runners/live_gate5_probe.py": {"f0a838421d24"},
    "tests/test_live_gate4_runtime.py": {"efc369f96d74", "e65f74547fff", "6eb205574678"},
    "tests/test_live_gate5_runtime.py": {"efc369f96d74", "e65f74547fff", "6eb205574678"},
    "tests/test_live_gate5_permits.py": {"4097889236a2"},
}
# Placeholders only: RFC 2606 example domains, Supabase's generated config sample
# (admin@email.com), commit attribution and GitHub noreply addresses.
ALLOWED_EMAILS = re.compile(
    r"@(example\.(com|org|net)|email\.com|anthropic\.com|users\.noreply\.github\.com)$"
)


def candidate_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")
    files = []
    for rel in out:
        path = ROOT / rel
        if path.is_file():
            files.append(path)
    return files


def scan_text(text: str, *, path: str = "") -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for name, pattern in PATTERNS.items():
            for match in pattern.finditer(line):
                if name == "email" and ALLOWED_EMAILS.search(match.group(0)):
                    continue
                if name in {"credential_literal", "bearer_token"} and PLACEHOLDER.match(
                    match.group(1)
                ):
                    continue
                if name == "credential_literal":
                    value = match.group(1)
                    if re.fullmatch(r"env\([A-Z_][A-Z0-9_]*\)", value):
                        continue
                    fingerprint = hashlib.sha256(value.encode()).hexdigest()[:12]
                    if fingerprint in SYNTHETIC_LITERALS.get(path, set()):
                        continue
                findings.append((lineno, name))
    return findings


def scan(paths: Iterable[Path]) -> list[str]:
    report = []
    for path in paths:
        try:
            text = path.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            report.append(f"{path.relative_to(ROOT)}: unreadable_file")
            continue
        if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
            report.append(f"{path.relative_to(ROOT)}: forbidden_env_file")
        for lineno, name in scan_text(text, path=path.relative_to(ROOT).as_posix()):
            report.append(f"{path.relative_to(ROOT)}:{lineno}: {name}")
    return report


def scan_history(root: Path = ROOT) -> list[str]:
    """Scan every unique blob reachable from HEAD; never fetch or print its contents."""
    objects = (
        subprocess.run(
            ["git", "rev-list", "--objects", "HEAD"],  # noqa: S607
            cwd=root,
            capture_output=True,
            check=True,
        )
        .stdout.decode("utf-8")
        .splitlines()
    )
    paths = dict(line.split(" ", 1) for line in objects if " " in line)
    types = (
        subprocess.run(
            ["git", "cat-file", "--batch-check"],  # noqa: S607
            cwd=root,
            input="\n".join(paths).encode(),
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .splitlines()
    )
    blobs = [line.split()[0] for line in types if line.split()[1] == "blob"]
    data = subprocess.run(
        ["git", "cat-file", "--batch"],  # noqa: S607
        cwd=root,
        input="\n".join(blobs).encode(),
        capture_output=True,
        check=True,
    ).stdout
    report: list[str] = []
    offset = 0
    for sha in blobs:
        end = data.index(b"\n", offset)
        size = int(data[offset:end].split()[2])
        text = data[end + 1 : end + 1 + size].decode("utf-8", errors="replace")
        path = paths[sha]
        report.extend(
            f"history:{sha[:12]}:{path}:{line}: {kind}" for line, kind in scan_text(text, path=path)
        )
        if Path(path).name == ".env" or (
            Path(path).name.startswith(".env.") and Path(path).name != ".env.example"
        ):
            report.append(f"history:{sha[:12]}:{path}: forbidden_env_file")
        offset = end + 1 + size + 1
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true", help="also scan HEAD ancestry blobs")
    args = parser.parse_args()
    report = scan(candidate_files())
    if args.history:
        report.extend(scan_history())
    for line in report:
        print(line)
    print(f"secret/PII scan: {len(report)} finding(s); no file/suffix exclusions")
    return 1 if report else 0


if __name__ == "__main__":
    sys.exit(main())
