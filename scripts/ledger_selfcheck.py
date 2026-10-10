"""Replay / hash-chain self-check over a synthetic ledger. Exit code 1 on any failure.

    uv run python scripts/ledger_selfcheck.py

1. builds the canonical synthetic ladder (raw evidence -> contextual learning);
2. verifies the hash chain end to end;
3. rebuilds all projections twice from the ledger and compares digests;
4. mutates one historical payload and confirms tampering is detected.
"""

from __future__ import annotations

import sys

from serene.lineage.chain import verify_hash_chain
from serene.projections import projection_digest, rebuild_projections
from serene.testing import build_full_ladder


def main() -> int:
    family = build_full_ladder(seed="selfcheck")["family"]
    events = list(family.store.read_stream(family.child_id))
    chain = verify_hash_chain(events)
    first = projection_digest(rebuild_projections(events))
    second = projection_digest(rebuild_projections(family.store.read_stream(family.child_id)))

    tampered = list(events)
    payload = dict(tampered[0].payload)
    payload["evidence"] = {**payload["evidence"], "content": "rewritten history"}
    tampered[0] = tampered[0].model_copy(update={"payload": payload})
    detection = verify_hash_chain(tampered)

    checks = {
        "events": len(events),
        "chain_ok": chain.ok,
        "head": events[-1].event_hash,
        "replay_identical": first == second,
        "projection_digest": first,
        "tamper_detected": (not detection.ok, detection.failure_index, detection.reason),
    }
    for key, value in checks.items():
        print(f"{key}: {value}")
    ok = chain.ok and first == second and not detection.ok and detection.failure_index == 0
    print("SELF-CHECK", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
