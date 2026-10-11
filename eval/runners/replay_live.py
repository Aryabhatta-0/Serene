"""Rebuild a stored live Serene run's ledgers from its recorded model exchanges.

    git worktree add --detach ../morrow-at-run <manifest git.head>
    uv run python eval/runners/replay_live.py ../morrow-at-run \\
        eval/reports/local/live/<run> --out <dir>/replayed.json

No model and no network is used. The code that ran is imported from the worktree, which
must be checked out at the run's commit (`manifest.json` git.head). Every Hermes response is
served from `raw/serene__<scenario>.jsonl` in order; the run's own fault injection
re-injects its faults; the verifier's re-fetch reads the SHA-pinned page from git.

Fails closed unless every recorded exchange is consumed, every replayed request input is
byte-identical to the recorded one, and the replayed scores equal the stored scores. The
output holds, per scenario, the rebuilt ledger events and the trajectory as that commit
reduced it, so a later scorer version can rescore the run (`rescore_live.py`).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def git(worktree: Path, *args: str) -> str:
    return subprocess.run(  # noqa: S603 - fixed git read-only arguments
        ["git", "-C", str(worktree), *args],  # noqa: S607 - git from PATH
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("worktree", type=Path)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    worktree, run_dir, target = (p.resolve() for p in (args.worktree, args.run_dir, args.out))
    manifest = json.loads((run_dir / "manifest.json").read_text("utf-8"))
    head = git(worktree, "rev-parse", "HEAD")
    if head.strip() != manifest["git"]["head"] or manifest["git"]["dirty"]:
        raise SystemExit(f"worktree is at {head.strip()}, the run used {manifest['git']}")

    sys.path.insert(0, str(worktree))
    os.chdir(worktree)
    import eval.scenarios.runtime_live as live
    from eval.scorers.runtime_scorers import report_row
    from serene.adapters.browser.fetch import visible_text
    from serene.adapters.hermes.transport import (
        HermesResponse,
        HermesToolCall,
        HermesTransportError,
        HermesUsage,
    )
    from serene.evidence.verifier import FetchedPage

    if not Path(live.__file__).resolve().is_relative_to(worktree):
        raise SystemExit(f"imported {live.__file__}, not the worktree's code")
    pages = {
        url: visible_text(git(worktree, "show", f"{sha}:{path}"))
        for url in live.LIVE_SOURCES
        for sha, path in [url.split("/morrow/", 1)[1].split("/", 1)]
    }

    class PinnedFromGit:
        def __init__(self, sources: tuple[str, ...] = live.LIVE_SOURCES) -> None:
            self._sources = sources

        def fetch(self, url: str, allowed_domains: tuple[str, ...]) -> Any:
            plain = url.split("#", 1)[0]
            return FetchedPage(url=url, text=pages[plain]) if plain in self._sources else None

    class Replay:
        def __init__(self, records: list[dict[str, Any]]) -> None:
            injected = [r for r in records if r.get("error", {}).get("code", "").startswith("INJ")]
            self.queue = [r for r in records if r not in injected]
            self.used = 0
            self.mismatched: list[int] = []

        def respond(self, request: Any) -> Any:
            if self.used >= len(self.queue):
                raise SystemExit("the replay asked for more exchanges than were recorded")
            record = self.queue[self.used]
            self.used += 1
            if (record["purpose"], record["input"]) != (request.purpose, request.input):
                self.mismatched.append(record["seq"])
            if "error" in record:
                raise HermesTransportError(record["error"]["kind"], record["error"]["code"])
            r = record["response"]
            return HermesResponse(
                output_text=r["output_text"],
                tool_calls=tuple(
                    HermesToolCall(f"replay-{record['seq']}-{i}", c["name"], c["arguments"])
                    for i, c in enumerate(r["tool_calls"])
                ),
                usage=HermesUsage(**r["usage"]),
                model=r["model"],
                status=r["status"],
                latency_ms=r["latency_ms"],
            )

    live._PinnedFetcher = PinnedFromGit  # type: ignore[misc,assignment]
    stored = json.loads((run_dir / "scores.json").read_text("utf-8"))["rows"]
    out: dict[str, Any] = {"run": run_dir.name, "git": manifest["git"], "scenarios": {}}
    for row in stored:
        if row["system"] != "serene":
            continue
        sid = row["scenario"]
        raw = run_dir / "raw" / f"serene__{sid}.jsonl"
        replay = Replay([json.loads(line) for line in raw.read_text("utf-8").splitlines()])
        result = live.run_serene_live(sid, replay)
        replayed = report_row(result.trajectory, live.DEV[sid].oracle)["scores"]
        faithful = replay.used == len(replay.queue) and not replay.mismatched
        print(f"{sid}: {replay.used}/{len(replay.queue)} exchanges, mismatched "
              f"{replay.mismatched}, scores identical: {replayed == row['scores']}")  # fmt: skip
        if not faithful or replayed != row["scores"]:
            raise SystemExit(f"the replay of {sid} does not reproduce the stored run")
        out["scenarios"][sid] = {
            "run_id": row["run_id"],
            "trajectory": json.loads(result.trajectory.to_json()),
            "events": [e.model_dump(mode="json") for e in result.ledger_events],
        }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, indent=1, sort_keys=True), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
