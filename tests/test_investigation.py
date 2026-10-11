"""Investigation state machine, retrieval, hypotheses and minimum data (#10-#14, #21)."""

from __future__ import annotations

import dataclasses
import json
from datetime import timedelta
from typing import Any

import pytest

from serene.adapters.cfoai import TableCostModel
from serene.adapters.hermes import HermesTransportError
from serene.adapters.hermes.scripted import raw_response
from serene.adapters.hermes.wire import WireError, WireProposals, parse_wire
from serene.domain.entities import (
    TERMINAL_INVESTIGATION_PHASES,
    Hypothesis,
    InvestigationPhase,
)
from serene.domain.events import (
    AcquisitionMode,
    EventType,
    HypothesisPrediction,
    InformationValue,
    InvestigationPhaseChanged,
    PredictedAnswer,
)
from serene.domain.values import EpistemicLevel, SourceKind, SourceRef
from serene.investigation.context import ContextRetriever, Layer, disagreements_in
from serene.investigation.minimum_data import (
    EvidenceCandidate,
    MinimumDataPolicy,
    ScoredCandidate,
)
from serene.ledger.service import AdmissionRejected
from serene.lineage.chain import verify_hash_chain
from serene.policies.acquisition import AcquisitionSafety
from serene.policies.investigation import PHASE_TRANSITIONS
from serene.projections import rebuild_projections
from serene.projections.state import replay
from serene.testing import SyntheticFamily
from tests.investigation_support import (
    TelegramScript,
    form_reply,
    make_investigation_rig,
    no_change_reply,
    plan_reply,
)
from tests.runtime_support import InMemoryMemory

P = InvestigationPhase
HUNGER = "Hunger after a long day drives the distress"
TRANSITION = "The abrupt transition at pickup drives the distress"


# ---------------------------------------------------------------- transition table
def test_every_phase_is_enumerated_and_terminals_are_explicit() -> None:
    assert set(PHASE_TRANSITIONS) == set(InvestigationPhase)
    assert (
        {p for p, nxt in PHASE_TRANSITIONS.items() if not nxt}
        == set(TERMINAL_INVESTIGATION_PHASES)
        == {P.COMPLETE, P.PARKED_UNRESOLVED}
    )
    for phase, nxt in PHASE_TRANSITIONS.items():
        if phase not in TERMINAL_INVESTIGATION_PHASES:
            assert P.PARKED_UNRESOLVED in nxt, phase  # honest parking is always possible
    assert PHASE_TRANSITIONS[P.EVALUATING] >= {P.NEEDS_APPROVAL, P.COMPLETE, P.NEEDS_EVIDENCE}
    assert PHASE_TRANSITIONS[P.NEEDS_EVIDENCE] >= {P.ASKING_HUMAN, P.RESEARCHING}


def _fam_with_investigation(seed: str = "sm") -> tuple[SyntheticFamily, Any]:
    fam = SyntheticFamily(seed=seed)
    fam.observe("tearful pickup", day=0)
    return fam, fam.open_investigation("why are pickups hard?")


def _phase(fam: SyntheticFamily, inv: Any, frm: P, to: P) -> Any:
    return fam.append(
        fam.draft(
            EventType.INVESTIGATION_PHASE_CHANGED,
            fam.system,
            InvestigationPhaseChanged(
                investigation_id=inv.investigation_id,
                from_phase=frm,
                to_phase=to,
                reason_codes=("TEST",),
            ),
        )
    )


ILLEGAL = [
    (P.UNDERSTANDING, P.COMPLETE),
    (P.UNDERSTANDING, P.FORMING_HYPOTHESES),
    (P.UNDERSTANDING, P.NEEDS_APPROVAL),
    (P.UNDERSTANDING, P.EVALUATING),
]


@pytest.mark.parametrize(("frm", "to"), ILLEGAL)
def test_illegal_transitions_are_rejected(frm: P, to: P) -> None:
    fam, inv = _fam_with_investigation()
    head = fam.state().last_event_hash
    with pytest.raises(AdmissionRejected) as exc:
        _phase(fam, inv, frm, to)
    assert exc.value.reason_codes[0].startswith("ILLEGAL_TRANSITION")
    assert fam.state().last_event_hash == head


