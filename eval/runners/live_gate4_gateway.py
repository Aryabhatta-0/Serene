"""Private live-gate/4 bootstrap around the installed official Hermes API adapter.

Only inherited stdin/stdout carry attestation. No extra HTTP endpoint is required.
Hermes files are neither patched nor copied. All diagnostics are discarded because
provider exceptions/config dumps may contain credentials. Receipts are allowlisted.
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import os
import secrets
import sys
from pathlib import Path
from typing import Any


def main() -> None:
    # -I suppresses implicit cwd/PYTHONPATH/user-site imports. Add only pinned roots.
    root, home = (Path(p).resolve() for p in sys.argv[1:3])
    site_packages = Path(sys.argv[3]).resolve()
    # Load the frozen installed dependency tree without the Windows venv redirector.
    # Do not execute editable .pth hooks or permit user-site customization.
    sys.path.insert(0, str(site_packages))
    sys.prefix = sys.exec_prefix = str(site_packages.parent.parent)
    if "--offline-probe" in sys.argv[4:]:
        import ipaddress
        import socket

        connect = socket.socket.connect

        def local_connect(sock: Any, address: Any) -> Any:
            if not isinstance(address, tuple) or not ipaddress.ip_address(address[0]).is_loopback:
                raise RuntimeError("OFFLINE_PROBE_NETWORK_DENIED")
            return connect(sock, address)

        socket.socket.connect = local_connect
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import json

    from eval.runners.live_gate4_runtime import (
        BASE_URL,
        CONFIG_SHA256,
        ENDPOINT,
        HOST,
        INTERNAL_BRIDGES,
        MODEL,
        PORT,
        PROVIDER,
        RequestGate,
        check_body,
        check_sdk_payload,
        package_identity,
        require,
        sha,
    )

    pipe = sys.stdout
    null = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    sys.stdout = sys.stderr = null
    initial_environment = dict(os.environ)
    identity = package_identity(root, Path(sys.executable), site_packages)
    nonce = secrets.token_hex(32)
    process = {
        "pid": os.getpid(),
        "nonce": nonce,
        "home": str(home),
        "executable_sha256": sha(Path(sys.executable)),
    }
    sys.path.insert(0, str(root))
    # Importing these official modules does not invoke a model.
    from gateway.config import PlatformConfig
    from gateway.platforms.api_server import APIServerAdapter, _request_agent_overrides
    from gateway.platforms.api_server_request_options import _request_reasoning_config
    from gateway.run import _current_max_iterations
    from hermes_cli.version_info import get_version_info
    from hermes_constants import get_hermes_home

    agent_sessions: set[str] = set()

    def environment_ok() -> None:
        current = dict(os.environ)
        session_environment = current.pop("HERMES_SESSION_ID", None)
        require(
            session_environment is None or session_environment in agent_sessions,
            "SESSION_ENVIRONMENT_OVERRIDE",
        )
        # This is Hermes' config bridge, never an allowed inherited override.
        for name, value in INTERNAL_BRIDGES.items():
            require(current.pop(name, None) == value, "INTERNAL_BRIDGE_DRIFT")
        changed = sorted(
            k
            for k in set(current) | set(initial_environment)
            if current.get(k) != initial_environment.get(k)
        )
        require(not changed, "ENVIRONMENT_DRIFT_" + ",".join(changed))

    def verify() -> None:
        require(Path(get_hermes_home()).resolve() == home, "HERMES_HOME_CHANGED")
        require(sha(home / "config.yaml") == CONFIG_SHA256, "HERMES_CONFIG_DRIFT")
        require(
            package_identity(root, Path(sys.executable), site_packages) == identity,
            "HERMES_PACKAGE_DRIFT",
        )
        environment_ok()
        require(_current_max_iterations() == 500, "MAX_TURNS_UNATTESTED")
        require(not (home / ".env").exists(), "HERMES_ENV_FILE_APPEARED")
        version = get_version_info()
        require(
            version.base_version == identity["base_version"]
            and version.commit == identity["commit"],
            "HERMES_VERSION_DRIFT",
        )

    gate = RequestGate()
    original = APIServerAdapter._create_agent
    active_send: contextvars.ContextVar[Any] = contextvars.ContextVar(
        "owned_sdk_send", default=None
    )
    import httpx

    http_send = httpx.Client.send

    def checked_http(client: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
        agent = active_send.get()
        require(agent is not None and client is agent.client._client, "UNATTESTED_PROVIDER_IO")
        verify()
        require(str(request.url) == BASE_URL + "/chat/completions", "PROVIDER_URL_DRIFT")
        require(agent.client.max_retries == 0, "SDK_RETRY_DRIFT")
        check_sdk_payload(json.loads(request.content))
        # Public, credential-free attestation persisted before the actual network boundary.
        audit = home / "sdk-attestations"
        audit.mkdir(exist_ok=True)
        with (audit / f"{agent.session_id}.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "config_sha256": CONFIG_SHA256,
                        "provider": agent.provider,
                        "model": agent.model,
                        "reasoning_effort": "high",
                        "max_turns": agent.max_iterations,
                        "provider_base_url": agent.base_url,
                        "sdk_payload_sha256": sha_bytes(request.content),
                    }
                )
                + "\n"
            )
        return http_send(client, request, *args, **kwargs)

    def sha_bytes(value: bytes) -> str:
        import hashlib

        return hashlib.sha256(value).hexdigest()

    httpx.Client.send = checked_http

    @functools.wraps(original)
    def create_agent(adapter: Any, *args: Any, **kwargs: Any) -> Any:
        verify()
        require(kwargs.get("requested_provider") == PROVIDER, "PROVIDER_UNBOUND")
        require(kwargs.get("requested_model") == MODEL, "MODEL_UNBOUND")
        require(
            _request_reasoning_config(kwargs.get("model_options"))
            == {"enabled": True, "effort": "high"},
            "REASONING_UNBOUND",
        )
        require(not kwargs.get("route") and not kwargs.get("session_model"), "SESSION_OVERRIDE")
        require(not adapter._model_routes and adapter.gateway_runner is None, "DAEMON_OVERRIDE")
        agent = original(adapter, *args, **kwargs)
        require(agent.session_id == kwargs.get("session_id"), "SESSION_OVERRIDE")
        agent_sessions.add(agent.session_id)
        require(
            agent.provider == PROVIDER
            and agent.model == MODEL
            and agent.base_url == BASE_URL
            and agent.max_iterations == 500,
            "RESOLVED_AGENT_DRIFT",
        )
        require(
            agent._session_init_model_config["reasoning_config"]
            == {"enabled": True, "effort": "high"},
            "RESOLVED_REASONING_DRIFT",
        )
        require(agent._api_max_retries == 1 and agent._auto_recovery_cycles == 0, "RETRY_DRIFT")
        require(
            not agent._fallback_chain and agent.api_mode == "chat_completions", "FALLBACK_DRIFT"
        )
        require(agent._resolved_api_call_timeout() == 120, "PROVIDER_TIMEOUT_DRIFT")
        require(not agent.request_overrides, "REQUEST_OVERRIDES")
        # Guard the actual SDK boundary too: retries/tool turns cannot bypass the freeze.
        client = agent.client
        require(client.max_retries == 0, "SDK_RETRIES_UNATTESTED")
        require(str(client.base_url).rstrip("/") == BASE_URL, "SDK_BASE_URL_DRIFT")
        resource = client.chat.completions
        send = resource.create

        def guarded_send(*call_args: Any, **payload: Any) -> Any:
            verify()
            require(agent.provider == PROVIDER and agent.model == MODEL, "MID_TURN_ROUTE_DRIFT")
            check_sdk_payload(payload)
            require(client.max_retries == 0, "SDK_RETRY_DRIFT")
            token = active_send.set(agent)
            try:
                return send(*call_args, **payload)
            finally:
                active_send.reset(token)

        resource.create = guarded_send
        return agent

    APIServerAdapter._create_agent = create_agent

    async def run() -> None:
        from aiohttp import web

        adapter = APIServerAdapter(
            PlatformConfig(
                enabled=True,
                extra={
                    "host": HOST,
                    "port": PORT,
                    "key": initial_environment["API_SERVER_KEY"],
                    "model_routes": {},
                    "direct_model_requests": True,
                },
            )
        )

        # Restrict the entire surface: no /model, profile, config, tools or session writes.
        @web.middleware
        async def admission(request: Any, handler: Any) -> Any:
            body = await request.json()
            gate.admit(request.method, request.path, body, request.headers)
            verify()
            return await handler(request)

        make_middleware = adapter._make_profile_prefix_middleware
        adapter._make_profile_prefix_middleware = lambda: admission
        require(await adapter.connect(), "OWNED_GATEWAY_BIND_FAILED")
        del make_middleware
        if "--offline-probe" in sys.argv[4:]:
            # Exercise the real installed resolver/constructor; never run a conversation.
            probe_agent = create_agent(
                adapter,
                session_id="live-gate4-offline-probe",
                requested_provider=PROVIDER,
                requested_model=MODEL,
                model_options={"reasoning": {"enabled": True, "effort": "high"}},
            )
            probe_payload = probe_agent._build_api_kwargs(
                [
                    {"role": "user", "content": "offline construction only"},
                ]
            )
            check_sdk_payload(probe_payload)

            def scripted_provider(request: Any) -> Any:
                return httpx.Response(
                    200,
                    json={
                        "id": "offline",
                        "object": "chat.completion",
                        "created": 0,
                        "model": MODEL,
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": "offline"},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    },
                )

            # The actual installed OpenAI serialization and HTTPX guard run against an
            # in-memory scripted transport. No socket or provider credential is used.
            probe_agent.client._client.close()
            probe_agent.client._client = httpx.Client(
                transport=httpx.MockTransport(scripted_provider)
            )
            probe_agent.client.chat.completions.create(**probe_payload)

        def receipt(**extra: Any) -> None:
            verify()
            sockets = adapter._site._server.sockets
            require(
                sockets and all(s.getsockname()[:2] == (HOST, PORT) for s in sockets),
                "API_BIND_DRIFT",
            )
            pipe.write(
                json.dumps(
                    {
                        "state": "READY",
                        "process": process,
                        "nonce": nonce,
                        "package": identity,
                        "config_sha256": sha(home / "config.yaml"),
                        "endpoint": ENDPOINT,
                        "environment_names": sorted(initial_environment),
                        "environment_matches_launch": True,
                        "internal_bridges": INTERNAL_BRIDGES,
                        **extra,
                    }
                )
                + "\n"
            )
            pipe.flush()

        receipt()
        while line := await asyncio.to_thread(sys.stdin.readline):
            message = json.loads(line)
            body, session = message["body"], message["session"]
            check_body(body)
            selected = _request_agent_overrides(
                body,
                virtual_model="hermes-agent",
                allow_bare_model=True,
            )
            require(selected["requested_provider"] == PROVIDER, "API_PROVIDER_UNSUPPORTED")
            require(selected["requested_model"] == MODEL, "API_MODEL_UNSUPPORTED")
            require(
                _request_reasoning_config(selected["model_options"])
                == {"enabled": True, "effort": "high"},
                "API_REASONING_UNSUPPORTED",
            )
            receipt(**gate.prepare(body, session))
        await adapter.disconnect()

    asyncio.run(run())


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        # Never emit exception messages, config contents, or credential-bearing reprs.
        import json
        import re
        import traceback

        reason = str(exc) if type(exc).__name__ == "Refused" else "BOOTSTRAP_FAILURE"
        if not re.fullmatch(r"[A-Z0-9_,]+", reason):
            reason = "BOOTSTRAP_FAILURE"
        sys.__stdout__.write(
            json.dumps(
                {
                    "state": "INVALID",
                    "exception_type": type(exc).__name__,
                    "reason": reason,
                    "locations": [
                        f"{Path(frame.filename).name}:{frame.lineno}"
                        for frame in traceback.extract_tb(exc.__traceback__)
                    ],
                }
            )
            + "\n"
        )
        sys.__stdout__.flush()
        raise SystemExit(1) from None
