"""Owned Hermes runtime for live-gate/4. Importing this never starts a gateway.

No caller-supplied endpoint or attestation callback is accepted. The installed
official package runs in a new child with a private home and a closed environment.
The child reports on its own objects over inherited pipes, not invented HTTP APIs.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import queue
import secrets
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from eval.runners.live_gate4_protocol import check_envelope, digest, encoded, require

PROVIDER = "opencode-go"
MODEL = "deepseek-v4.1-flash"
BASE_URL = "https://opencode.ai/zen/go/v1"
MODEL_OPTIONS = {"reasoning": {"enabled": True, "effort": "high"}}
HOST = "127.0.0.1"
PORT = 18642
ENDPOINT = f"http://{HOST}:{PORT}/v1/responses"
CREDENTIALS = frozenset({"OPENCODE_GO_API_KEY"})
INTERNAL_BRIDGES = json.loads(
    (Path(__file__).parents[1] / "fixtures/hermes-v4-internal-bridges.json").read_text("utf-8")
)
OS_INPUTS = frozenset({"SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"})
FORBIDDEN_PREFIXES = (
    "HERMES_",
    "API_SERVER_",
    "OPENAI_",
    "ANTHROPIC_",
    "OPENCODE_",
    "MODEL",
    "REASONING",
    "GATEWAY_",
    "PYTHON",
    "UV_",
    "LITELLM_",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "SSL_CERT",
    "REQUESTS_CA",
)

# JSON is a YAML subset. Exact bytes are generated once and frozen, without secrets.
CONFIG = {
    "model": {"provider": PROVIDER, "default": MODEL, "base_url": BASE_URL},
    "agent": {
        "max_turns": 500,
        "reasoning_effort": "high",
        "api_max_retries": 1,
        "auto_recovery_cycles": 0,
        "environment_probe": False,
    },
    "providers": {PROVIDER: {"request_timeout_seconds": 120, "stale_timeout_seconds": 120}},
    "fallback_model": None,
    "platforms": {"api_server": {"enabled": True, "host": HOST, "port": PORT}},
    "gateway": {"multiplex_profiles": False},
}
CONFIG_BYTES = encoded(CONFIG) + b"\n"
CONFIG_SHA256 = hashlib.sha256(CONFIG_BYTES).hexdigest()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reject_overrides(environment: Mapping[str, str]) -> None:
    """Reject rather than silently ignoring stale/legacy execution overrides."""
    forbidden = sorted(
        name
        for name in environment
        if name.upper().startswith(FORBIDDEN_PREFIXES) and name.upper() not in CREDENTIALS
    )
    require(not forbidden, "FORBIDDEN_INHERITED_OVERRIDE")


def loopback(url: str) -> None:
    parsed = urlsplit(url)
    require(
        parsed.scheme == "http"
        and parsed.username is None
        and parsed.password is None
        and parsed.query == ""
        and parsed.fragment == ""
        and parsed.port == PORT
        and parsed.path == "/v1/responses",
        "API_BIND_CHANGED",
    )
    try:
        valid = ipaddress.ip_address(parsed.hostname or "").is_loopback
    except ValueError:
        valid = False
    require(valid and parsed.hostname == HOST, "API_NOT_LOOPBACK")


def launch_environment(
    inherited: Mapping[str, str],
    credentials: Mapping[str, str],
    home: Path,
    python: Path,
    api_key: str,
) -> dict[str, str]:
    reject_overrides(inherited)
    require(set(credentials) == CREDENTIALS and all(credentials.values()), "CREDENTIAL_ALLOWLIST")
    return {
        **{key: inherited[key] for key in OS_INPUTS if key in inherited},
        **dict(credentials),
        "API_SERVER_KEY": api_key,
        "HERMES_HOME": str(home),
        "HERMES_DISABLE_LAZY_INSTALLS": "1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        **{
            key: str(home)
            for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP")
        },
        "PATH": os.pathsep.join((str(python.parent), str(Path(shutil.which("git") or "").parent))),
    }


def package_identity(root: Path, python: Path, site_packages: Path | None = None) -> dict[str, Any]:
    """Pin installed source + data, executable, stamp and dependency RECORD identities.

    No user home, auth file, env file, or credential value is read into an archive.
    Git's tracked inventory avoids runtime caches and session content.
    """
    done = subprocess.run(  # noqa: S603
        ["git", "-C", str(root), "ls-files", "-z"],  # noqa: S607
        check=True,
        capture_output=True,
    )
    clean = subprocess.run(  # noqa: S603
        ["git", "-C", str(root), "diff", "--quiet", "HEAD", "--"],  # noqa: S607
        capture_output=True,
        check=False,
    )
    require(clean.returncode == 0, "HERMES_INSTALLATION_DIRTY")
    names = [
        n
        for n in done.stdout.decode().split("\0")
        if n
        and n.endswith((".py", ".yaml", ".toml", ".json"))
        and (
            "/" not in n
            or n.split("/")[0]
            in {
                "agent",
                "gateway",
                "hermes_cli",
                "tools",
                "providers",
                "acp_adapter",
                "pm",
                "plugins",
                "skills",
                "assets",
            }
        )
    ]
    require(names and not (root / ".env").exists(), "PACKAGE_PROJECT_ENV")
    inventory = {}
    for name in names:
        path = root / name
        require(not path.is_symlink(), "PACKAGE_SYMLINK")
        require(path.is_file(), "PACKAGE_INCOMPLETE")
        inventory[name] = sha(path)
    stamp = json.loads((root / "install-stamp.json").read_text("utf-8-sig"))
    site = site_packages or python.parent.parent / "Lib/site-packages"
    if not site.is_dir():
        candidates = list((python.parent.parent / "lib").glob("python*/site-packages"))
        require(len(candidates) == 1, "PACKAGE_SITE_UNKNOWN")
        site = candidates[0]
    records = {p.parent.name: sha(p) for p in sorted(site.glob("*.dist-info/RECORD"))}
    require(bool(records), "PACKAGE_DEPENDENCIES_UNKNOWN")
    return {
        "base_version": stamp["baseVersion"],
        "display_version": stamp["displayVersion"],
        "commit": stamp["commit"],
        "executable_sha256": sha(python),
        "source_inventory_sha256": digest(inventory),
        "source_file_count": len(inventory),
        "install_stamp_sha256": sha(root / "install-stamp.json"),
        "dependency_records_sha256": digest(records),
    }


def request_body(request: Mapping[str, Any]) -> dict[str, Any]:
    check_envelope(request)
    return {
        "provider": PROVIDER,
        "model": MODEL,
        "model_options": MODEL_OPTIONS,
        "instructions": request["instructions"],
        "input": request["input"],
        "store": False,
    }


def check_body(body: Mapping[str, Any]) -> None:
    require(
        set(body) == {"provider", "model", "model_options", "instructions", "input", "store"}
        and body["provider"] == PROVIDER
        and body["model"] == MODEL
        and body["model_options"] == MODEL_OPTIONS
        and body["store"] is False,
        "REQUEST_RUNTIME_UNBOUND",
    )


def check_sdk_payload(payload: Mapping[str, Any]) -> None:
    require(payload.get("model") == MODEL, "SDK_MODEL_DRIFT")
    reasoning = payload.get("reasoning", payload.get("extra_body", {}).get("reasoning", {}))
    effort = payload.get("reasoning_effort", reasoning.get("effort"))
    require(effort == "high" and reasoning.get("enabled") is not False, "SDK_REASONING_UNATTESTED")
    require("temperature" not in payload and "seed" not in payload, "SAMPLING_UNATTESTED")
    require(reasoning.get("effort", "high") == "high", "SDK_REASONING_UNATTESTED")
    require(
        not {"temperature", "seed"}.intersection(payload.get("extra_body", {})),
        "SAMPLING_UNATTESTED",
    )


def check_process(expected: Mapping[str, Any], observed: Mapping[str, Any]) -> None:
    require(observed == expected, "OWNED_PROCESS_IDENTITY_MISMATCH")


class RequestGate:
    """One exact request per permit; no session continuity or mutation routes."""

    def __init__(self) -> None:
        self.pending: dict[str, Any] = {}
        self.seen: set[str] = set()

    def prepare(self, body: Mapping[str, Any], session: str) -> dict[str, Any]:
        check_body(body)
        require(isinstance(session, str) and session.startswith("live-gate4-"), "SESSION_OVERRIDE")
        require(session not in self.seen and not self.pending, "SESSION_REUSE")
        self.seen.add(session)
        self.pending.update(session=session, request_sha256=digest(body))
        return dict(self.pending)

    def admit(self, method: str, path: str, body: Mapping[str, Any], headers: Any) -> None:
        require(method == "POST" and path == "/v1/responses", "API_ROUTE_DENIED")
        check_body(body)
        require(
            self.pending
            and self.pending["session"] == headers.get("X-Hermes-Session-Id")
            and self.pending["request_sha256"] == digest(body),
            "UNATTESTED_HTTP_REQUEST",
        )
        require("X-Hermes-Session-Key" not in headers, "SESSION_OVERRIDE")
        self.pending.clear()


class OwnedRuntime:
    """Single experiment lifetime, no daemon discovery, endpoint override, or resume.

    Construction and launch are separate so freeze/tests need neither keys nor I/O.
    Fresh per-request sessions preclude prior /model state even across arm boundaries.
    """

    def __init__(
        self,
        root: Path,
        python: Path,
        frozen_identity: Mapping[str, Any],
        *,
        site_packages: Path | None = None,
    ) -> None:
        self.root = root.resolve()
        self.python = python.resolve()
        self.site_packages = (site_packages or python.parent.parent / "Lib/site-packages").resolve()
        self._identity = encoded(frozen_identity)
        self.process: subprocess.Popen[str] | None = None
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self.home: Path | None = None
        self._api_key = ""
        self._environment: dict[str, str] = {}
        self._lines: queue.Queue[str] = queue.Queue()
        self._process_identity: dict[str, Any] = {}
        self._sessions: set[str] = set()
        self.offline_probe = False

    @property
    def identity(self) -> dict[str, Any]:
        return json.loads(self._identity)

    def start(
        self,
        inherited: Mapping[str, str],
        credentials: Mapping[str, str],
        *,
        offline_probe: bool = False,
    ) -> None:
        require(self.process is None and self._temporary is None, "RUNTIME_ALREADY_STARTED")
        reject_overrides(inherited)
        require(
            package_identity(self.root, self.python, self.site_packages) == self.identity,
            "HERMES_PACKAGE_DRIFT",
        )
        self._temporary = tempfile.TemporaryDirectory(
            prefix="live-gate4-", ignore_cleanup_errors=True
        )
        self.home = Path(self._temporary.name).resolve()
        require(not any(self.home.iterdir()), "HERMES_HOME_NOT_FRESH")
        (self.home / "config.yaml").write_bytes(CONFIG_BYTES)
        for name in ("state", "sessions", "work"):
            (self.home / name).mkdir()
        self._api_key = secrets.token_urlsafe(32)
        self._environment = launch_environment(
            inherited,
            credentials,
            self.home,
            self.python,
            self._api_key,
        )
        command = [
            str(self.python),
            "-I",
            "-S",
            str(Path(__file__).with_name("live_gate4_gateway.py")),
            str(self.root),
            str(self.home),
            str(self.site_packages),
        ]
        self.offline_probe = offline_probe
        if offline_probe:
            command.append("--offline-probe")
        self.process = subprocess.Popen(  # noqa: S603 - fixed local bootstrap, no shell
            command,
            cwd=self.home / "work",
            env=self._environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        assert self.process.stdout is not None

        def read() -> None:
            assert self.process is not None and self.process.stdout is not None
            for line in self.process.stdout:
                self._lines.put(line)

        threading.Thread(target=read, daemon=True).start()
        first = self._receive()
        self._process_identity = {
            "pid": self.process.pid,
            "nonce": first.get("nonce"),
            "executable_sha256": self.identity["executable_sha256"],
            "home": str(self.home),
        }
        require(bool(first.get("nonce")), "MISSING_PROCESS_NONCE")
        self._check(first)

    def _receive(self) -> dict[str, Any]:
        try:
            result = json.loads(self._lines.get(timeout=45))
        except (queue.Empty, ValueError):
            raise ValueError("OWNED_GATEWAY_ATTESTATION_UNAVAILABLE") from None
        require(result.get("state") == "READY", "OWNED_GATEWAY_REFUSED_" + json.dumps(result))
        return result

    def _check(self, receipt: Mapping[str, Any]) -> None:
        require(self.process is not None and self.process.poll() is None, "OWNED_GATEWAY_DEAD")
        check_process(self._process_identity, receipt["process"])
        require(receipt["package"] == self.identity, "HERMES_PACKAGE_DRIFT")
        require(receipt["config_sha256"] == CONFIG_SHA256, "HERMES_CONFIG_DRIFT")
        require(receipt["environment_names"] == sorted(self._environment), "ENVIRONMENT_DRIFT")
        require(receipt["environment_matches_launch"] is True, "ENVIRONMENT_DRIFT")
        require(receipt["internal_bridges"] == INTERNAL_BRIDGES, "ENVIRONMENT_DRIFT")
        loopback(receipt["endpoint"])

    def attest(self, body: Mapping[str, Any], session: str) -> dict[str, Any]:
        check_body(body)
        require(self.home is not None, "RUNTIME_NOT_STARTED")
        require(sha(self.home / "config.yaml") == CONFIG_SHA256, "HERMES_CONFIG_DRIFT")
        require(
            package_identity(self.root, self.python, self.site_packages) == self.identity,
            "HERMES_PACKAGE_DRIFT",
        )
        require(self.process is not None and self.process.poll() is None, "OWNED_GATEWAY_DEAD")
        require(session not in self._sessions, "SESSION_REUSE")
        self._sessions.add(session)
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps({"body": body, "session": session}) + "\n")
        self.process.stdin.flush()
        receipt = self._receive()
        self._check(receipt)
        require(receipt["request_sha256"] == digest(body), "REQUEST_RUNTIME_UNBOUND")
        require(receipt["session"] == session, "SESSION_OVERRIDE")
        return receipt

    def close(self) -> None:
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        if self._temporary is not None:
            self._temporary.cleanup()

    def __enter__(self) -> OwnedRuntime:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