def test_stale_from_phase_is_rejected() -> None:
    fam, inv = _fam_with_investigation()
    _phase(fam, inv, P.UNDERSTANDING, P.RETRIEVING_CONTEXT)
    with pytest.raises(AdmissionRejected) as exc:
        _phase(fam, inv, P.UNDERSTANDING, P.RETRIEVING_CONTEXT)
    assert exc.value.reason_codes == ("STALE_PHASE:RETRIEVING_CONTEXT",)


@pytest.mark.parametrize("terminal", [P.PARKED_UNRESOLVED])
def test_terminal_phases_cannot_silently_resume(terminal: P) -> None:
    fam, inv = _fam_with_investigation()
    _phase(fam, inv, P.UNDERSTANDING, terminal)
    for target in InvestigationPhase:
        with pytest.raises(AdmissionRejected) as exc:
            _phase(fam, inv, terminal, target)
        assert exc.value.reason_codes[0] == f"TERMINAL_PHASE:{terminal.value}"


def test_no_hypothesis_can_attach_to_a_terminal_investigation() -> None:
    fam = SyntheticFamily(seed="term-hyp")
    o1 = fam.observe("tearful pickup", day=0)
    o2 = fam.observe("tearful pickup again", day=1)
    pattern = fam.pattern((o1, o2), "pickups are tearful")
    inv = fam.open_investigation("why?")
    _phase(fam, inv, P.UNDERSTANDING, P.PARKED_UNRESOLVED)
    with pytest.raises(AdmissionRejected) as exc:
        fam.hypothesis(inv, (pattern,), "late hypothesis")
    assert any(r.startswith("INVESTIGATION_PHASE_TERMINAL") for r in exc.value.reason_codes)


def test_forming_needs_two_competing_hypotheses() -> None:
    fam = SyntheticFamily(seed="guard")
    o1 = fam.observe("tearful pickup", day=0)
    o2 = fam.observe("tearful pickup again", day=1)
    pattern = fam.pattern((o1, o2), "pickups are tearful")
    inv = fam.open_investigation("why?")
    _phase(fam, inv, P.UNDERSTANDING, P.RETRIEVING_CONTEXT)
    _phase(fam, inv, P.RETRIEVING_CONTEXT, P.FORMING_HYPOTHESES)
    fam.hypothesis(inv, (pattern,), TRANSITION)
    with pytest.raises(AdmissionRejected) as exc:
        _phase(fam, inv, P.FORMING_HYPOTHESES, P.NEEDS_EVIDENCE)
    assert exc.value.reason_codes == ("INSUFFICIENT_COMPETING_HYPOTHESES",)
    fam.hypothesis(inv, (pattern,), HUNGER)
    _phase(fam, inv, P.FORMING_HYPOTHESES, P.NEEDS_EVIDENCE)
    for to, code in [
        (P.ASKING_HUMAN, "NO_OPEN_QUESTION"),
        (P.RESEARCHING, "NO_OPEN_BROWSE_REQUEST"),
    ]:
        with pytest.raises(AdmissionRejected) as exc:
            _phase(fam, inv, P.NEEDS_EVIDENCE, to)
        assert exc.value.reason_codes == (code,)


def test_system_and_policy_only_may_move_phases() -> None:
    fam, inv = _fam_with_investigation()
    with pytest.raises(AdmissionRejected) as exc:
        fam.append(
            fam.draft(
                EventType.INVESTIGATION_PHASE_CHANGED,
                fam.agent,
                InvestigationPhaseChanged(
                    investigation_id=inv.investigation_id,
                    from_phase=P.UNDERSTANDING,
                    to_phase=P.RETRIEVING_CONTEXT,
                    reason_codes=("MODEL_SAYS_SO",),
                ),
            )
        )
    assert exc.value.reason_codes == ("ACTOR_NOT_PERMITTED:AGENT",)


# ---------------------------------------------------------------- end to end (ASK path)
def _report_three(script: TelegramScript, rig: Any) -> None:
    for text, statement in [
        ("Pickup was awful, crying at the door", "Crying at daycare pickup"),
        ("Another meltdown at pickup today", "Meltdown at daycare pickup"),
        ("Pickup tears again, calmer in the car", "Tearful at pickup, calmer later"),
    ]:
        from tests.runtime_support import structure_reply

        rig.transport.push("propose", structure_reply(statement))
        assert script.say(text).outcome == "RECORDED_STRUCTURED"


