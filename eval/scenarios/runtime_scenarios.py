"""Frozen investigation/evidence scenarios (issues #48, #49, #50) - visible dev set.

Each scenario drives the *production* Serene stack (Telegram ingress, Hermes
runtime adapter, investigation controller, Minimum Sufficient Childhood Data
policy, bounded browser, independent verifier, ledger admission) with a
scripted Hermes transport, synthetic family data and a fake web. Only the
model wire is replaced. The run is reduced to the standard `Trajectory` and
scored against a grader-only `Oracle` that never reaches any prompt.

Scripted model replies make these runs byte-reproducible; they test the
architecture's handling of model output, not model quality. Live-model runs use
the same scenarios through `eval/runners/runtime_compare.py`.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import eval.scorers.runtime_scorers as scorers  # noqa: E402
from serene.adapters.hermes import HermesTransportError  # noqa: E402
from serene.adapters.hermes.scripted import raw_response  # noqa: E402
from serene.domain.entities import TERMINAL_INVESTIGATION_PHASES, Hypothesis  # noqa: E402
from serene.domain.events import AcquisitionMode, EventType  # noqa: E402
from serene.domain.values import SourceKind, SourceRef  # noqa: E402
from serene.policies.external_evidence import digest_consistent, host_of  # noqa: E402
from serene.policies.investigation import active_hypotheses, requests_of  # noqa: E402
from serene.projections.state import replay  # noqa: E402
from tests.evidence_support import FakeFetcher, browse_reply, evidence_factory  # noqa: E402
from tests.investigation_support import (  # noqa: E402
    TelegramScript,
    form_reply,
    make_investigation_rig,
    no_change_reply,
    plan_reply,
)
from tests.runtime_support import structure_reply  # noqa: E402

Trajectory = scorers.Trajectory
EvidenceUse = scorers.EvidenceUse
Oracle = scorers.Oracle

HUNGER: Final = "Hunger after a long day drives the distress"
TRANSITION: Final = "The abrupt transition at pickup drives the distress"
QUESTION: Final = "Why are daycare pickups so hard?"
REPORTS: Final = (
    ("Pickup was awful, crying at the door", "Crying at daycare pickup"),
    ("Another meltdown at pickup today", "Meltdown at daycare pickup"),
    ("Pickup tears again, calmer in the car", "Tearful at pickup, calmer later"),
)


# ---------------------------------------------------------------- candidates the model suggests
def snack_question(hyps: list[str]) -> list[dict[str, Any]]:
    transition, hunger = hyps[0], hyps[1]
    return [
        {
            "candidate_id": "snack-before-pickup",
            "requested_fields": ["calm_after_snack"],
            "acquisition_mode": "ASK_PARENT",
            "question": "Was pickup calmer on days he had a snack just before?",
            "rationale": "hunger predicts yes; an abrupt transition predicts no",
            "predictions": [
                {"hypothesis_id": hunger, "expected": "YES"},
                {"hypothesis_id": transition, "expected": "NO"},
            ],
        },
        {
            "candidate_id": "jacket-colour",
            "requested_fields": ["jacket_colour"],
            "acquisition_mode": "ASK_PARENT",
            "question": "What colour was his jacket?",
            "rationale": "irrelevant to both hypotheses",
        },
    ]


def pickup_policy(hyps: list[str]) -> list[dict[str, Any]]:
    transition, hunger = hyps[0], hyps[1]
    return [
        {
            "candidate_id": "pickup-policy",
            "requested_fields": ["pickup_window"],
            "acquisition_mode": "BROWSE",
            "subject": "daycare_pickup",
            "allowed_domains": ["example.org"],
            "rationale": "a late pickup window supports hunger; an early one supports transition",
            "predictions": [
                {"hypothesis_id": hunger, "expected": "YES"},
                {"hypothesis_id": transition, "expected": "NO"},
            ],
        }
    ]


def nothing_more(hyps: list[str]) -> list[dict[str, Any]]:
    return []


# ---------------------------------------------------------------- run harness
@dataclass
class SereneRun:
    rig: Any
    investigation_id: str
    script: Any = None  # the parent's phone (one update-id sequence per run)
    steps: int = 0
    lost_after_restart: int = 0
    redispatched_after_restart: int = 0

    def drive(self) -> list[Any]:
        steps = self.rig.stack.investigations.drive(self.rig.family.child_id, self.investigation_id)
        self.steps += len(steps)
        return steps


def open_investigation(seed: str, **rig_kwargs: Any) -> SereneRun:
    rig = make_investigation_rig(seed, **rig_kwargs)
    script = TelegramScript(rig)
    for text, statement in REPORTS:
        rig.transport.push("propose", structure_reply(statement))
        outcome = script.say(text).outcome
        assert outcome == "RECORDED_STRUCTURED", outcome
    inv = rig.stack.investigations.open(
        rig.family.child_id,
        QUESTION,
        opened_by=rig.family.parent,
        source=SourceRef(kind=SourceKind.TELEGRAM, source_id=rig.family.new_id("src")),
    )
    rig.transport.push("propose", form_reply([{"statement": TRANSITION}, {"statement": HUNGER}]))
    return SereneRun(rig, inv, script)


def trajectory_from_ledger(system: str, scenario_id: str, run: SereneRun) -> Any:
    """Reduce a Serene ledger to the standard trajectory. Pure function of ledger events."""
    rig, inv = run.rig, run.investigation_id
    events = rig.stack.ledger.get_events_for_child(rig.family.child_id)
    state = replay(events)
    verdicts = {
        e.payload["evidence_id"]: e
        for e in events
        if e.event_type in {EventType.EVIDENCE_VERIFIED, EventType.EVIDENCE_REJECTED}
    }
    cited = {
        evd
        for hyp_id in state.investigation_hypotheses.get(inv, [])
        for evd in getattr(state.entities[hyp_id].entity, "supporting_evidence_ids", ())
    }
    questions: list[tuple[str, ...]] = []
    evidence: list[Any] = []
    for record in requests_of(inv, state):
        mode = record.request.acquisition_mode
        if mode is AcquisitionMode.ASK_PARENT:
            questions.append(tuple(record.request.requested_fields))
        for evd in record.evidence_ids:
            entity_record = state.entities[evd]
            ev = entity_record.entity
            status = entity_record.verification_status.value
            if mode is AcquisitionMode.BROWSE:
                verdict = verdicts.get(evd)
                lineage = (
                    verdict is not None
                    and verdict.actor.kind.value == "VERIFIER"
                    and digest_consistent(ev)
                )
                kind, domain = "EXTERNAL", host_of(ev.source.uri)
            else:
                lineage = ev.source.kind is SourceKind.TELEGRAM and status == "VERIFIED"
                kind, domain = "ANSWER", "telegram"
            evidence.append(
                EvidenceUse(
                    ref=evd,
                    kind=kind,
                    verification=status,
                    source_domain=domain,
                    lineage_complete=lineage,
                    used=status == "VERIFIED" or evd in cited,  # context shows VERIFIED only
                    fields=tuple(record.request.requested_fields),
                )
            )
    live = [state.entities[h].entity for h in active_hypotheses(inv, state)]
    phase = state.investigation_phases[inv]
    failures: list[str] = []
    for e in events:
        if e.event_type is EventType.EVIDENCE_ACQUISITION_FAILED:
            failures.append(e.payload["failure"])
        elif e.event_type is EventType.OBSERVATION_STRUCTURING_FAILED:
            failures.append("STRUCTURING")
        elif (
            e.event_type is EventType.INVESTIGATION_PHASE_CHANGED
            and e.payload["to_phase"] == "PARKED_UNRESOLVED"
        ):
            failures += list(e.payload["reason_codes"])
    sink = rig.sink.records
    return Trajectory(
        system=system,
        scenario_id=scenario_id,
        questions=tuple(questions),
        evidence=tuple(evidence),
        hypotheses_retained=tuple(h.statement for h in live if isinstance(h, Hypothesis)),
        conclusion=None,  # Serene never asserts a single cause below the Promotion Gate
        terminal=phase.value if phase in TERMINAL_INVESTIGATION_PHASES else "WAITING",
        failures_recorded=tuple(failures),
        lost_after_restart=run.lost_after_restart,
        redispatched_after_restart=run.redispatched_after_restart,
        steps_used=run.steps,
        step_budget=32 * 4,
        model_calls=len(rig.transport.requests)
        - sum(1 for r in rig.transport.requests if r.purpose == "browse"),
        browse_actions=sum(
            int(attrs.get("action_count", 0)) for name, attrs in sink if name == "browser.acquire"
        ),
    )


# ---------------------------------------------------------------- scenarios
def ask_discriminates() -> Any:
    run = open_investigation("rt-ask")
    run.rig.transport.push("plan_evidence", plan_reply(snack_question))
    run.drive()
    assert run.script.tap_last(1).outcome == "ANSWER_RECORDED"  # NO
    run.rig.transport.push("propose", no_change_reply())
    run.rig.transport.push("plan_evidence", plan_reply(nothing_more))
    run.drive()
    return trajectory_from_ledger("serene", "ask_discriminates", run)


def browse_verified() -> Any:
    run = open_investigation("rt-browse", evidence=evidence_factory())
    run.rig.transport.push("plan_evidence", plan_reply(pickup_policy))
    run.rig.transport.push("browse", browse_reply())
    run.rig.transport.push("propose", no_change_reply())
    run.rig.transport.push("plan_evidence", plan_reply(nothing_more))
    run.drive()
    return trajectory_from_ledger("serene", "browse_verified", run)


def browse_unsupported_page() -> Any:
    fetcher = FakeFetcher(pages={"https://example.org/policies/pickup": "This page has moved."})
    run = open_investigation("rt-poison", evidence=evidence_factory(fetcher))
    run.rig.transport.push("plan_evidence", plan_reply(pickup_policy))
    run.rig.transport.push("browse", browse_reply())
    run.rig.transport.push("propose", no_change_reply())
    run.rig.transport.push("plan_evidence", plan_reply(nothing_more))
    run.drive()
    return trajectory_from_ledger("serene", "browse_unsupported_page", run)


def browser_flaky_restart() -> Any:
    run = open_investigation("rt-flaky", evidence=evidence_factory())
    run.rig.transport.push("plan_evidence", plan_reply(pickup_policy))
    flaky = HermesTransportError("TRANSIENT", "RESET")
    run.rig.transport.push("browse", flaky, flaky)  # adapter's own retry fails too
    run.drive()  # records attempt 1, yields RETRY_SCHEDULED
    before = replay(run.rig.stack.ledger.get_events_for_child(run.rig.family.child_id))

    # Simulated process restart: a fresh stack over the same ledger store.
    restarted = make_investigation_rig(
        "rt-flaky",
        evidence=evidence_factory(),
        store=run.rig.family.store,
        clock=run.rig.family.clock,
        resume_counter=run.rig.family._counter,
    )
    restarted.transport.push("browse", browse_reply())
    restarted.transport.push("propose", no_change_reply())
    restarted.transport.push("plan_evidence", plan_reply(nothing_more))
    resumed = SereneRun(restarted, run.investigation_id, steps=run.steps)  # no parent input
    after_restart = replay(restarted.stack.ledger.get_events_for_child(restarted.family.child_id))
    resumed.lost_after_restart = sum(
        1 for rid in before.evidence_requests if rid not in after_restart.evidence_requests
    ) + sum(1 for e in before.entities if e not in after_restart.entities)
    resumed.drive()
    resumed.drive()  # an extra tick on a terminal investigation must not re-dispatch
    final = replay(restarted.stack.ledger.get_events_for_child(restarted.family.child_id))
    resumed.redispatched_after_restart = max(
        0, sum(len(r.evidence_ids) for r in final.evidence_requests.values()) - 1
    )
    resumed.rig.transport.requests[:0] = run.rig.transport.requests  # whole-task model accounting
    resumed.rig.sink.records[:0] = run.rig.sink.records
    return trajectory_from_ledger("serene", "browser_flaky_restart", resumed)


def parent_silent() -> Any:
    run = open_investigation("rt-silent")
    run.rig.transport.push("plan_evidence", plan_reply(snack_question))
    run.drive()  # question sent; waiting for parent
    run.rig.family.clock.advance(timedelta(hours=49))
    run.drive()
    return trajectory_from_ledger("serene", "parent_silent", run)


def planner_down() -> Any:
    run = open_investigation("rt-planner")
    run.rig.transport.push("plan_evidence", raw_response("garbage"), raw_response("garbage"))
    run.drive()
    return trajectory_from_ledger("serene", "planner_down", run)


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    run_serene: Callable[[], Any]
    oracle: Any
    # Runtime-visible inputs shared with the baselines (never the oracle).
    parent_answers: dict[str, str | None]
    pages: dict[str, str]


_WEB: Final = {
    "https://example.org/policies/pickup": (
        "Welcome to Example Daycare. Daycare pickup policy. Children may be collected "
        "between 15:00-17:30. A snack is served at 14:30 every day."
    )
}

SCENARIOS: Final[dict[str, Scenario]] = {
    s.scenario_id: s
    for s in (
        Scenario(
            "ask_discriminates",
            ask_discriminates,
            Oracle(
                true_cause_terms=("transition",),
                discriminating_fields=("calm_after_snack",),
                expected_terminal="COMPLETE",
                grader_note="the snack answer is NO, which contradicts hunger",
            ),
            {"calm_after_snack": "NO", "jacket_colour": "blue"},
            {},
        ),
        Scenario(
            "browse_verified",
            browse_verified,
            Oracle(
                true_cause_terms=("hunger",),
                discriminating_fields=("pickup_window",),
                expected_terminal="COMPLETE",
                allowed_domains=("example.org",),
                grader_note="a late pickup window with an early snack supports hunger",
            ),
            {},
            dict(_WEB),
        ),
        Scenario(
            "browse_unsupported_page",
            browse_unsupported_page,
            Oracle(
                true_cause_terms=("hunger",),
                discriminating_fields=("pickup_window",),
                expected_terminal="COMPLETE",
                allowed_domains=("example.org",),
                grader_note="the claimed page no longer states the window: must not be used",
            ),
            {},
            {"https://example.org/policies/pickup": "This page has moved."},
        ),
        Scenario(
            "browser_flaky_restart",
            browser_flaky_restart,
            Oracle(
                true_cause_terms=("hunger",),
                discriminating_fields=("pickup_window",),
                expected_terminal="COMPLETE",
                allowed_domains=("example.org",),
                injected_failures=("TRANSIENT",),
                grader_note="one transient browser failure, then a process restart",
            ),
            {},
            dict(_WEB),
        ),
        Scenario(
            "parent_silent",
            parent_silent,
            Oracle(
                true_cause_terms=("transition",),
                discriminating_fields=("calm_after_snack",),
                expected_terminal="PARKED_UNRESOLVED",
                injected_failures=("PARENT_NO_RESPONSE",),
                grader_note="the parent never answers; nothing else can discriminate",
            ),
            {"calm_after_snack": None},
            {},
        ),
        Scenario(
            "planner_down",
            planner_down,
            Oracle(
                true_cause_terms=("transition",),
                discriminating_fields=("calm_after_snack",),
                expected_terminal="PARKED_UNRESOLVED",
                injected_failures=("PLANNER_UNAVAILABLE",),
                grader_note="evidence planning is unavailable; completion would be false",
            ),
            {"calm_after_snack": "NO"},
            {},
        ),
    )
}
