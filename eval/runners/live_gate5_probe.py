"""Real HTTP route, denied outbound after SDK attestation; no evaluation or telemetry."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from eval.runners.live_gate5_compare import (
    DEFAULT_CATALOG,
    describe,
    load,
    read_tape,
    run_pair,
    write_new,
)
from eval.runners.live_gate5_protocol import digest, require, select_tapes
from eval.runners.live_gate5_runtime import (
    ENDPOINT,
    OS_INPUTS,
    PERMIT_HEADER,
    OwnedRuntime,
    new_permit,
    request_body,
)


def exact_pending(trees: dict[str, Path], tape_root: Path) -> tuple[dict[str, Any], str, str]:
    from eval.runners.live_gate5_experiment import PRODUCT_SHAS

    arms = {arm: describe(tree) for arm, tree in trees.items()}
    require(
        {arm: metadata["sha"] for arm, metadata in arms.items()} == PRODUCT_SHAS,
        "PRODUCT_SHA_MISMATCH",
    )
    tape = select_tapes(load(DEFAULT_CATALOG))[0]
    pair = run_pair(trees, tape, read_tape(tape_root, tape, arms), arms)
    require(pair["status"] == "first_policy_divergence", "EXACT_PENDING_UNAVAILABLE")
    return pair["states"]["A"]["request"], pair["prefix_sha256"], tape["tape_id"]


def post_probe(
    runtime: OwnedRuntime, request: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    require(runtime.offline_probe, "OFFLINE_PROBE_REQUIRED")
    body = request_body(request)
    permit = new_permit(body, request, context)
    attestation = runtime.attest(body, permit)
    result: dict[str, Any] = {
        "case": context["tape_id"],
        "request_sha256": digest(body),
        "runtime_attested": attestation["permit"] == permit,
    }
    http = urllib.request.Request(  # noqa: S310 - fixed loopback endpoint
        ENDPOINT,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {runtime._api_key}",
            "Content-Type": "application/json",
            PERMIT_HEADER: permit["permit_id"],
        },
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(http, timeout=120) as response:
            result["local_http_status"] = response.status
    except urllib.error.HTTPError as exc:
        result.update(
            local_http_status=exc.code,
            exception_type=type(exc).__name__,
            locations=[
                f"{Path(f.filename).name}:{f.lineno}"
                for f in traceback.extract_tb(exc.__traceback__)
            ],
        )
        exc.close()  # No response/error body is read or saved.
    try:
        receipt = runtime.sdk_receipt(body, permit)
    except Exception:
        require(runtime.home is not None, "RUNTIME_NOT_STARTED")
        diagnostic = runtime.home / "offline-diagnostics" / f"{permit['permit_id']}.json"
        if diagnostic.is_file():
            print(diagnostic.read_text("utf-8"), flush=True)  # Only safe file:line/type fields.
        raise
    require(runtime.home is not None, "RUNTIME_NOT_STARTED")
    denied = runtime.home / "sdk-attestations" / f"{permit['permit_id']}.offline-denied"
    require(denied.is_file(), "OFFLINE_DENIAL_NOT_REACHED")
    result.update(
        sdk_boundary_reached=True,
        sdk_receipt=receipt,
        provider_network_denied=True,
        live_provider_calls=0,
        telemetry_exports=0,
        process_alive=runtime.process is not None and runtime.process.poll() is None,
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation-root", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--site-packages", type=Path, required=True)
    parser.add_argument("--arm-a", type=Path, required=True)
    parser.add_argument("--arm-b", type=Path, required=True)
    parser.add_argument("--tape-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    exact, prefix, tape_id = exact_pending({"A": args.arm_a, "B": args.arm_b}, args.tape_root)
    identity = load(Path(__file__).parents[1] / "fixtures/hermes-v5-installation.json")
    minimal = {
        "purpose": "propose",
        "session_ref": "offline-diagnostic",
        "instructions": "Diagnostic only.",
        "instructions_sha256": hashlib.sha256(b"Diagnostic only.").hexdigest(),
        "input": "Reply OK.",
    }
    with OwnedRuntime(
        args.installation_root, args.python, identity, site_packages=args.site_packages
    ) as runtime:
        runtime.start(
            {k: v for k, v in os.environ.items() if k in OS_INPUTS},
            {"OPENCODE_GO_API_KEY": "offline-placeholder-no-provider-access"},
            offline_probe=True,
        )
        for attempt, (label, request) in enumerate(
            ((tape_id, exact), ("minimal-synthetic", minimal)), 1
        ):
            result = post_probe(
                runtime,
                request,
                {
                    "manifest_sha256": "0" * 64,
                    "prefix_sha256": prefix,
                    "tape_id": label,
                    "pair": 1,
                    "arm": "A",
                    "attempt": attempt,
                },
            )
            write_new(args.out / f"{label}.json", result)
            print(
                json.dumps(
                    {
                        "case": label,
                        "sdk_boundary_reached": True,
                        "provider_network_denied": True,
                        "live_provider_calls": 0,
                    }
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