def _discriminating_question(hyps: list[str]) -> list[dict[str, Any]]:
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


def _after_answer(hyps: list[str]) -> list[dict[str, Any]]:
    # Only predictions on hypotheses that are still live count; nothing discriminates now.
    return [
        {
            "candidate_id": "snack-policy",
            "requested_fields": ["snack_schedule"],
            "acquisition_mode": "BROWSE",
            "subject": "daycare_snack_policy",
            "allowed_domains": ["example.org"],
            "rationale": "only bears on the hunger hypothesis",
            "predictions": [{"hypothesis_id": h, "expected": "YES"} for h in hyps[1:]],
        }
    ]


def run_ask_investigation(seed: str = "e2e", store: Any = None) -> tuple[Any, str]:
    rig = make_investigation_rig(seed, store=store)
    script = TelegramScript(rig)
    _report_three(script, rig)
    inv = rig.stack.investigations.open(
        rig.family.child_id,
        "Why are daycare pickups so hard?",
        opened_by=rig.family.parent,
        source=SourceRef(kind=SourceKind.TELEGRAM, source_id=rig.family.new_id("src")),
    )
    rig.transport.push("propose", form_reply([{"statement": TRANSITION}, {"statement": HUNGER}]))
    rig.transport.push("plan_evidence", plan_reply(_discriminating_question))
    first = rig.stack.investigations.drive(rig.family.child_id, inv)
    assert [r.to_phase for r in first[:-1]] == [
        P.RETRIEVING_CONTEXT,
        P.FORMING_HYPOTHESES,
        P.NEEDS_EVIDENCE,
        P.ASKING_HUMAN,
    ]
    assert first[-1].action == "WAITING_FOR_PARENT" and first[-1].waiting
    assert script.tap_last(1).outcome == "ANSWER_RECORDED"  # NO: contradicts hunger
    rig.transport.push("propose", no_change_reply())
    rig.transport.push("plan_evidence", plan_reply(_after_answer))
    second = rig.stack.investigations.drive(rig.family.child_id, inv)
    assert [r.to_phase for r in second] == [P.VERIFYING, P.EVALUATING, P.COMPLETE]
    return rig, inv


def test_ask_investigation_reaches_complete_and_keeps_competitors() -> None:
    rig, inv = run_ask_investigation()
    state = rig.stack.ledger.replay_events(rig.family.child_id)
    assert state.investigation_phases[inv] is P.COMPLETE
    hyps = state.investigation_hypotheses[inv]
    assert len(hyps) == 2
    # generation never declared a winner: both remain level-3 hypotheses in the ledger
    assert {state.hypothesis_levels[h] for h in hyps} == {EpistemicLevel.HYPOTHESIS}
    (request,) = state.evidence_requests.values()
    assert request.request.information_value is InformationValue.HIGH
    assert request.request.acquisition_mode is AcquisitionMode.ASK_PARENT
    assert len(rig.outbox.sent) == 1  # exactly one question was asked
    assert "jacket" not in rig.outbox.sent[0][1]


def test_phase_state_reconstructs_entirely_from_the_ledger() -> None:
    rig, inv = run_ask_investigation("replay")
    events = rig.events()
    assert verify_hash_chain(events).ok
    rebuilt = replay(events)
    assert rebuilt.investigation_phases[inv] is P.COMPLETE
    projections = rebuild_projections(events)
    assert inv not in projections["active_investigations"]  # terminal phases are not active
    phases = [
        e.payload["to_phase"]
        for e in events
        if e.event_type is EventType.INVESTIGATION_PHASE_CHANGED
    ]
    assert phases == [
        "RETRIEVING_CONTEXT",
        "FORMING_HYPOTHESES",
        "NEEDS_EVIDENCE",
        "ASKING_HUMAN",
        "VERIFYING",
        "EVALUATING",
        "COMPLETE",
    ]


