"""Permit failures and the Windows private-stdin regression, without provider I/O."""
# ruff: noqa: S603, S607 -- fixed Git/Python commands against temporary test repositories

from __future__ import annotations

import contextvars
import copy
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from eval.runners import live_gate5_runtime as r
from eval.runners.live_gate5_protocol import Refused
from tests.test_live_gate5_runtime import permit_for


def test_guard_binds_request_local_client_to_the_agent_permit() -> None:
    from eval.runners.live_gate5_gateway import bind_sdk_client

    active: contextvars.ContextVar[Any] = contextvars.ContextVar("test_send", default=None)
    agent = SimpleNamespace(provider=r.PROVIDER, model=r.MODEL)
    clients = []
    checks = []
    for _ in range(2):  # Primary and real request-local clients are distinct objects.
        client = SimpleNamespace(max_retries=0, base_url=r.BASE_URL, _client=object())

        def send(*args: Any, **kwargs: Any) -> Any:
            binding = active.get()
            assert binding[0] is agent and binding[1] is clients[-1]
            return "guarded"

        client.chat = SimpleNamespace(completions=SimpleNamespace(create=send))
        clients.append(client)
        bind_sdk_client(agent, client, lambda: checks.append(True), active)
        # Pinned Hermes can reuse its request-local client; binding is idempotent.
        bind_sdk_client(agent, client, lambda: checks.append(True), active)
        assert client.chat.completions.create(model=r.MODEL, reasoning_effort="high") == "guarded"
        assert active.get() is None
        with pytest.raises(Refused, match="SDK_CLIENT_PERMIT_REUSE"):
            bind_sdk_client(object(), client, lambda: None, active)
    assert len(checks) == 2


def test_stateless_responses_body_cannot_import_session_or_previous_response() -> None:
    body, _ = permit_for()
    assert body["store"] is False
    for key in ("previous_response_id", "conversation", "session_id", "session_key"):
        with pytest.raises(Refused, match="REQUEST_RUNTIME_UNBOUND"):
            r.check_body({**body, key: "caller-selected"})


def test_http_failure_still_collects_the_permit_receipt(tmp_path: Path, monkeypatch: Any) -> None:
    import urllib.error

    from eval.runners import live_gate5_transport as t
    from tests.test_live_gate5_protocol import request

    collected = []

    def receipt(body: Any, permit: Any) -> dict[str, Any]:
        collected.append(permit)
        return {"permit": permit}

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise urllib.error.HTTPError(r.ENDPOINT, 500, "ignored", {}, None)

    provider = object.__new__(t.OwnedExperimentProvider)
    provider.runtime = SimpleNamespace(
        offline_probe=False, _api_key="placeholder", attest=lambda *a: {}, sdk_receipt=receipt
    )
    provider.observe = lambda: None
    provider._context = json.dumps(
        {"manifest_sha256": "a" * 64, "prefix_sha256": "b" * 64, "tape_id": "synthetic"}
    ).encode()
    provider._pair, provider._arm, provider._count = 1, "A", 1
    provider._out = tmp_path
    provider.sink = SimpleNamespace(flush=lambda: None)
    provider.telemetry = SimpleNamespace(emit=lambda *a: None)
    monkeypatch.setattr(t.urllib.request, "build_opener", lambda *a: SimpleNamespace(open=fail))
    with pytest.raises(ValueError, match="LIVE_ATTEMPT_INVALID"):
        provider.single_attempt(request("synthetic input"))
    saved = json.loads((tmp_path / "attempt-0001.sdk.json").read_text())
    assert saved["sends"][0]["permit"] == collected[0]
    assert len(collected) == 1


@pytest.mark.parametrize("operation", ["inventory", "clean"])
def test_git_stdin_timeout_and_capture(monkeypatch: Any, operation: str) -> None:
    def run(command: Any, **kwargs: Any) -> Any:
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.DEVNULL
        assert kwargs["stdout"] == (
            subprocess.PIPE if operation == "inventory" else subprocess.DEVNULL
        )
        assert kwargs["timeout"] == r.GIT_TIMEOUT_S
        assert command[3:] == (
            ["ls-files", "-z"] if operation == "inventory" else ["diff", "--quiet", "HEAD", "--"]
        )
        return subprocess.CompletedProcess(command, 0, b"tracked.py\0")

    monkeypatch.setattr(r.subprocess, "run", run)
    assert r.identity_git(Path("repo"), operation) == (
        b"tracked.py\0" if operation == "inventory" else b""
    )


