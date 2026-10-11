"""Freeze or replay live-gate/3 DEV tapes. CLI is strictly offline.

The continuation API accepts a caller-supplied provider only after a sealed
divergence. There is deliberately no provider discovery or live CLI default.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import queue
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from eval.runners.shared_prefix_protocol import (
    DEV_IDS,
    PROTOCOL_VERSION,
    SCORER_VERSION,
    TRUST_VERSION,
    ContinuationJournal,
    Refused,
    SharedPrefix,
    digest,
    encoded,
    require,
    sealed_tape,
    select_tapes,
    validate_versions,
)

DEFAULT_CATALOG = Path(__file__).parents[1] / "fixtures/shared-prefix-dev-v3.json"
WORKER = Path(__file__).with_name("shared_prefix_worker.py")


def implementation_hashes() -> dict[str, str]:
    return {
        name: file_sha(WORKER.with_name(name))
        for name in (
            "shared_prefix_protocol.py",
            "shared_prefix_worker.py",
            "shared_prefix_compare.py",
            "shared_prefix_metrics.py",
        )
    }


def load(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: Any) -> None:
    """Never overwrite historical manifests, results or prefix checkpoints."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


class Worker:
    def __init__(self, tree: Path, scenario: str | None = None) -> None:
        command = [sys.executable, str(WORKER), "--worktree", str(tree.resolve())]
        if scenario is not None:
            require(scenario in DEV_IDS, "DEV_ONLY")
            command += ["--scenario", scenario]
        self.process = subprocess.Popen(  # noqa: S603 - fixed local worker, no shell
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.lines: queue.Queue[str] = queue.Queue()

        def reader() -> None:
            assert self.process.stdout is not None
            for line in self.process.stdout:
                self.lines.put(line)
            self.lines.put("")

        threading.Thread(target=reader, daemon=True).start()

    def receive(self) -> dict[str, Any]:
        try:
            line = self.lines.get(timeout=45)
        except queue.Empty as exc:
            raise Refused("WORKER_TIMEOUT") from exc
        require(bool(line), "WORKER_EXITED")
        message = json.loads(line)
        require(message.get("kind") != "error", "WORKER_" + message.get("code", "ERROR"))
        return message

    def send(self, command: Mapping[str, Any]) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(command) + "\n")
        self.process.stdin.flush()

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=5)
        for stream in (self.process.stdin, self.process.stdout):
            if stream is not None:
                stream.close()


def describe(tree: Path) -> dict[str, Any]:
    worker = Worker(tree)
    try:
        return worker.receive()
    finally:
        worker.close()


def validate_arms(arms: Mapping[str, Any]) -> None:
    a, b = arms["A"], arms["B"]
    for metadata in (a, b):
        require(set(metadata["oracles"]) == set(DEV_IDS), "DEV_SET_MISMATCH")
        for oracle in metadata["oracles"].values():
            validate_versions({**metadata, "oracle_sha256": oracle}, oracle)
    for field in ("oracles", "runtime", "protected_sha256", "kernel_sha256"):
        require(a[field] == b[field], "ARM_MISMATCH_" + field.upper())
    require(a["policy_sha256"] != b["policy_sha256"], "IDENTICAL_POLICIES")


def read_tape(root: Path, tape: Mapping[str, Any], arms: Mapping[str, Any]) -> tuple[Any, ...]:
    """Validate the WHOLE source tape before replaying any reply or scoring."""
    folder = (root / "runs" / tape["tape_id"]).resolve()
    require(folder.is_relative_to(root.resolve()), "TAPE_PATH_ESCAPE")
    for name, expected in tape["files"].items():
        path = (folder / name).resolve()
        require(path.is_relative_to(folder) and path.is_file(), "INCOMPLETE_TAPE")
        require(file_sha(path) == expected, "TAPE_FILE_HASH_MISMATCH")
    manifest = load(folder / "native/manifest.json")
    rowset = load(folder / "native/scores.json")["rows"]
    require(len(rowset) == 1, "TAPE_ROWS")
    row = rowset[0]
    oracle = arms["A"]["oracles"][tape["scenario"]]
    for metadata in (tape, {**row, "trust_scorer_version": row["trust_scorers"]["scorer_version"]}):
        validate_versions({"protocol_version": PROTOCOL_VERSION, **metadata}, oracle)
    require(manifest["versions"]["scorer"] == SCORER_VERSION, "SCORER_MISMATCH")
    require(manifest["versions"]["trust_scorer"] == TRUST_VERSION, "TRUST_SCORER_MISMATCH")
    require(manifest["split"] == row["split"] == "dev", "DEV_ONLY")
    require(row["scenario"] == tape["scenario"] and row["system"] == "serene", "TAPE_IDENTITY")
    require(manifest["git"] == {"head": tape["source_sha"], "dirty": False}, "TAPE_SHA")
    require(bool(manifest["finished_at"]), "INCOMPLETE_TAPE")
    runtime = arms["A"]["runtime"]
    require(manifest["matched_budget"] == runtime["budget"], "BUDGET_MISMATCH")
    for key in ("runtime_prompt", "browser_prompt"):
        require(manifest["versions"][key] == runtime[key], "PROMPT_VERSION_MISMATCH")
    require(manifest["evidence_sources"] == runtime["sources"], "PINNED_PAGE_MISMATCH")
    raw = folder / "native/raw" / f"serene__{tape['scenario']}.jsonl"
    records = [json.loads(line) for line in raw.read_text("utf-8").splitlines()]
    require(row["live"]["exchanges"] == tape["exchange_count"], "INCOMPLETE_TAPE")
    return sealed_tape(records, tape["exchange_count"])


