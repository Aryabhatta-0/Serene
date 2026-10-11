"""Secrets, PII and environment documentation hygiene (issue #59)."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

from scripts import env_audit, synthetic_audit

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
    assert env_audit.audit() == []


def test_env_example_has_no_values_for_secrets() -> None:
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if any(word in key for word in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            assert value.strip() == "", key


@pytest.mark.parametrize(
    "source",
    [
        'import os; os.environ["NEW_RUNTIME_SETTING"]',
        'import os as system; system.getenv("NEW_RUNTIME_SETTING")',
        'from os import getenv as read; read("NEW_RUNTIME_SETTING")',
        'from os import environ as settings; settings.get("NEW_RUNTIME_SETTING")',
        'import os; snapshot = dict(os.environ); snapshot.get("NEW_RUNTIME_SETTING")',
        'CREDENTIALS = frozenset({"NEW_RUNTIME_SETTING"})',
    ],
)
def test_env_inventory_detects_aliases_and_indirect_credentials(source: str) -> None:
    assert env_audit.python_references(source) == ({"NEW_RUNTIME_SETTING"}, [])


def test_unknown_dynamic_env_reads_require_explicit_review() -> None:
    assert env_audit.python_references("import os; os.getenv(variable)")[1]


def test_new_web_env_setting_fails_coverage(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("", encoding="utf-8")
    web = tmp_path / "app/web"
    web.mkdir(parents=True)
    (web / "config.mjs").write_text("process.env.NEW_WEB_SETTING", encoding="utf-8")
    assert env_audit.audit(tmp_path) == ["app/web/config.mjs: undocumented NEW_WEB_SETTING"]


def test_reviewed_synthetic_assets_are_unchanged() -> None:
    assert synthetic_audit.audit() == []


def test_synthetic_inventory_detects_added_and_changed_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = synthetic_audit.inventory()
    path = next(iter(current))
    current[path] = "0" * 64
    current["tests/fixtures/unreviewed.json"] = "1" * 64
    monkeypatch.setattr(synthetic_audit, "inventory", lambda root: current)
    assert synthetic_audit.audit() == [
        "tests/fixtures/unreviewed.json: synthetic provenance review required",
        f"{path}: reviewed synthetic bytes changed",
    ]


@pytest.mark.parametrize("suffix", [".json", ".md", ".lock", ".png"])
def test_scan_includes_all_file_types_and_reports_no_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
) -> None:
    monkeypatch.setattr(secret_scan, "ROOT", tmp_path)
    path = tmp_path / f"planted{suffix}"
    planted = "gh" + "p_" + "z" * 36
    path.write_bytes(b"\xff" + planted.encode())
    report = secret_scan.scan([path])
    assert report == [f"{path.name}:1: github_token"]
    assert planted not in repr(report)


def test_real_env_files_are_forbidden_even_without_recognizable_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(secret_scan, "ROOT", tmp_path)
    path = tmp_path / ".env.production"
    path.write_text("SOME_VALUE=unrecognized", encoding="utf-8")
    assert secret_scan.scan([path]) == [".env.production: forbidden_env_file"]


def test_scanner_detects_bearer_passwords_and_extended_provider_formats() -> None:
    planted = "\n".join(
        [
            "Authorization: " + "Bear" + "er " + "a" * 30,
            'password = "' + "nonplaceholder123" + '"',
            "github_" + "pat_" + "a" * 40,
            "AS" + "IA" + "B" * 16,
            "-----BEGIN " + "ENCRYPTED PRIVATE KEY-----",
        ]
    )
    names = {name for _, name in secret_scan.scan_text(planted)}
    assert names == {
        "bearer_token",
        "credential_literal",
        "github_fine_grained_token",
        "aws_temporary_key",
        "private_key",
    }


def test_history_scan_detects_a_deleted_credential_without_printing_it(tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)  # noqa: S603,S607

    git("init")
    git("config", "user.name", "Synthetic audit")
    git("config", "user.email", "audit@example.com")
    planted = "gh" + "p_" + "x" * 36
    path = tmp_path / "removed.json"
    path.write_text(planted, encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "synthetic planted credential")
    git("rm", "removed.json")
    git("commit", "-m", "remove synthetic fixture")
    report = secret_scan.scan_history(tmp_path)
    assert len(report) == 1 and "github_token" in report[0]
    assert planted not in repr(report)
