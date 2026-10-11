"""Adversarial checks at actual log/export/exception boundaries (#59)."""

from __future__ import annotations

import ast
import json
import subprocess
import traceback
from pathlib import Path
from typing import Any

import psycopg
import pytest

from serene.adapters.git_memory import GitError, GitMemoryRepository
from serene.adapters.neatlogs_sink import NeatlogsSink
from serene.adapters.postgres import LedgerWriteRefused, PostgresEventStore
from serene.observability import RecordingSink, SafeTelemetry, redact
from serene.observability.telemetry import ALLOWED_KEYS
from serene.ports.event_store import ConcurrencyConflict
from serene.testing import SyntheticFamily

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = (
    "chd_" + "a" * 32,
    "act_" + "b" * 32,
    "Raw parent message about pickup",
    "Private caregiver report about sleep",
    "Private evidence containing family details",
    "Bearer " + "s" * 35,
    "sk-" + "x" * 40,
    "gh" + "p_" + "x" * 36,
)


@pytest.mark.parametrize("value", PRIVATE)
def test_sensitive_values_under_every_allowed_key_are_removed(value: str) -> None:
    for key in ALLOWED_KEYS:
        out = redact({key: value, "count": 4}, pseudonym_key=None)
        assert value not in repr(out)
        assert out["count"] == 4


def test_messages_identity_and_session_secrets_never_reach_application_telemetry() -> None:
    sink = RecordingSink()
    telemetry = SafeTelemetry(sink, pseudonym_key=b"test-audit-key")
    telemetry.emit(
        "ledger.append",
        {
            "child_id": PRIVATE[0],
            "person_id": PRIVATE[1],
            "parent_message": PRIVATE[2],
            "caregiver_text": PRIVATE[3],
            "evidence_content": PRIVATE[4],
            "authorization": PRIVATE[5],
            "session_secret": PRIVATE[6],
            "event_type": "OBSERVATION_REPORTED",
            "sequence": 2,
        },
    )
    assert all(value not in repr(sink.records) for value in PRIVATE)
    attrs = sink.records[0][1]
    assert attrs["event_type"] == "OBSERVATION_REPORTED" and attrs["sequence"] == 2
    assert str(attrs["child_ref"]).startswith("cref_")
    assert redact(attrs, pseudonym_key=None) == attrs


@pytest.mark.parametrize("value", PRIVATE)
def test_neatlogs_direct_call_and_root_metadata_cannot_bypass_redaction(value: str) -> None:
    bodies: list[bytes] = []

    def post(request: Any, timeout: float) -> int:
        bodies.append(request.data)
        return 200

    sink = NeatlogsSink(
        value, api_key="test-audit-key", session_id=value, end_user_id=value, opener=post
    )
    sink.emit(value, {"status": "OK"})
    sink.emit("runtime.call", {"status": "OK", "input_tokens": 12, "reason_codes": (value,)})
    sink.flush()
    assert bodies and all(value not in body.decode() for body in bodies)
    span = json.loads(bodies[0])["children"][0]
    assert span["tokens"]["prompt"] == 12 and span["status"] == "OK"


def test_neatlogs_exception_text_and_authorization_never_enter_reports() -> None:
    def fail(request: Any, timeout: float) -> int:
        raise RuntimeError(PRIVATE[2] + PRIVATE[6])

    sink = NeatlogsSink(api_key=PRIVATE[6], opener=fail)
    sink.emit("runtime.call", {"status": "FAILED"})
    report = sink.flush()
    assert report.errors == ("NETWORK_RuntimeError",)
    assert all(value not in repr(report) for value in PRIVATE)


@pytest.mark.parametrize(
    "error, expected",
    [
        (psycopg.errors.UniqueViolation, ConcurrencyConflict),
        (psycopg.errors.CheckViolation, LedgerWriteRefused),
        (psycopg.errors.ForeignKeyViolation, LedgerWriteRefused),
    ],
)
def test_database_failure_details_are_not_exportable_exception_messages(
    monkeypatch: pytest.MonkeyPatch,
    error: type[Exception],
    expected: type[Exception],
) -> None:
    store = PostgresEventStore("unused")

    def fail() -> Any:
        raise error("failing row contains " + PRIVATE[2])

    monkeypatch.setattr(store, "_connect", fail)
    family = SyntheticFamily(seed="privacy-errors")
    family.observe("synthetic observation", day=0)
    event = family.store.read_stream(family.child_id)[0]
    with pytest.raises(expected) as caught:
        store.append(event, expected_prev_hash=event.prev_event_hash)
    assert PRIVATE[2] not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__suppress_context__


def test_git_stderr_and_private_paths_are_not_exception_messages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess([], 1, b"", PRIVATE[2].encode()),
    )
    with pytest.raises(GitError, match="GIT_COMMAND_FAILED: exit=1"):
        GitMemoryRepository._run(tmp_path, "status")
    with pytest.raises(GitError, match=r"^NOT_A_MEMORY_REPOSITORY$"):
        GitMemoryRepository(tmp_path / "private-parent-name")


def test_application_has_no_raw_logging_or_console_exception_dump() -> None:
    # Kernel/adapters export only through SafeTelemetry. New logging needs review.
    for path in (ROOT / "serene").rglob("*.py"):
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(a.name not in {"logging", "loguru", "structlog"} for a in node.names), (
                    path
                )
            if isinstance(node, ast.ImportFrom):
                assert node.module not in {"logging", "loguru", "structlog"}, path
            if isinstance(node, ast.Call):
                assert ast.unparse(node.func) not in {"print", "traceback.print_exc"}, path
    for name, code in (
        ("global-error.tsx", "Serene client error"),
        ("error.tsx", "Serene view error"),
    ):
        source = (ROOT / "app/web/app" / name).read_text("utf-8")
        assert f'console.error("{code}")' in source
        assert "console.error(error)" not in source