def freeze(a: Path, b: Path, root: Path, catalog: Path = DEFAULT_CATALOG) -> dict[str, Any]:
    catalog_data = load(catalog)
    selected = select_tapes(catalog_data)  # frozen identities BEFORE opening score files
    arms = {"A": describe(a), "B": describe(b)}
    validate_arms(arms)
    require(
        arms["A"]["protected_sha256"] == catalog_data["source_protected_sha256"],
        "SOURCE_RUNTIME_DRIFT",
    )
    for tape in selected:
        read_tape(root, tape, arms)  # any invalid tape refuses the whole experiment
    body = {
        "protocol_version": PROTOCOL_VERSION,
        "scorer_version": SCORER_VERSION,
        "trust_scorer_version": TRUST_VERSION,
        "catalog_sha256": file_sha(catalog),
        "implementation_sha256": implementation_hashes(),
        "historical_verdict": "FAIL",
        "mode": "shared-prefix-only",
        "arms": arms,
        "tapes": list(selected),
    }
    return {**body, "manifest_sha256": digest(body)}


def check_manifest(manifest: Mapping[str, Any]) -> None:
    body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    require(digest(body) == manifest["manifest_sha256"], "MANIFEST_HASH_MISMATCH")
    require(manifest["implementation_sha256"] == implementation_hashes(), "PROTOCOL_CODE_DRIFT")
    require(manifest["catalog_sha256"] == file_sha(DEFAULT_CATALOG), "CATALOG_DRIFT")
    require(manifest["historical_verdict"] == "FAIL", "HISTORICAL_VERDICT_CHANGED")
    require(manifest["mode"] == "shared-prefix-only", "UNSUPPORTED_MODE")
    validate_arms(manifest["arms"])
    validate_versions({**manifest, "oracle_sha256": "checked-per-tape"}, "checked-per-tape")
    select_tapes(
        {
            "protocol_version": PROTOCOL_VERSION,
            "experiment": "pr67-ab-20261011",
            "tapes": manifest["tapes"],
        }
    )