def test_a_completed_investigation_never_resumes() -> None:
    rig, inv = run_ask_investigation("no-resume")
    before = len(rig.events())
    result = rig.stack.investigations.step(rig.family.child_id, inv)
    assert result.action == "TERMINAL" and len(rig.events()) == before


def test_restart_resumes_from_ledger_state_with_a_fresh_service() -> None:
    from serene.adapters.in_memory_event_store import InMemoryEventStore

    store = InMemoryEventStore()
    rig = make_investigation_rig("restart", store=store)
    script = TelegramScript(rig)
    _report_three(script, rig)
    inv = rig.stack.investigations.open(
        rig.family.child_id,
        "Why are pickups hard?",
        opened_by=rig.family.parent,
        source=SourceRef(kind=SourceKind.TELEGRAM, source_id=rig.family.new_id("src")),
    )
    rig.transport.push("propose", form_reply([{"statement": TRANSITION}, {"statement": HUNGER}]))
    rig.transport.push("plan_evidence", plan_reply(_discriminating_question))
    rig.stack.investigations.drive(rig.family.child_id, inv)
    # "crash": a brand-new service over the same store picks up at ASKING_HUMAN.
    revived = make_investigation_rig("restart", store=store)
    assert revived.phase(inv) == "ASKING_HUMAN"
    revived.family.clock = rig.family.clock
    result = revived.stack.investigations.step(rig.family.child_id, inv)
    assert result.waiting and result.action == "WAITING_FOR_PARENT"


def test_unanswered_question_parks_honestly_after_timeout() -> None:
    rig = make_investigation_rig("timeout")
    script = TelegramScript(rig)
    _report_three(script, rig)
    inv = rig.stack.investigations.open(
        rig.family.child_id,
        "Why?",
        opened_by=rig.family.parent,
        source=SourceRef(kind=SourceKind.TELEGRAM, source_id=rig.family.new_id("src")),
    )
    rig.transport.push("propose", form_reply([{"statement": TRANSITION}, {"statement": HUNGER}]))
    rig.transport.push("plan_evidence", plan_reply(_discriminating_question))
    rig.stack.investigations.drive(rig.family.child_id, inv)
    rig.family.clock.advance(timedelta(hours=49))
    result = rig.stack.investigations.step(rig.family.child_id, inv)
    assert result.to_phase is P.PARKED_UNRESOLVED and result.reason_codes == ("PARENT_NO_RESPONSE",)


@pytest.mark.parametrize(
    "failure",
    [raw_response("nope"), HermesTransportError("AUTH", "HTTP_401")],
)
def test_runtime_failure_parks_instead_of_inventing_hypotheses(failure: Any) -> None:
    rig = make_investigation_rig("rt-fail")
    script = TelegramScript(rig)
    _report_three(script, rig)
    inv = rig.stack.investigations.open(
        rig.family.child_id,
        "Why?",
        opened_by=rig.family.parent,
        source=SourceRef(kind=SourceKind.TELEGRAM, source_id=rig.family.new_id("src")),
    )
    rig.transport.push("propose", failure, failure)
    results = rig.stack.investigations.drive(rig.family.child_id, inv)
    assert results[-1].to_phase is P.PARKED_UNRESOLVED
    assert rig.stack.ledger.replay_events(rig.family.child_id).investigation_hypotheses == {}


def test_planner_failure_is_never_read_as_sufficient_evidence() -> None:
    rig = make_investigation_rig("plan-fail")
    script = TelegramScript(rig)
    _report_three(script, rig)
    inv = rig.stack.investigations.open(
        rig.family.child_id,
        "Why?",
        opened_by=rig.family.parent,
        source=SourceRef(kind=SourceKind.TELEGRAM, source_id=rig.family.new_id("src")),
    )
    rig.transport.push("propose", form_reply([{"statement": TRANSITION}, {"statement": HUNGER}]))
    rig.transport.push("plan_evidence", raw_response("garbage"), raw_response("garbage"))
    results = rig.stack.investigations.drive(rig.family.child_id, inv)
    assert results[-1].to_phase is P.PARKED_UNRESOLVED
    assert results[-1].reason_codes == ("PLANNER_UNAVAILABLE",)


