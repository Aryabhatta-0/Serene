"""Isolated, network-free runtime process for live-gate/3's lockstep coordinator.

Even live continuation gets replies through stdin; this worker has no provider.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# Imported by filename, before importing the selected worktree's eval namespace.
from shared_prefix_protocol import (
    POLICY_FILES,
    PROTECTED_FILES,
    PROTOCOL_VERSION,
    Refused,
    digest,
    envelope,
    request_key,
    require,
)


def git(tree: Path, *args: str) -> str:
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(tree), *args],  # noqa: S607
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout.strip()


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=True), flush=True)


class StopAtBoundary(BaseException):
    pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--scenario")
    args = parser.parse_args()
    tree = args.worktree.resolve()
    sys.path.insert(0, str(tree))
    os.chdir(tree)
    import eval.scenarios.runtime_live as live
    from eval.baselines.runtime_baselines import MatchedBudget
    from eval.runners.runtime_live_compare import _trust_scores
    from eval.scorers.runtime_scorers import SCORER_VERSION, report_row
    from serene.adapters.browser.fetch import visible_text
    from serene.adapters.browser.hermes_browser import BROWSER_PROMPT_VERSION
    from serene.adapters.hermes.runtime import PROMPT_VERSION
    from serene.adapters.hermes.transport import (
        HermesResponse,
        HermesToolCall,
        HermesTransportError,
        HermesUsage,
    )
    from serene.evidence.verifier import FetchedPage
    from serene.investigation.service import InvestigationBudget
    from serene.policies.scorers import SCORER_VERSION as TRUST_VERSION

    require(Path(live.__file__).resolve().is_relative_to(tree), "WRONG_WORKTREE_IMPORT")
    require(not git(tree, "status", "--porcelain"), "DIRTY_WORKTREE")
    metadata = {
        "kind": "ready",
        "sha": git(tree, "rev-parse", "HEAD"),
        "protocol_version": PROTOCOL_VERSION,
        "scorer_version": SCORER_VERSION,
        "trust_scorer_version": TRUST_VERSION,
        "oracles": {sid: s.oracle.digest() for sid, s in live.DEV.items()},
        "protected_sha256": {
            f: hashlib.sha256((tree / f).read_bytes()).hexdigest() for f in PROTECTED_FILES
        },
        "policy_sha256": {
            f: hashlib.sha256((tree / f).read_bytes()).hexdigest() for f in POLICY_FILES
        },
        "kernel_sha256": {
            f: hashlib.sha256((tree / f).read_bytes()).hexdigest()
            for f in git(tree, "ls-files", "serene").splitlines()
            if f not in POLICY_FILES
        },
        "runtime": {
            "runtime_prompt": PROMPT_VERSION,
            "browser_prompt": BROWSER_PROMPT_VERSION,
            "budget": dataclasses.asdict(MatchedBudget.from_serene()),
            "investigation_budget": {
                k: str(v) for k, v in dataclasses.asdict(InvestigationBudget()).items()
            },
            "max_ticks": live.MAX_TICKS,
            "silence": str(live.SILENCE),
            "sources": live.LIVE_SOURCES,
            "scenarios": {
                sid: {k: v for k, v in dataclasses.asdict(s).items() if k != "oracle"}
                for sid, s in live.DEV.items()
            },
        },
    }
    emit(metadata)
    if args.scenario is None:
        return
    require(args.scenario in live.DEV, "DEV_ONLY")
    # Verify SHA-pinned pages locally. No verifier or model network can occur here.
    pages = {}
    for url in live.LIVE_SOURCES:
        commit, path = url.split("/morrow/", 1)[1].split("/", 1)
        pages[url] = visible_text(git(tree, "show", f"{commit}:{path}"))

    class PinnedFromGit:
        def __init__(self, sources: tuple[str, ...] = live.LIVE_SOURCES) -> None:
            self.sources = sources

        def fetch(self, url: str, allowed_domains: tuple[str, ...]) -> Any:
            plain = url.split("#", 1)[0]
            return FetchedPage(url=url, text=pages[plain]) if plain in self.sources else None

    live._PinnedFetcher = PinnedFromGit
    rigs: list[Any] = []
    original_rig = live._rig

    def observed_rig(*a: Any, **kw: Any) -> Any:
        rig = original_rig(*a, **kw)
        rigs.append(rig)
        return rig

    live._rig = observed_rig

    def snapshot() -> dict[str, Any]:
        rig = rigs[-1]
        return {
            "events": [e.model_dump(mode="json") for e in rig.events()],
            "policy_selections": [
                attrs for name, attrs in rig.sink.records if name == "evidence.select"
            ],
        }

    class Bridge:
        def respond(self, request: Any) -> Any:
            req = envelope(request)
            emit({"kind": "boundary", "request": req, **snapshot()})
            line = sys.stdin.readline()
            require(bool(line), "COORDINATOR_DISCONNECTED")
            command = json.loads(line)
            if command.get("kind") == "stop":
                raise StopAtBoundary
            require(command.get("kind") == "reply", "BAD_COMMAND")
            reply = command["delivery"]
            require(
                reply.get("request_sha256") == digest(request_key(req)), "DELIVERY_INPUT_MISMATCH"
            )
            if "error" in reply:
                raise HermesTransportError(reply["error"]["kind"], reply["error"]["code"])
            r = reply["response"]
            return HermesResponse(
                output_text=r["output_text"],
                status=r["status"],
                model=r["model"],
                usage=HermesUsage(**r["usage"]),
                latency_ms=r["latency_ms"],
                tool_calls=tuple(
                    HermesToolCall(f"prefix-{i}", c["name"], c["arguments"])
                    for i, c in enumerate(r["tool_calls"])
                ),
            )

    try:
        result = live.run_serene_live(args.scenario, Bridge())
    except StopAtBoundary:
        emit({"kind": "stopped", **snapshot()})
        return
    emit(
        {
            "kind": "done",
            "request": None,
            **snapshot(),
            "trajectory": json.loads(result.trajectory.to_json()),
            "scores": report_row(result.trajectory, live.DEV[args.scenario].oracle)["scores"],
            "trust_scorers": _trust_scores(result, live.DEV[args.scenario].oracle),
            "wire": result.exchanges,
            "notes": result.notes,
        }
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never print credentials, provider error bodies, or arbitrary exception messages.
        emit(
            {"kind": "error", "code": str(exc) if isinstance(exc, Refused) else type(exc).__name__}
        )
        sys.exit(2)