class FrozenContinuation:
    """One provider/config for both arms. No outcome or arm label reaches it.

    Instantiate before replay; persist metadata in the future experiment manifest.
    Configuration contains public identities/digests only, never credentials.
    Caller supplies its existing Hermes/NeatLogs adapter, not another policy.
    """

    def __init__(
        self,
        configuration: Mapping[str, Any],
        current_configuration: Callable[[], Mapping[str, Any]],
        provider: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        fields = {
            "provider",
            "model",
            "config_sha256",
            "timeout_s",
            "retry_configuration",
            "budget",
            "neatlogs_path",
        }
        require(
            set(configuration) == fields and all(v is not None for v in configuration.values()),
            "INCOMPLETE_LIVE_CONFIGURATION",
        )
        self._configuration = encoded(configuration)
        self._current = current_configuration
        self._provider = provider
        self.check()

    @property
    def metadata(self) -> dict[str, Any]:
        return json.loads(self._configuration)

    def check(self) -> None:
        require(encoded(self._current()) == self._configuration, "LIVE_CONFIGURATION_DRIFT")

    def respond(self, request: dict[str, Any]) -> dict[str, Any]:
        self.check()
        return self._provider(request)

    def begin_arm(self, arm: str) -> None:
        require(arm in {"A", "B"}, "UNKNOWN_ARM")


class ContinuationProvider(Protocol):
    def begin_arm(self, arm: str) -> None: ...

    def respond(self, request: dict[str, Any]) -> dict[str, Any]: ...


def continue_pair(
    workers: Mapping[str, Any],
    pending: Mapping[str, Any],
    prefix: SharedPrefix,
    provider: ContinuationProvider,
) -> tuple[dict[str, Any], ContinuationJournal]:
    """Optional API: complete A's LIVE suffix, then B's; never replay downstream.

    Caller persists provider.metadata before replay; config is rechecked per call.
    The same provider is called for each arm's own exact pending input.
    It returns a reply with request_sha256, just like Exchange.deliver.
    """
    journal = ContinuationJournal(prefix)
    divergence = prefix.divergence
    assert divergence is not None
    for arm in ("A", "B"):
        require(
            encoded(pending[arm].get("request")) == encoded(divergence["requests"][arm]),
            "CONTINUATION_BOUNDARY_CHANGED",
        )
    states = dict(pending)
    for arm in ("A", "B"):
        provider.begin_arm(arm)
        while states[arm].get("request") is not None:
            request = states[arm].get("request")
            if request is None:
                continue
            # Copy inputs so a provider cannot mutate a boundary or prefix record.
            reply = provider.respond(json.loads(encoded(request)))
            journal.append(arm, request, reply)  # input binding checked before dispatch
            workers[arm].send({"kind": "reply", "delivery": reply})
            prior_events = states[arm]["events"]
            states[arm] = workers[arm].receive()
            require(states[arm]["kind"] in {"boundary", "done"}, "BAD_WORKER_MESSAGE")
            require(
                encoded(states[arm]["events"][: len(prior_events)]) == encoded(prior_events),
                "PREFIX_HISTORY_CHANGED",
            )
    return states, journal


def run_pair(
    trees: Mapping[str, Path],
    tape: Mapping[str, Any],
    exchanges: tuple[Any, ...],
    arms: Mapping[str, Any],
) -> dict[str, Any]:
    workers: dict[str, Worker] = {}
    prefix = SharedPrefix(exchanges)
    result: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "scorer_version": SCORER_VERSION,
        "trust_scorer_version": TRUST_VERSION,
        "oracle_sha256": tape["oracle_sha256"],
        "SHAs": {k: arms[k]["sha"] for k in ("A", "B")},
        "tape": dict(tape),
        "live_calls": 0,
        "evaluation_verdict": "NOT_EVALUATED",
        "eligible_for_holdout": False,
    }
    try:
        for arm in ("A", "B"):
            workers[arm] = Worker(trees[arm], tape["scenario"])
            require(workers[arm].receive() == arms[arm], "WORKTREE_DRIFT")
        while True:
            states = {arm: w.receive() for arm, w in workers.items()}
            require(
                all(s["kind"] in {"boundary", "done"} for s in states.values()),
                "BAD_WORKER_MESSAGE",
            )
            action = prefix.step(states["A"], states["B"])
            if action["kind"] != "shared_reply":
                result.update(status=action["kind"], boundary=action, states=states)
                break
            for worker in workers.values():
                worker.send({"kind": "reply", "delivery": action["delivery"]})
    except (Refused, OSError, ValueError) as exc:
        result.update(
            status="INVALID", refusal=str(exc) if isinstance(exc, Refused) else type(exc).__name__
        )
        if "states" in locals():
            result["states"] = states
    finally:
        for worker in workers.values():
            worker.close()
    result["prefix"] = [dataclasses.asdict(e) for e in prefix.history]
    result["prefix_sha256"] = prefix.history_sha256
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "replay"))
    parser.add_argument("--arm-a", type=Path, required=True)
    parser.add_argument("--arm-b", type=Path, required=True)
    parser.add_argument("--tape-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.command == "freeze":
        write_new(args.manifest, freeze(args.arm_a, args.arm_b, args.tape_root))
        return
    manifest = load(args.manifest)
    check_manifest(manifest)
    require(args.out is not None and not args.out.exists(), "NEW_OUTPUT_DIRECTORY_REQUIRED")
    # Validate all tapes AND both worktrees before computing any new results.
    for arm, tree in (("A", args.arm_a), ("B", args.arm_b)):
        require(describe(tree) == manifest["arms"][arm], "WORKTREE_DRIFT")
    tapes = [(t, read_tape(args.tape_root, t, manifest["arms"])) for t in manifest["tapes"]]
    for tape, exchanges in tapes:
        result = run_pair({"A": args.arm_a, "B": args.arm_b}, tape, exchanges, manifest["arms"])
        result["manifest_sha256"] = manifest["manifest_sha256"]
        write_new(args.out / (tape["tape_id"] + ".json"), result)
        require(result["status"] != "INVALID", "INVALID_PAIR_STOP_EXPERIMENT")


if __name__ == "__main__":
    main()