def test_a_single_hypothesis_parks_rather_than_committing_prematurely() -> None:
    rig = make_investigation_rig("single")
    script = TelegramScript(rig)
    _report_three(script, rig)
    inv = rig.stack.investigations.open(
        rig.family.child_id,
        "Why?",
        opened_by=rig.family.parent,
        source=SourceRef(kind=SourceKind.TELEGRAM, source_id=rig.family.new_id("src")),
    )
    rig.transport.push("propose", form_reply([{"statement": TRANSITION}]))
    results = rig.stack.investigations.drive(rig.family.child_id, inv)
    assert results[-1].reason_codes == ("INSUFFICIENT_COMPETING_HYPOTHESES",)


# ---------------------------------------------------------------- hypotheses (#12)
def test_competing_hypotheses_retain_support_counter_scope_and_confounders() -> None:
    rig, inv = run_ask_investigation("hyps")
    state = rig.stack.ledger.replay_events(rig.family.child_id)
    hyps = [state.entities[h].entity for h in state.investigation_hypotheses[inv]]
    first, second = hyps
    assert second.competing_hypothesis_ids == (first.hypothesis_id,)
    assert second.statement in first.alternative_explanations  # siblings considered
    for hyp in hyps:
        assert hyp.scope.contexts == ("daycare_pickup",)
        assert hyp.known_confounders and hyp.falsification_criteria
        assert isinstance(hyp.counter_evidence_ids, tuple)


def test_counter_evidence_is_stored_per_hypothesis() -> None:
    fam = SyntheticFamily(seed="counter")
    o1 = fam.observe("tearful pickup", day=0)
    o2 = fam.observe("tearful pickup again", day=1)
    calm = fam.report("calm pickup with a snack")
    pattern = fam.pattern((o1, o2), "pickups are tearful")
    inv = fam.open_investigation("why?")
    base = fam.hypothesis(inv, (pattern,), HUNGER)
    data = base.model_dump(mode="json")
    data.update(
        hypothesis_id=fam.new_id("hyp"),
        statement=TRANSITION,
        counter_evidence_ids=[calm.evidence_id],
        competing_hypothesis_ids=[base.hypothesis_id],
    )
    rival = Hypothesis.model_validate_json(json.dumps(data))
    from serene.domain.events import HypothesisProposed

    fam.append(
        fam.draft(
            EventType.HYPOTHESIS_PROPOSED,
            fam.agent,
            HypothesisProposed(hypothesis=rival),
            status=fam.state().verification_of(base.hypothesis_id),
            derived_from=(fam.introduced_by[pattern.pattern_id],),
        )
    )
    state = fam.state()
    assert state.entities[rival.hypothesis_id].entity.counter_evidence_ids == (calm.evidence_id,)
    assert state.entities[base.hypothesis_id].entity.counter_evidence_ids == ()


@pytest.mark.parametrize("field", ["is_true", "verified", "winner", "level"])
def test_generation_cannot_set_a_truth_flag(field: str) -> None:
    wire = {
        "contract": "serene-hermes-wire/1",
        "proposals": [
            {
                "kind": "hypothesis",
                "ref": "H1",
                "pattern_refs": ["P1"],
                "statement": "x",
                "falsification_criteria": ["y"],
                "contexts": ["daycare_pickup"],
                field: True,
            }
        ],
    }
    with pytest.raises(WireError):
        parse_wire(json.dumps(wire), WireProposals)
    assert field not in Hypothesis.model_fields


# ---------------------------------------------------------------- retrieval (#11, #21)
def _fam_for_context() -> tuple[SyntheticFamily, Any]:
    fam = SyntheticFamily(seed="ctx")
    parent_obs = fam.observe("Pickup was calm and easy", day=0)
    caregiver_ev = fam.report("Pickup was a disaster, screaming", observer=fam.caregiver)
    fam.structure(
        (caregiver_ev,), "Pickup was a disaster, screaming", observed_at=parent_obs.observed_at
    )
    fam.report("rumour from another parent", verified=False)
    inv = fam.open_investigation("Why are daycare pickups hard?")
    return fam, inv


MEMORY = {
    "learnings/pickup.md": (
        "We BELIEVE pickup distress is caused by hunger. level=CONTEXTUAL_LEARNING status=ACTIVE."
    ),
    "routines/evening.md": "Dinner is at six. Daycare pickup at five.",
    "child/profile.md": "Unrelated: likes trains.",
}