@pytest.mark.parametrize("operation", ["inventory", "clean"])
@pytest.mark.parametrize("failure", ["timeout", "launch", "nonzero"])
def test_git_refusals_never_include_child_text(
    monkeypatch: Any, operation: str, failure: str
) -> None:
    def run(*args: Any, **kwargs: Any) -> Any:
        if failure == "timeout":
            raise subprocess.TimeoutExpired("private command", 10, output="secret")
        if failure == "launch":
            raise OSError("private launch error")
        return subprocess.CompletedProcess([], 7, b"private stdout", b"private stderr")

    monkeypatch.setattr(r.subprocess, "run", run)
    code = {"timeout": "TIMEOUT", "launch": "LAUNCH_FAILED", "nonzero": "NONZERO"}[failure]
    with pytest.raises(Refused, match=f"^IDENTITY_GIT_{operation.upper()}_{code}$"):
        r.identity_git(Path("repo"), operation)


@pytest.mark.parametrize("operation", ["inventory", "clean"])
def test_identity_git_completes_while_private_stdin_read_is_pending(
    tmp_path: Path, operation: str
) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--allow-empty",
            "-m",
            "fixture",
        ],
        check=True,
        capture_output=True,
    )
    code = """
import os,sys,threading,time
from pathlib import Path
from eval.runners.live_gate5_runtime import identity_git
threading.Thread(target=sys.stdin.readline,daemon=True).start()
time.sleep(0.2)
identity_git(Path(sys.argv[1]),sys.argv[2])
print('COMPLETE',flush=True)
os._exit(0)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(tmp_path), operation],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
    try:
        assert lines.get(timeout=20).strip() == "COMPLETE"
        assert process.wait(timeout=5) == 0
    finally:
        process.kill() if process.poll() is None else None
        process.wait(timeout=5)
        process.stdin.close()
        process.stdout.close()


@pytest.mark.skipif(
    os.name != "nt", reason="The inherited private-pipe deadlock is Windows-specific"
)
@pytest.mark.parametrize("command", [["ls-files", "-z"], ["diff", "--quiet", "HEAD", "--"]])
def test_old_inherited_stdin_shape_blocks_on_windows(tmp_path: Path, command: list[str]) -> None:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--allow-empty",
            "-m",
            "fixture",
        ],
        check=True,
        capture_output=True,
    )
    code = """
import os,subprocess,sys,threading,time
threading.Thread(target=sys.stdin.readline,daemon=True).start()
time.sleep(0.2)
p=subprocess.Popen(['git','-C',sys.argv[1],*sys.argv[2:]],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    p.wait(timeout=2)
    print('UNEXPECTED_COMPLETION',flush=True)
except subprocess.TimeoutExpired:
    subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    print('BLOCKED',flush=True)
os._exit(0)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(tmp_path), *command],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert process.stdout.readline().strip() == "BLOCKED"
        assert process.wait(timeout=5) == 0
    finally:
        process.kill() if process.poll() is None else None
        process.wait(timeout=5)
        process.stdin.close()
        process.stdout.close()


def sdk_fixture(tmp_path: Path) -> tuple[Any, Any, Any, Any, Any]:
    body, permit = permit_for()
    runtime = r.OwnedRuntime(tmp_path, tmp_path / "python", {"executable_sha256": "unused"})
    runtime.home = tmp_path
    runtime._permits[permit["permit_id"]] = r.encoded(permit)
    runtime._process_identity = {"pid": 12}
    receipt = {
        "permit": copy.deepcopy(permit),
        "pid": 12,
        "config_sha256": r.CONFIG_SHA256,
        "provider": r.PROVIDER,
        "model": r.MODEL,
        "reasoning": {"enabled": True, "effort": "high"},
        "max_turns": 500,
        "provider_base_url": r.BASE_URL,
        "generated_session_id": "generated-hermes-uuid",
        "sdk_payload_sha256": "c" * 64,
    }
    folder = tmp_path / "sdk-attestations"
    folder.mkdir()
    path = folder / (permit["permit_id"] + ".jsonl")
    return runtime, body, permit, receipt, path


