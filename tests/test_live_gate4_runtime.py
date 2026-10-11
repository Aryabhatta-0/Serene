"""Deterministic runtime attacks. No daemon, provider or telemetry network access."""

from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pytest

from eval.runners import live_gate4_experiment as v4
from eval.runners import live_gate4_runtime as runtime_module
from eval.runners import shared_prefix_experiment as v3
from eval.runners.live_gate4_protocol import Refused
from eval.runners.live_gate4_runtime import (
    CONFIG_BYTES,
    CONFIG_SHA256,
    CREDENTIALS,
    ENDPOINT,
    INTERNAL_BRIDGES,
    MODEL,
    MODEL_OPTIONS,
    PROVIDER,
    OwnedRuntime,
    RequestGate,
    check_body,
    check_process,
    check_sdk_payload,
    launch_environment,
    loopback,
    reject_overrides,
    request_body,
)
from tests.test_live_gate4_protocol import request


@pytest.mark.parametrize(
    "name",
    [
        "HERMES_HOME",
        "HERMES_MAX_ITERATIONS",
        "HERMES_MODEL",
        "HERMES_REASONING_EFFORT",
        "OPENAI_BASE_URL",
        "OPENCODE_GO_BASE_URL",
        "API_SERVER_HOST",
        "MODEL",
        "PYTHONPATH",
        "HTTP_PROXY",
        "GATEWAY_MULTIPLEX_PROFILES",
        "hermes_max_iterations",
    ],
)
def test_forbidden_inherited_overrides(name: str) -> None:
    with pytest.raises(Refused, match="FORBIDDEN_INHERITED_OVERRIDE"):
        reject_overrides({name: "stale"})


def test_closed_launch_environment_credentials_only(tmp_path: Path) -> None:
    environment = launch_environment(
        {"SYSTEMROOT": "system", "PATH": "untrusted", "UNRELATED_SECRET": "not-copied"},
        {"OPENCODE_GO_API_KEY": "provider-secret"},
        tmp_path,
        tmp_path / "python",
        "api-secret",
    )
    assert environment["HERMES_HOME"] == str(tmp_path)
    assert environment["HOME"] == environment["USERPROFILE"] == str(tmp_path)
    assert environment["OPENCODE_GO_API_KEY"] == "provider-secret"
    assert "not-copied" not in environment.values()
    assert "untrusted" not in environment["PATH"]
    assert "HERMES_MAX_ITERATIONS" not in environment
    assert {"OPENCODE_GO_API_KEY"} == CREDENTIALS
    with pytest.raises(Refused, match="CREDENTIAL_ALLOWLIST"):
        launch_environment({}, {"OPENAI_API_KEY": "wrong"}, tmp_path, tmp_path / "python", "key")


def test_generated_config_hash_is_exact_and_secret_free() -> None:
    assert hashlib.sha256(CONFIG_BYTES).hexdigest() == CONFIG_SHA256
    assert (v4.ROOT / "eval/fixtures/hermes-v4-config.json").read_bytes() == CONFIG_BYTES
    config = json.loads(CONFIG_BYTES)
    assert config["agent"]["max_turns"] == 500
    assert config["agent"]["reasoning_effort"] == "high"
    assert "api_key" not in CONFIG_BYTES.decode()
    assert "temperature" not in CONFIG_BYTES.decode() and "seed" not in CONFIG_BYTES.decode()


@pytest.mark.parametrize(
    "url",
    [
        "http://0.0.0.0:18642/v1/responses",
        "http://localhost:18642/v1/responses",
        "http://127.0.0.1.evil:18642/v1/responses",
        "http://127.0.0.1:8642/v1/responses",
        "http://secret@127.0.0.1:18642/v1/responses",
        "http://[::]:18642/v1/responses",
        "http://127.0.0.1:18642/v1/responses?model=other",
    ],
)
def test_loopback_and_exact_owned_endpoint_only(url: str) -> None:
    loopback(ENDPOINT)
    with pytest.raises(Refused):
        loopback(url)


@pytest.mark.parametrize(
    "key,value",
    [
        ("provider", "other"),
        ("model", "hermes-agent"),
        ("model_options", {}),
        ("model_options", {"reasoning": {"effort": "low"}}),
        ("temperature", 0),
        ("seed", 1),
        ("previous_response_id", "old-session"),
        ("store", True),
    ],
)
def test_every_request_explicitly_binds_runtime(key: str, value: Any) -> None:
    body = request_body(request("unchanged bytes"))
    assert body["provider"] == PROVIDER and body["model"] == MODEL
    assert body["model_options"] == MODEL_OPTIONS
    check_body(body)
    body[key] = value
    with pytest.raises(Refused, match="REQUEST_RUNTIME_UNBOUND"):
        check_body(body)