def test_three_layers_are_returned_distinctly() -> None:
    fam, inv = _fam_for_context()
    ctx = ContextRetriever(InMemoryMemory(MEMORY)).retrieve(
        fam.state(),
        child_id=fam.child_id,
        investigation_id=inv.investigation_id,
        now=fam.clock.now(),
    )
    assert {i.layer for i in ctx.experience} == {Layer.EXPERIENCE}
    assert {m.layer for m in ctx.memory} == {Layer.MEMORY}
    assert all(b.layer is Layer.BELIEF for b in ctx.belief)
    assert {m.path for m in ctx.memory} == {"learnings/pickup.md", "routines/evening.md"}


def test_memory_files_never_masquerade_as_belief() -> None:
    fam, inv = _fam_for_context()
    ctx = ContextRetriever(InMemoryMemory(MEMORY)).retrieve(
        fam.state(),
        child_id=fam.child_id,
        investigation_id=inv.investigation_id,
        now=fam.clock.now(),
    )
    assert not any("hunger" in b.statement.lower() for b in ctx.belief)
    assert all(b.entity_id in fam.state().entities for b in ctx.belief)  # ledger-only
    assert not any(m.path in ctx.visible_ids() for m in ctx.memory)  # memory is not citable


def test_retrieval_is_deterministic_for_a_fixed_snapshot() -> None:
    fam, inv = _fam_for_context()
    retriever = ContextRetriever(InMemoryMemory(MEMORY))
    a = retriever.retrieve(
        fam.state(),
        child_id=fam.child_id,
        investigation_id=inv.investigation_id,
        now=fam.clock.now(),
    )
    b = retriever.retrieve(
        replay(fam.ledger.get_events_for_child(fam.child_id)),
        child_id=fam.child_id,
        investigation_id=inv.investigation_id,
        now=fam.clock.now(),
    )
    assert a.digest == b.digest and a == b


def test_unverified_evidence_is_withheld_from_context() -> None:
    fam, inv = _fam_for_context()
    ctx = ContextRetriever().retrieve(
        fam.state(),
        child_id=fam.child_id,
        investigation_id=inv.investigation_id,
        now=fam.clock.now(),
    )
    assert all("rumour" not in i.content for i in ctx.experience)
    assert [s.value for _, s in ctx.withheld] == ["UNVERIFIED"]


def test_caregiver_disagreement_is_preserved_and_exposed() -> None:
    fam, inv = _fam_for_context()
    ctx = ContextRetriever().retrieve(
        fam.state(),
        child_id=fam.child_id,
        investigation_id=inv.investigation_id,
        now=fam.clock.now(),
    )
    (disagreement,) = [d for d in ctx.disagreements if d.diverges]
    kinds = sorted(a.observer_kind for a in disagreement.accounts)
    assert kinds == ["CAREGIVER", "PARENT"]
    statements = {a.statement for a in disagreement.accounts}
    assert statements == {"Pickup was calm and easy", "Pickup was a disaster, screaming"}


def test_no_averaging_or_reliability_is_synthesized() -> None:
    fam, inv = _fam_for_context()
    ctx = ContextRetriever().retrieve(
        fam.state(),
        child_id=fam.child_id,
        investigation_id=inv.investigation_id,
        now=fam.clock.now(),
    )
    for obj in (*ctx.disagreements, *(a for d in ctx.disagreements for a in d.accounts)):
        names = {f.name for f in dataclasses.fields(obj)}
        assert not names & {"reliability", "weight", "score", "average", "consensus", "confidence"}
    assert len(disagreements_in(ctx.experience)) == len(ctx.disagreements)


# ---------------------------------------------------------------- minimum data (#13, #14)
def _ctx_with_two_hypotheses() -> tuple[Any, list[str]]:
    fam = SyntheticFamily(seed="mscd")
    o1 = fam.observe("tearful pickup", day=0)
    o2 = fam.observe("tearful pickup again", day=1)
    pattern = fam.pattern((o1, o2), "pickups are tearful")
    inv = fam.open_investigation("why?")
    h1 = fam.hypothesis(inv, (pattern,), TRANSITION)
    h2 = fam.hypothesis(inv, (pattern,), HUNGER)
    ctx = ContextRetriever().retrieve(
        fam.state(),
        child_id=fam.child_id,
        investigation_id=inv.investigation_id,
        now=fam.clock.now(),
    )
    return ctx, [h1.hypothesis_id, h2.hypothesis_id]