def test_receipt_key_is_permit_and_generated_session_is_evidence(tmp_path: Path) -> None:
    runtime, body, permit, receipt, path = sdk_fixture(tmp_path)
    path.write_text(json.dumps(receipt) + "\n")
    assert receipt["generated_session_id"] != permit["permit_id"]
    assert runtime.sdk_receipt(body, permit) == receipt
    assert receipt["generated_session_id"] in runtime._agent_sessions
    with pytest.raises(Refused, match="SDK_RECEIPT_REUSE"):
        runtime.sdk_receipt(body, permit)


@pytest.mark.parametrize(
    "attack",
    [
        "missing",
        "wrong_key",
        "duplicate",
        "body",
        "permit",
        "provider",
        "model",
        "reasoning",
        "empty_session",
        "reused_session",
        "payload",
        "pid",
        "invalid_send",
    ],
)
def test_receipt_attacks_fail_closed(tmp_path: Path, attack: str) -> None:
    runtime, body, permit, receipt, path = sdk_fixture(tmp_path)
    if attack == "body":
        receipt["permit"]["body_sha256"] = "f" * 64
    elif attack == "permit":
        receipt["permit"]["attempt"] += 1
    elif attack in {"provider", "model", "reasoning", "pid"}:
        receipt[attack] = "wrong"
    elif attack == "empty_session":
        receipt["generated_session_id"] = ""
    elif attack == "reused_session":
        runtime._agent_sessions.add(receipt["generated_session_id"])
    elif attack == "payload":
        receipt.pop("sdk_payload_sha256")
    elif attack == "invalid_send":
        path.with_suffix(".invalid").touch()
    if attack not in {"missing", "wrong_key"}:
        path.write_text((json.dumps(receipt) + "\n") * (2 if attack == "duplicate" else 1))
    elif attack == "wrong_key":
        path.with_name("wrong.jsonl").write_text(json.dumps(receipt))
    with pytest.raises(Refused):
        runtime.sdk_receipt(body, permit)


def test_admission_requires_prepared_body_and_one_use_permit() -> None:
    body, permit = permit_for()
    gate = r.RequestGate()
    headers = {r.PERMIT_HEADER: permit["permit_id"]}
    with pytest.raises(Refused, match="UNATTESTED_HTTP_REQUEST"):
        gate.admit("POST", "/v1/responses", body, headers)

    gate.prepare(body, permit)
    for other in [{}, {r.PERMIT_HEADER: "wrong"}]:
        with pytest.raises(Refused, match="UNATTESTED_HTTP_REQUEST"):
            gate.admit("POST", "/v1/responses", body, other)
    assert gate.admit("POST", "/v1/responses", body, headers) == permit
    with pytest.raises(Refused, match="UNATTESTED_HTTP_REQUEST"):
        gate.admit("POST", "/v1/responses", body, headers)


def test_receipt_cannot_rebind_a_previously_attested_permit(tmp_path: Path) -> None:
    runtime, body, permit, receipt, path = sdk_fixture(tmp_path)
    permit["attempt"] += 1
    receipt["permit"] = dict(permit)
    path.write_text(json.dumps(receipt) + "\n")
    with pytest.raises(Refused, match="ATTESTED_PERMIT_MISMATCH"):
        runtime.sdk_receipt(body, permit)


@pytest.mark.parametrize("field", ["body_sha256", "pair", "arm", "attempt", "tape_id"])
def test_permit_binding_is_checked_before_dispatch(field: str) -> None:
    body, permit = permit_for()
    permit[field] = None
    with pytest.raises(Refused):
        r.RequestGate().prepare(body, permit)