def test_sessions_one_use_and_no_override_routes() -> None:
    gate = RequestGate()
    body = request_body(request("input"))
    headers = {"X-Hermes-Session-Id": "live-gate4-fresh"}
    gate.prepare(body, headers["X-Hermes-Session-Id"])
    with pytest.raises(Refused, match="SESSION_OVERRIDE"):
        gate.admit("POST", "/v1/responses", body, {**headers, "X-Hermes-Session-Key": "old"})
    for path in ("/api/config", "/api/sessions/old/model", "/p/default/v1/responses"):
        with pytest.raises(Refused, match="API_ROUTE_DENIED"):
            gate.admit("POST", path, body, headers)
    gate.admit("POST", "/v1/responses", body, headers)
    with pytest.raises(Refused, match="UNATTESTED_HTTP_REQUEST"):
        gate.admit("POST", "/v1/responses", body, headers)
    with pytest.raises(Refused, match="SESSION_REUSE"):
        gate.prepare(body, headers["X-Hermes-Session-Id"])
    gate.prepare(body, "live-gate4-next-attempt")


def test_request_permit_is_bound_to_exact_input() -> None:
    gate = RequestGate()
    body = request_body(request("one"))
    gate.prepare(body, "live-gate4-fresh")
    with pytest.raises(Refused, match="UNATTESTED_HTTP_REQUEST"):
        gate.admit(
            "POST",
            "/v1/responses",
            {**body, "input": "two"},
            {"X-Hermes-Session-Id": "live-gate4-fresh"},
        )


@pytest.mark.parametrize("key", ["pid", "nonce", "executable_sha256", "home"])
def test_process_identity_mismatch(key: str) -> None:
    identity = {"pid": 42, "nonce": "owned", "executable_sha256": "hash", "home": "fresh"}
    check_process(identity, identity)
    with pytest.raises(Refused, match="OWNED_PROCESS_IDENTITY_MISMATCH"):
        check_process(identity, {**identity, key: "different"})


@pytest.fixture
def owned(monkeypatch: Any, tmp_path: Path) -> Any:
    identity = {"executable_sha256": "frozen", "base_version": "0.21.6"}
    runtime = OwnedRuntime(tmp_path, tmp_path / "python", identity)
    monkeypatch.setattr(runtime_module, "package_identity", lambda *args: identity.copy())

    class Process:
        pid = 123
        stdout = io.StringIO("")
        stdin = io.StringIO()
        alive = True

        def poll(self) -> Any:
            return None if self.alive else 1

        def terminate(self) -> None:
            self.alive = False

        def wait(self, **kwargs: Any) -> int:
            return 0

    observed_launches = []

    def launch(command: Any, **kwargs: Any) -> Process:
        assert kwargs["cwd"] == runtime.home / "work"
        assert not list((runtime.home / "state").iterdir())
        assert not list((runtime.home / "sessions").iterdir())
        assert command[1:3] == ["-I", "-S"] and "gateway.py" in command[3]
        observed_launches.append(kwargs)
        return Process()

    monkeypatch.setattr(runtime_module.subprocess, "Popen", launch)

    def receipt() -> dict[str, Any]:
        return {
            "nonce": "owned",
            "process": {
                "pid": 123,
                "nonce": "owned",
                "home": str(runtime.home),
                "executable_sha256": "frozen",
            },
            "package": identity.copy(),
            "config_sha256": CONFIG_SHA256,
            "endpoint": ENDPOINT,
            "environment_names": sorted(runtime._environment),
            "environment_matches_launch": True,
            "internal_bridges": INTERNAL_BRIDGES,
        }

    monkeypatch.setattr(runtime, "_receive", receipt)
    runtime.start({}, {"OPENCODE_GO_API_KEY": "secret-only-at-launch"})
    yield runtime, receipt, observed_launches
    runtime.close()


def test_fresh_home_and_state_not_normal_daemon(owned: Any) -> None:
    runtime, receipt, launches = owned
    assert runtime.home.name.startswith("live-gate4-")
    assert launches[0]["env"]["HERMES_HOME"] == str(runtime.home)
    assert "secret-only-at-launch" not in json.dumps(receipt())
    assert (runtime.home / "config.yaml").read_bytes() == CONFIG_BYTES
    home = runtime.home
    runtime.close()
    assert not home.exists()


