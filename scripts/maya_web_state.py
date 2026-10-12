"""Read-only local web adapter for the canonical generated Maya report.

No runtime drive, model calls, database, or memory writes. The existing view
builders derive UI fields from report events; the report remains the only input.
"""

from __future__ import annotations

import json
from os import fstat
from pathlib import Path
from typing import Any

from serene.causal import build_causal_twin
from serene.causal.provenance import build_twin_provenance
from serene.demo.report import verify_report
from serene.domain.canonical import canonical_json, sha256_hex
from serene.domain.events import DomainEvent
from serene.experiments.view import build_experiments_view
from serene.memory.view import build_memory_dream_view
from serene.ports.memory import MemoryDocument
from serene.projections.investigations import investigations
from serene.projections.state import KernelState, apply_event

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / ".demo" / "maya" / "report.json"


class ReportMemory:
    """The report's memory snapshot, with no write capability."""

    def __init__(self, report: dict[str, Any]) -> None:
        self.contents: dict[str, str] = report["memory"]
        self.revision: str = report["memory_head"]

    def read(self, path: str) -> MemoryDocument | None:
        content = self.contents.get(path)
        if content is None:
            return None
        return MemoryDocument(
            path=path,
            revision=self.revision,
            content=content,
            content_digest=sha256_hex(content.encode()),
        )

    def list_paths(self, prefix: str) -> list[str]:
        return [p for p in self.contents if p.startswith(prefix)]

    def head(self) -> str:
        return self.revision


def build_web_state(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("synthetic") is not True or report.get("mode") != "offline-scripted-io":
        raise ValueError("Only the canonical synthetic report is supported")
    beats = verify_report(report)
    events = [DomainEvent.model_validate_json(json.dumps(e)) for e in report["events"]]
    state = KernelState()
    snapshots = []
    provenance_before = None
    for event in events:
        apply_event(state, event)
        # The report's "before" twin was taken once the competing hypotheses were
        # proposed; its provenance is that of the first ledger position whose
        # twin is exactly the recorded one (issue #75).
        if provenance_before is None and state.hypothesis_levels:
            twin_now = build_causal_twin(state, event.occurred_at)
            if twin_now.model_dump(mode="json") == report["twin_before"]:
                provenance_before = build_twin_provenance(state, event.occurred_at, twin_now)
        if event.event_type.value == "INVESTIGATION_PHASE_CHANGED":
            snapshots.append({"sequence": event.sequence, "investigations": investigations(state)})
    final = investigations(state)
    snapshots.append({"sequence": events[-1].sequence, "investigations": final})
    twin_after = build_causal_twin(state, events[-1].occurred_at)
    twin = twin_after.model_dump(mode="json")
    if twin != report["twin_after"]:
        raise ValueError("Report twin disagrees with its events")
    if provenance_before is None:
        raise ValueError("Report twin_before matches no ledger position")
    provenance_after = build_twin_provenance(state, events[-1].occurred_at, twin_after)
    memory = build_memory_dream_view(state, ReportMemory(report)).model_dump(mode="json")
    if memory["unreadable"]:
        raise ValueError("Report memory is unreadable")
    return {
        "report_sha256": sha256_hex(canonical_json(report)),
        "ledger_head": state.last_event_hash,
        "event_count": len(events),
        "beats": beats,
        "snapshots": snapshots,
        "investigations": final,
        "experiments": build_experiments_view(state, events[-1].occurred_at).model_dump(
            mode="json"
        ),
        "memory": memory,
        "twin_before": report["twin_before"],
        "twin_after": twin,
        "twin_provenance_before": provenance_before.model_dump(mode="json"),
        "twin_provenance_after": provenance_after.model_dump(mode="json"),
        "promotions": [
            {
                "sequence": e.sequence,
                "granted": e.event_type.value == "PROMOTION_GRANTED",
                **e.payload,
            }
            for e in events
            if e.event_type.value in ("PROMOTION_GRANTED", "PROMOTION_DENIED")
        ],
    }


def main() -> None:
    # Open once: bytes and regeneration receipt refer to the same file instance.
    with REPORT.open("rb") as source:
        data = source.read()
        modified_ns = str(fstat(source.fileno()).st_mtime_ns)
    state = build_web_state(json.loads(data))
    state["artifact_modified_ns"] = modified_ns
    print(canonical_json(state).decode())


if __name__ == "__main__":
    main()