def _ask(
    cid: str, predictions: dict[str, str], fields: tuple[str, ...] = ("f",)
) -> EvidenceCandidate:
    return EvidenceCandidate(
        candidate_id=cid,
        requested_fields=fields or (cid.replace("-", "_"),),
        acquisition_mode=AcquisitionMode.ASK_PARENT,
        question=f"question {cid}?",
        rationale="r",
        predictions=tuple(
            HypothesisPrediction(hypothesis_id=h, expected=PredictedAnswer(v))
            for h, v in predictions.items()
        ),
    )


def _browse(
    cid: str, predictions: dict[str, str], domain: str = "example.org"
) -> EvidenceCandidate:
    return EvidenceCandidate(
        candidate_id=cid,
        requested_fields=(cid.replace("-", "_"),),
        acquisition_mode=AcquisitionMode.BROWSE,
        subject="daycare_policy",
        allowed_domains=(domain,),
        rationale="r",
        predictions=tuple(
            HypothesisPrediction(hypothesis_id=h, expected=PredictedAnswer(v))
            for h, v in predictions.items()
        ),
    )


def _policy(costs: dict[str, int] | None = None) -> MinimumDataPolicy:
    return MinimumDataPolicy(TableCostModel(costs or {}), browse_allowlist=("example.org",))


def test_information_value_is_ordinal_high_medium_low() -> None:
    _ctx, (h1, h2) = _ctx_with_two_hypotheses()
    policy = _policy()
    live = frozenset({h1, h2})
    assert policy.information_value(_ask("a", {h1: "YES", h2: "NO"}), live) is InformationValue.HIGH
    assert policy.information_value(_ask("b", {h1: "YES"}), live) is InformationValue.MEDIUM
    assert policy.information_value(_ask("c", {h1: "YES", h2: "YES"}), live) is (
        InformationValue.MEDIUM
    )
    assert policy.information_value(_ask("d", {}), live) is InformationValue.LOW


def test_at_most_one_item_is_selected_and_low_value_is_never_asked() -> None:
    ctx, (h1, h2) = _ctx_with_two_hypotheses()
    selection = _policy().select(
        [
            _ask("low", {}, ("x",)),
            _ask("medium", {h1: "YES"}, ("y",)),
            _ask("high", {h1: "YES", h2: "NO"}, ("z",)),
        ],
        ctx,
    )
    assert selection.chosen is not None and selection.chosen.candidate.candidate_id == "high"
    assert ("low", "LOW_VALUE") in selection.excluded


def test_none_is_returned_when_the_investigation_is_sufficient() -> None:
    ctx, _ = _ctx_with_two_hypotheses()
    selection = _policy().select([_ask("low", {}, ("x",))], ctx)
    assert selection.sufficient and selection.chosen is None
    assert _policy().select([], ctx).sufficient


def test_no_numeric_precision_is_emitted() -> None:
    ctx, (h1, h2) = _ctx_with_two_hypotheses()
    selection = _policy({"acquire:BROWSE": 10}).select(
        [_ask("a", {h1: "YES", h2: "NO"}, ("x",)), _browse("b", {h1: "NO"})], ctx
    )

    def walk(value: Any) -> None:
        assert not isinstance(value, float)
        if dataclasses.is_dataclass(value):
            for f in dataclasses.fields(value):
                walk(getattr(value, f.name))
        elif isinstance(value, tuple | list):
            for v in value:
                walk(v)

    walk(selection)
    assert {f.name for f in dataclasses.fields(ScoredCandidate)}.isdisjoint(
        {"expected_information_gain", "probability", "score"}
    )