def test_frozen_package_identity_cannot_be_mutated_through_public_snapshot(owned: Any) -> None:
    runtime, _, _ = owned
    snapshot = runtime.identity
    snapshot["base_version"] = "drift"
    assert runtime.identity["base_version"] == "0.21.6"


def test_config_mutation_after_launch_blocks_next_attempt(owned: Any) -> None:
    runtime, _, _ = owned
    (runtime.home / "config.yaml").write_bytes(b"mutated")
    with pytest.raises(Refused, match="HERMES_CONFIG_DRIFT"):
        runtime.attest(request_body(request("x")), "live-gate4-next")
    assert runtime.process.stdin.getvalue() == ""


@pytest.mark.parametrize("kind", ["dead", "pid", "env", "version", "bind"])
def test_pre_attempt_process_drift(owned: Any, kind: str) -> None:
    runtime, receipt, _ = owned
    observed = receipt()
    if kind == "dead":
        runtime.process.alive = False
    elif kind == "pid":
        observed["process"]["pid"] = 999
    elif kind == "env":
        observed["environment_matches_launch"] = False
    elif kind == "version":
        observed["package"]["base_version"] = "other"
    else:
        observed["endpoint"] = "http://0.0.0.0:18642/v1/responses"
    with pytest.raises(Refused):
        runtime._check(observed)


def test_v3_archives_and_decision_semantics_unchanged() -> None:
    # Compare functions themselves, not a duplicated set of expected answers.
    import ast

    old = ast.parse(Path(v3.__file__).read_text("utf-8"))
    new = ast.parse(Path(v4.__file__).read_text("utf-8"))
    for name in ("decide", "validate_row", "number", "count", "run_frozen_pair"):
        a = next(n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == name)
        b = next(n for n in new.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assert ast.dump(a) == ast.dump(b)
    assert v3.RULE == v4.RULE and v3.SAMPLING == v4.SAMPLING
    v3.check_experiment(v3.load(v3.MANIFEST))
    a, b = (
        json.loads((v4.ROOT / f"eval/fixtures/shared-prefix-dev-v{v}.json").read_text())
        for v in (3, 4)
    )
    b["protocol_version"] = "live-gate/3"
    assert a == b  # complete identical tapes/provenance, not just the same tape count
    if v4.MANIFEST.exists():
        manifest = v4.load(v4.MANIFEST)
        assert manifest["v3_attempt_verdict"] == "INVALID"
        for name, expected in manifest["v3_files_sha256"].items():
            assert v4.file_sha(v4.ROOT / name) == expected


def test_no_live_daemon_can_be_injected(tmp_path: Path) -> None:
    with pytest.raises(Refused, match="EXPERIMENT_OWNED_RUNTIME_REQUIRED"):
        v4.execute({}, {}, tmp_path, object(), tmp_path)


@pytest.mark.parametrize(
    "payload",
    [
        {"model": MODEL, "reasoning_effort": "low"},
        {"model": "other", "reasoning_effort": "high"},
        {"model": MODEL},
        {"model": MODEL, "reasoning_effort": "high", "temperature": 0},
        {"model": MODEL, "reasoning_effort": "high", "extra_body": {"seed": 1}},
        {"model": MODEL, "reasoning_effort": "high", "reasoning": {"effort": "low"}},
    ],
)
def test_sdk_boundary_rejects_unbound_or_invented_controls(payload: Any) -> None:
    with pytest.raises(Refused):
        check_sdk_payload(payload)


def test_sdk_supports_the_installed_hermes_reasoning_encodings() -> None:
    for payload in (
        {"model": MODEL, "reasoning_effort": "high"},
        {"model": MODEL, "extra_body": {"reasoning": {"enabled": True, "effort": "high"}}},
        {"model": MODEL, "reasoning": {"enabled": True, "effort": "high"}},
    ):
        check_sdk_payload(payload)


def test_v4_protocol_replay_logic_equal_v3() -> None:
    old = (v4.ROOT / "eval/runners/shared_prefix_protocol.py").read_text("utf-8")
    new = (v4.ROOT / "eval/runners/live_gate4_protocol.py").read_text("utf-8")
    assert old.replace("live-gate/3", "live-gate/4") == new
    # Never normalize or reinterpret tape request/reply content in the v4 catalog.
    assert copy.deepcopy(MODEL_OPTIONS) == {"reasoning": {"enabled": True, "effort": "high"}}
