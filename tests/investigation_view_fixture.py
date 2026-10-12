"""The synthetic investigation fixture the Today / Investigations surfaces are
tested with (issue #35).

It is produced by running the real investigation controller, not written by
hand: three Telegram reports, an investigation, two competing hypotheses from
a scripted model, a question selected by the minimum-data policy, then (after
the snapshot) the parent's answer, verification and evaluation. The fixture is
the child's serene.projection_state rows exactly as the kernel's projection
publisher writes them (#33): a snapshot while Serene waits for the parent,
then each later change in ledger order, so the web app follows them through
the same Realtime path it uses live.

`tests/test_investigation_view.py` checks that the checked-in JSON is exactly
what this produces. To regenerate it:

    uv run python -m tests.investigation_view_fixture
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from serene.domain.events import DomainEvent
from serene.domain.values import SourceKind, SourceRef
from serene.investigation.service import StepResult
from serene.ledger.service import EventLedger
from serene.projections.state import KernelState
from serene.projections.views import project
from tests.investigation_support import (
    InvestigationRig,
    TelegramScript,
    form_reply,
    make_investigation_rig,
    no_change_reply,
    plan_reply,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "app" / "web" / "fixtures" / "synthetic-investigation.json"
QUESTION = "Why are daycare pickups so hard?"
HUNGER = "Hunger after a long day drives the distress"
TRANSITION = "The abrupt transition at pickup drives the distress"


def discriminating_question(rig: InvestigationRig) -> Any:
    """The planner's candidate, with each prediction bound to its hypothesis by
    statement (never by list position), so the rationale and predictions agree."""

    def make(hyps: list[str]) -> list[dict[str, Any]]:
        state = rig.stack.ledger.replay_events(rig.family.child_id)
        by_statement = {state.entities[h].entity.statement: h for h in hyps}
        return [
            {
                "candidate_id": "snack-before-pickup",
                "requested_fields": ["calm_after_snack"],
                "acquisition_mode": "ASK_PARENT",
                "question": "Was pickup calmer on days he had a snack just before?",
                "rationale": "hunger predicts yes; an abrupt transition predicts no",
                "predictions": [
                    {"hypothesis_id": by_statement[HUNGER], "expected": "YES"},
                    {"hypothesis_id": by_statement[TRANSITION], "expected": "NO"},
                ],
            }
        ]

    return make


def _nothing_more(hyps: list[str]) -> list[dict[str, Any]]:
    return []


@dataclass
class Recorder:
    """Collects projection_state rows the way `projection_publisher` writes them."""

    rows: list[dict[str, Any]] = field(default_factory=list)

    def __call__(self, event: DomainEvent, state: KernelState) -> None:
        for name, value in sorted(project(state).items()):
            self.rows.append(
                {
                    "child_id": event.child_id,
                    "projection": name,
                    "state": value,
                    "last_sequence": event.sequence,
                    "last_event_hash": event.event_hash,
                }
            )


@dataclass
class InvestigationFixture:
    rig: InvestigationRig
    investigation_id: str
    steps: list[tuple[KernelState, StepResult]]
    snapshot: list[dict[str, Any]]
    changes: list[dict[str, Any]]


def build_fixture(seed: str = "investigation-view") -> InvestigationFixture:
    rig = make_investigation_rig(seed)
    fam = rig.family
    recorder = Recorder()
    # The kernel's own after-append hook (#33), recording instead of writing Postgres.
    rig.stack.ledger._after_append = recorder
    assert isinstance(rig.stack.ledger, EventLedger)
    script = TelegramScript(rig)
    from tests.runtime_support import structure_reply

    for text, statement in [
        ("Pickup was awful, crying at the door", "Crying at daycare pickup"),
        ("Another meltdown at pickup today", "Meltdown at daycare pickup"),
        ("Pickup tears again, calmer in the car", "Tearful at pickup, calmer later"),
    ]:
        rig.transport.push("propose", structure_reply(statement))
        assert script.say(text).outcome == "RECORDED_STRUCTURED"
    inv = rig.stack.investigations.open(
        fam.child_id,
        QUESTION,
        opened_by=fam.parent,
        source=SourceRef(kind=SourceKind.TELEGRAM, source_id=fam.new_id("src")),
    )
    rig.transport.push("propose", form_reply([{"statement": TRANSITION}, {"statement": HUNGER}]))
    rig.transport.push("plan_evidence", plan_reply(discriminating_question(rig)))

    steps: list[tuple[KernelState, StepResult]] = []

    def drive() -> None:
        while True:
            before = rig.stack.ledger.replay_events(fam.child_id)
            result = rig.stack.investigations.step(fam.child_id, inv)
            steps.append((before, result))
            if result.waiting or result.terminal or result.action == "TRANSITION_REFUSED":
                return

    drive()  # ... -> ASKING_HUMAN, waiting for the parent
    snapshot = _latest(recorder.rows)
    seen = len(recorder.rows)
    assert script.tap_last(1).outcome == "ANSWER_RECORDED"  # NO: contradicts hunger
    rig.transport.push("propose", no_change_reply())
    rig.transport.push("plan_evidence", plan_reply(_nothing_more))
    drive()  # VERIFYING -> EVALUATING -> COMPLETE
    steps.append((rig.stack.ledger.replay_events(fam.child_id), _terminal_step(rig, inv)))
    changes = _changed_only(snapshot, recorder.rows[seen:])
    return InvestigationFixture(rig, inv, steps, snapshot, changes)


def _terminal_step(rig: InvestigationRig, inv: str) -> StepResult:
    return rig.stack.investigations.step(rig.family.child_id, inv)


def _latest(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        latest[row["projection"]] = row
    return [latest[name] for name in sorted(latest)]


def _changed_only(
    snapshot: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """What Realtime delivers: only rows whose state changed (`advance` skips the rest)."""
    current = {r["projection"]: r["state"] for r in snapshot}
    out = []
    for row in rows:
        if current.get(row["projection"]) != row["state"]:
            current[row["projection"]] = row["state"]
            out.append(row)
    return out


def fixture_json(fixture: InvestigationFixture) -> str:
    payload = {"snapshot": fixture.snapshot, "changes": fixture.changes}
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    FIXTURE.write_text(fixture_json(build_fixture()), encoding="utf-8", newline="\n")
    print(f"wrote {FIXTURE.relative_to(ROOT)}")
