"""Offline owned startup only: placeholder credential; outbound connects denied.

This is NOT a live CLI. It never submits a Responses request or emits telemetry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from eval.runners.live_gate4_runtime import OS_INPUTS, OwnedRuntime, request_body


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation-root", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--site-packages", type=Path, required=True)
    args = parser.parse_args()
    frozen = Path(__file__).parents[1] / "fixtures/hermes-v4-installation.json"
    identity = json.loads(frozen.read_text("utf-8"))
    with OwnedRuntime(
        args.installation_root, args.python, identity, site_packages=args.site_packages
    ) as runtime:
        runtime.start(
            {k: v for k, v in os.environ.items() if k in OS_INPUTS},
            {"OPENCODE_GO_API_KEY": "offline-placeholder-no-provider-access"},
            offline_probe=True,
        )
        runtime.attest(
            request_body(
                {
                    "purpose": "propose",
                    "session_ref": "offline-probe",
                    "instructions": "offline",
                    "instructions_sha256": hashlib.sha256(b"offline").hexdigest(),
                    "input": "offline",
                }
            ),
            "live-gate4-offline-permit",
        )
        print("OFFLINE_OWNED_STARTUP_OK; provider calls=0; telemetry exports=0")


if __name__ == "__main__":
    main()
