"""Secrets, PII and environment documentation hygiene (issue #59)."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("secret_scan", ROOT / "scripts" / "secret_scan.py")
assert _spec and _spec.loader
secret_scan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(secret_scan)


def test_repository_contains_no_secrets_or_personal_emails() -> None:
    assert secret_scan.scan(secret_scan.candidate_files()) == []


def test_scanner_catches_planted_credentials() -> None:
    planted = "\n".join(
        [
            "token = " + "gh" + "p_" + "a" * 36,
            "key = " + "AK" + "IA" + "B" * 16,
            "url = postgresql://svc:" + "hunter2x" + "@db.internal:5432/x",
            "contact = someone@" + "gmail.com",
        ]
    )
    names = {name for _, name in secret_scan.scan_text(planted)}
    assert names == {"github_token", "aws_access_key", "db_url_with_password", "email"}
    assert secret_scan.scan_text("ok = dev@example.com\npostgresql://u:password@host") == []


def test_env_example_documents_every_variable_the_code_reads() -> None:
    documented = {
        line.split("=", 1)[0].strip()
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    pattern = re.compile(r"""(?:environ\.get|getenv|environ\[)\(?\s*["']([A-Z0-9_]+)["']""")
    referenced: set[str] = set()
    for folder in ("serene", "scripts", "eval"):
        for path in (ROOT / folder).rglob("*.py"):
            referenced |= set(pattern.findall(path.read_text(encoding="utf-8")))
    assert referenced, "expected at least one environment variable reference"
    assert referenced <= documented, sorted(referenced - documented)


def test_env_example_has_no_values_for_secrets() -> None:
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if any(word in key for word in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            assert value.strip() == "", key
