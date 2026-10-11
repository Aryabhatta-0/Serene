"""Eval-only single-attempt transport; never discovers a user Hermes daemon."""

from __future__ import annotations

import dataclasses
import json
import time
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from eval.runners.live_gate5_experiment import (
    ExperimentProvider,
    check_experiment,
    describe,
    expected_configuration,
    verify_implementation_commit,
    write_new,
)
from eval.runners.live_gate5_protocol import digest, request_key, require
from eval.runners.live_gate5_runtime import (
    ENDPOINT,
    MODEL,
    PERMIT_HEADER,
    PROVIDER,
    OwnedRuntime,
    loopback,
    new_permit,
    request_body,
)
from serene.adapters.hermes.transport import MAX_RESPONSE_BYTES, parse_responses_payload
from serene.adapters.neatlogs_sink import NeatlogsSink, _NoRedirect
from serene.observability.telemetry import SafeTelemetry


class OwnedExperimentProvider(ExperimentProvider):
    """The only provider accepted by v5.execute; no injectable attestation callback.

    Start the supplied OwnedRuntime explicitly inside its context manager only
    after separate live authorization. Neither constructor performs network I/O.
    """

    def __init__(
        self,
        manifest: Mapping[str, Any],
        trees: Mapping[str, Path],
        runtime: OwnedRuntime,
        out: Path,
        *,
        neatlogs_key: str,
        pseudonym_key: bytes,
    ) -> None:
        require(type(runtime) is OwnedRuntime, "EXPERIMENT_OWNED_RUNTIME_REQUIRED")
        require(bool(neatlogs_key) and bool(pseudonym_key), "TELEMETRY_CREDENTIAL_REQUIRED")
        require(
            runtime.identity == manifest["live_configuration"]["hermes"]["installation"],
            "HERMES_PACKAGE_DRIFT",
        )
        self.runtime = runtime
        self.trees = dict(trees)
        self.sink = NeatlogsSink(
            "serene-live-eval",
            api_key=neatlogs_key,
            endpoint="https://ingest.neatlogs.com/v1/trace",
            timeout_s=10,
            max_body_bytes=7000,
            max_pending_spans=5000,
        )
        self.telemetry = SafeTelemetry(self.sink, pseudonym_key=pseudonym_key)
        super().__init__(manifest, self.observe, self.single_attempt, out)

    def observe(self) -> dict[str, Any]:
        manifest = self.metadata
        check_experiment(manifest)
        verify_implementation_commit(manifest)
        require(
            {arm: describe(tree) for arm, tree in self.trees.items()} == manifest["arms"],
            "WORKTREE_DRIFT",
        )
        require(
            self.sink.endpoint == "https://ingest.neatlogs.com/v1/trace"
            and self.sink.workflow_name == "serene-live-eval"
            and self.sink._timeout == 10
            and self.sink._max_body == 7000
            and self.sink._max_pending == 5000,
            "NEATLOGS_CONFIGURATION_DRIFT",
        )
        return expected_configuration(manifest)

    def single_attempt(self, request: dict[str, Any]) -> dict[str, Any]:
        require(not self.runtime.offline_probe, "OFFLINE_PROBE_CANNOT_EXECUTE_EXPERIMENT")
        self.observe()  # real worktrees/code/oracles/scorers immediately before I/O too
        body = request_body(request)
        context = json.loads(self._context or b"{}")
        permit = new_permit(
            body,
            request,
            {
                "manifest_sha256": context["manifest_sha256"],
                "prefix_sha256": context["prefix_sha256"],
                "tape_id": context["tape_id"],
                "pair": self._pair,
                "arm": self._arm,
                "attempt": self._count,
            },
        )
        receipt = self.runtime.attest(body, permit)
        write_new(self._out / f"attempt-{self._count:04d}.runtime.json", receipt)
        loopback(ENDPOINT)
        # Stateless Responses requests use the one-use permit for correlation.
        # Hermes generates its own fresh agent session; no session headers are sent.
        http = urllib.request.Request(  # noqa: S310
            ENDPOINT,
            data=json.dumps(body).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.runtime._api_key}",
                "Content-Type": "application/json",
                PERMIT_HEADER: permit["permit_id"],
            },
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
        start = time.monotonic()
        self.sink.session_id = f"pr67-v5-{self._pair:02d}-{self._arm}"
        try:
            try:
                with opener.open(http, timeout=120) as response:
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
            finally:
                # HTTP/protocol errors do not erase evidence of an SDK send.
                audit = self.runtime.sdk_receipt(body, permit)
                write_new(self._out / f"attempt-{self._count:04d}.sdk.json", {"sends": [audit]})
            require(len(raw) <= MAX_RESPONSE_BYTES, "RESPONSE_TOO_LARGE")
            payload = json.loads(raw)
            require(self.runtime.home is not None, "OWNED_GATEWAY_DEAD")
            resolved = payload.get("runtime", {})
            require(
                resolved.get("provider") == PROVIDER
                and resolved.get("model") == MODEL
                and resolved.get("route_source") == "raw_request",
                "RESPONSE_RUNTIME_UNATTESTED",
            )
            result = parse_responses_payload(
                payload, latency_ms=int((time.monotonic() - start) * 1000)
            )
            require(
                type(result.usage.input_tokens) is int and type(result.usage.output_tokens) is int,
                "MISSING_ACTUAL_USAGE",
            )
            delivery = {
                "request_sha256": digest(request_key(request)),
                "response": dataclasses.asdict(result),
            }
            self.telemetry.emit(
                "runtime.call",
                {
                    "status": "COMPLETE",
                    "input_tokens": result.usage.input_tokens,
                    "output_tokens": result.usage.output_tokens,
                },
            )
        except Exception:
            self.telemetry.emit("runtime.call", {"status": "FAILED"})
            self.sink.flush()
            # Unknown billed usage cannot be declared zero or become a favorable retry.
            raise ValueError("LIVE_ATTEMPT_INVALID_USAGE_OR_RUNTIME_UNATTESTED") from None
        exported = self.sink.flush()
        require(exported.ok and not self.telemetry.dropped, "NEATLOGS_INFRASTRUCTURE_FAILURE")
        delivery["neatlogs"] = {"export": "ok", "session_id": exported.session_id}
        return delivery
