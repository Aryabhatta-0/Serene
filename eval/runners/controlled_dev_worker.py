"""controlled-dev/1 runtime worker: one arm, one DEV scenario, one clean pinned worktree.

Shared prefix: replies arrive over stdin, bound to the exact recorded model input.
After the coordinator seals a valid divergence it sends ``go_live`` once; from then on
this arm calls Serene's NORMAL Hermes integration (``transport_from_env``, the HTTP
client in the arm's own worktree) for its exact pending input and every later one.
No custom Hermes process, SDK patch, permit, attestation or retry interception: the
runtime's own retry policy runs unchanged, and each attempt is only observed.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Imported by filename, before importing the selected worktree's eval namespace.
from shared_prefix_protocol import (
    POLICY_FILES,
    PROTECTED_FILES,
    Refused,
    digest,
    envelope,
    request_key,
    require,
)

PROTOCOL_VERSION = "controlled-dev/1"


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
    parser.add_argument("--neatlogs-session")
    args = parser.parse_args()
    tree = args.worktree.resolve()
    sys.path.insert(0, str(tree))
    os.chdir(tree)
    import eval.scenarios.runtime_live as live
    from eval.baselines.runtime_baselines import MatchedBudget
    from eval.runners.runtime_live_compare import _neatlogs, _trust_scores
    from eval.scorers.runtime_scorers import SCORER_VERSION, report_row
    from serene.adapters.browser.fetch import visible_text
    from serene.adapters.browser.hermes_browser import BROWSER_PROMPT_VERSION
    from serene.adapters.hermes.runtime import PROMPT_VERSION
    from serene.adapters.hermes.transport import (
        HermesResponse,
        HermesToolCall,
        HermesTransportError,
        HermesUsage,
        transport_from_env,
    )
    from serene.evidence.verifier import FetchedPage
    from serene.investigation.service import InvestigationBudget
    from serene.policies.scorers import SCORER_VERSION as TRUST_VERSION

    require(Path(live.__file__).resolve().is_relative_to(tree), "WRONG_WORKTREE_IMPORT")
    require(not git(tree, "status", "--porcelain"), "DIRTY_WORKTREE")
    emit(
        {
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
    )
    if args.scenario is None:
        return
    require(args.scenario in live.DEV, "DEV_ONLY")
    # SHA-pinned pages, verified from local git objects (unchanged from the tapes).
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
        """Recorded replies until ``go_live``; then the arm's normal Hermes transport."""

        def __init__(self) -> None:
            self.live: Any = None
            self.attempts: list[dict[str, Any]] = []

        def respond(self, request: Any) -> Any:
            if self.live is not None:
                return self._live(request)
            req = envelope(request)
            emit({"kind": "boundary", "request": req, **snapshot()})
            line = sys.stdin.readline()
            require(bool(line), "COORDINATOR_DISCONNECTED")
            command = json.loads(line)
            if command.get("kind") == "stop":
                raise StopAtBoundary
            if command.get("kind") == "go_live":
                transport = transport_from_env()
                require(transport is not None, "HERMES_NOT_CONFIGURED")
                self.live = transport
                return self._live(request)
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

        def _live(self, request: Any) -> Any:
            record: dict[str, Any] = {
                "attempt": len(self.attempts) + 1,
                "purpose": request.purpose,
                "request_sha256": digest(request_key(envelope(request))),
            }
            self.attempts.append(record)
            started = time.monotonic()
            try:
                response = self.live.respond(request)
            except HermesTransportError as exc:
                # A failed call reports no usage: it stays unknown, never zero.
                record.update(
                    outcome="error",
                    error={"kind": exc.kind, "code": exc.code},
                    usage={"input_tokens": None, "output_tokens": None},
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                )
                raise
            except Exception as exc:
                record.update(
                    outcome="error",
                    error={"kind": "UNEXPECTED", "code": type(exc).__name__},
                    usage={"input_tokens": None, "output_tokens": None},
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                )
                raise
            record.update(
                outcome="ok",
                model=response.model,
                status=response.status,
                usage={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
            return response

    bridge = Bridge()
    try:
        result = live.run_serene_live(args.scenario, bridge)
    except StopAtBoundary:
        emit({"kind": "stopped", **snapshot()})
        return
    went_live = bridge.live is not None
    neatlogs: dict[str, Any] = {"sent": False, "reason": "no live suffix"}
    if went_live:
        try:
            neatlogs = _neatlogs(args.neatlogs_session or "controlled-dev-1", result)
        except Exception as exc:  # telemetry export never changes the product result
            neatlogs = {"sent": False, "reason": type(exc).__name__}
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
            "went_live": went_live,
            "live_attempts": bridge.attempts,
            "neatlogs": neatlogs,
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