def test_cost_cannot_outrank_safety() -> None:
    ctx, (h1, h2) = _ctx_with_two_hypotheses()
    cheap_unsafe = _browse("cheap-unsafe", {h1: "YES", h2: "NO"}, domain="tracker.example.net")
    selection = _policy({"acquire:BROWSE": 0, "acquire:ASK_PARENT": 9_999_999}).select(
        [cheap_unsafe, _ask("pricey-safe", {h1: "YES", h2: "NO"}, ("q",))], ctx
    )
    assert selection.chosen is not None
    assert selection.chosen.candidate.candidate_id == "pricey-safe"
    assert ("cheap-unsafe", "UNSAFE") in selection.excluded


def test_a_question_smuggling_an_intervention_is_unsafe() -> None:
    ctx, (h1, h2) = _ctx_with_two_hypotheses()
    smuggled = EvidenceCandidate(
        candidate_id="melatonin",
        requested_fields=("calm_with_melatonin",),
        acquisition_mode=AcquisitionMode.ASK_PARENT,
        question="Could you try giving melatonin tonight and tell me?",
        rationale="r",
        predictions=(
            HypothesisPrediction(hypothesis_id=h1, expected=PredictedAnswer.YES),
            HypothesisPrediction(hypothesis_id=h2, expected=PredictedAnswer.NO),
        ),
    )
    assert _policy().score(smuggled, ctx).safety is AcquisitionSafety.UNSAFE


def test_priority_is_safety_then_need_then_value_then_burden_then_cost() -> None:
    ctx, (h1, h2) = _ctx_with_two_hypotheses()
    policy = _policy({"acquire:BROWSE": 50, "acquire:ASK_PARENT": 0})
    # Equal on safety/need/value: browsing spares the parent, so it wins despite cost.
    ask = _ask("ask", {h1: "YES", h2: "NO"}, ("x",))
    browse = _browse("browse", {h1: "YES", h2: "NO"})
    assert policy.select([ask, browse], ctx).chosen.candidate.candidate_id == "browse"  # type: ignore[union-attr]
    # HIGH value beats a cheaper MEDIUM one.
    medium = _browse("medium", {h1: "YES"})
    assert policy.select([medium, ask], ctx).chosen.candidate.candidate_id == "ask"  # type: ignore[union-attr]
    # Cost only breaks a genuine tie (ids chosen so an id tie-break would pick "aa-dear").
    cheap = _browse("zz-cheap", {h1: "YES", h2: "NO"})
    dear = _browse("aa-dear", {h1: "YES", h2: "NO"})
    tie = _policy({"acquire:BROWSE:zz-cheap": 1, "acquire:BROWSE:aa-dear": 9})
    assert tie.select([dear, cheap], ctx).chosen.candidate.candidate_id == "zz-cheap"  # type: ignore[union-attr]
    # ...and an unknown cost sorts after a known one instead of counting as free.
    unknown = _policy({"acquire:BROWSE:zz-cheap": 1})
    assert unknown.select([dear, cheap], ctx).chosen.candidate.candidate_id == "zz-cheap"  # type: ignore[union-attr]


def test_selection_is_deterministic_and_order_independent() -> None:
    ctx, (h1, h2) = _ctx_with_two_hypotheses()
    items = [
        _ask("b", {h1: "YES", h2: "NO"}, ("x",)),
        _ask("a", {h1: "YES", h2: "NO"}, ("y",)),
        _browse("c", {h1: "YES"}),
    ]
    first = _policy().select(items, ctx)
    second = _policy().select(list(reversed(items)), ctx)
    assert [s.candidate.candidate_id for s in first.ranked] == [
        s.candidate.candidate_id for s in second.ranked
    ]
    assert first.chosen is not None and first.chosen.candidate.candidate_id == "a"


def test_redundant_questions_are_never_asked_twice() -> None:
    rig, inv = run_ask_investigation("redundant")
    state = rig.stack.ledger.replay_events(rig.family.child_id)
    ctx = rig.stack.retriever.retrieve(
        state, child_id=rig.family.child_id, investigation_id=inv, now=rig.family.clock.now()
    )
    hyps = state.investigation_hypotheses[inv]
    again = _ask("again", {hyps[0]: "YES", hyps[1]: "NO"}, ("calm_after_snack",))
    assert ("again", "REDUNDANT_FIELDS") in _policy().select([again], ctx).excluded
