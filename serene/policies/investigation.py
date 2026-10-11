"""Investigation phase state machine and evidence-gated transitions (issue #10).

Branch-A policy, consulted by ledger admission for INVESTIGATION_PHASE_CHANGED:

    UNDERSTANDING -> RETRIEVING_CONTEXT -> FORMING_HYPOTHESES -> NEEDS_EVIDENCE
      -> ASKING_HUMAN | RESEARCHING -> VERIFYING -> EVALUATING
      -> NEEDS_APPROVAL | NEEDS_EVIDENCE | COMPLETE | PARKED_UNRESOLVED

Every phase may park honestly (PARKED_UNRESOLVED). COMPLETE and
PARKED_UNRESOLVED are terminal: a finished investigation never resumes; new
work needs a new investigation. Transitions into evidence-bearing phases are
guarded by ledger facts, so the orchestrator cannot claim progress it lacks.
"""

from __future__ import annotations

from typing import Final

from serene.domain.entities import (
    TERMINAL_INVESTIGATION_PHASES,
    TERMINAL_INVESTIGATION_STATUSES,
    InvestigationPhase,
)
from serene.domain.events import (
    AcquisitionMode,
    HypothesisPrediction,
    InformationValue,
    InvestigationPhaseChanged,
)
from serene.domain.values import VerificationStatus
from serene.policies.decision import PolicyDecision
from serene.projections.state import (
    EvidenceRequestRecord,
    ExperimentStatus,
    KernelState,
    LifecycleStatus,
)

POLICY_VERSION: Final = "investigation-phase/2"
MIN_COMPETING_HYPOTHESES: Final = 2

_P = InvestigationPhase
PHASE_TRANSITIONS: Final[dict[InvestigationPhase, frozenset[InvestigationPhase]]] = {
    _P.UNDERSTANDING: frozenset({_P.RETRIEVING_CONTEXT, _P.PARKED_UNRESOLVED}),
    _P.RETRIEVING_CONTEXT: frozenset({_P.FORMING_HYPOTHESES, _P.PARKED_UNRESOLVED}),
    _P.FORMING_HYPOTHESES: frozenset({_P.NEEDS_EVIDENCE, _P.PARKED_UNRESOLVED}),
    _P.NEEDS_EVIDENCE: frozenset(
        {_P.ASKING_HUMAN, _P.RESEARCHING, _P.EVALUATING, _P.PARKED_UNRESOLVED}
    ),
    _P.ASKING_HUMAN: frozenset({_P.VERIFYING, _P.PARKED_UNRESOLVED}),
    _P.RESEARCHING: frozenset({_P.VERIFYING, _P.NEEDS_EVIDENCE, _P.PARKED_UNRESOLVED}),
    _P.VERIFYING: frozenset({_P.EVALUATING, _P.PARKED_UNRESOLVED}),
    _P.EVALUATING: frozenset(
        {_P.NEEDS_APPROVAL, _P.NEEDS_EVIDENCE, _P.COMPLETE, _P.PARKED_UNRESOLVED}
    ),
    _P.NEEDS_APPROVAL: frozenset({_P.EVALUATING, _P.PARKED_UNRESOLVED}),
    _P.COMPLETE: frozenset(),
    _P.PARKED_UNRESOLVED: frozenset(),
}

# The only phases in which a (model-proposed) hypothesis may enter the ledger:
# forming the competing set, and revising it while evaluating evidence.
HYPOTHESIS_PHASES: Final = frozenset({_P.FORMING_HYPOTHESES, _P.EVALUATING})

_AWAITING_EXPERIMENT = frozenset(
    {
        ExperimentStatus.PROPOSED,
        ExperimentStatus.CLASSIFIED,
        ExperimentStatus.AWAITING_APPROVAL,
    }
)


def active_hypotheses(investigation_id: str, state: KernelState) -> list[str]:
    return [
        hyp_id
        for hyp_id in state.investigation_hypotheses.get(investigation_id, [])
        if state.entities[hyp_id].status is LifecycleStatus.ACTIVE
    ]


def requests_of(investigation_id: str, state: KernelState) -> list[EvidenceRequestRecord]:
    return [
        state.evidence_requests[r] for r in state.investigation_requests.get(investigation_id, [])
    ]


def latest_request(investigation_id: str, state: KernelState) -> EvidenceRequestRecord | None:
    records = requests_of(investigation_id, state)
    return records[-1] if records else None


def pending_evidence(investigation_id: str, state: KernelState) -> list[str]:
    """Evidence acquired for this investigation that the verifier has not yet decided."""
    return [
        evidence_id
        for record in requests_of(investigation_id, state)
        for evidence_id in record.evidence_ids
        if state.verification_of(evidence_id) is VerificationStatus.UNVERIFIED
    ]


def _guard(
    to: InvestigationPhase, frm: InvestigationPhase, inv: str, state: KernelState
) -> list[str]:
    latest = latest_request(inv, state)
    mode = None if latest is None else latest.request.acquisition_mode
    is_open = latest is not None and latest.open
    if (
        to is _P.NEEDS_EVIDENCE
        and frm is _P.FORMING_HYPOTHESES
        and len(active_hypotheses(inv, state)) < MIN_COMPETING_HYPOTHESES
    ):
        return ["INSUFFICIENT_COMPETING_HYPOTHESES"]
    if to is _P.ASKING_HUMAN and not (is_open and mode is AcquisitionMode.ASK_PARENT):
        return ["NO_OPEN_QUESTION"]
    if to is _P.RESEARCHING and not (is_open and mode is AcquisitionMode.BROWSE):
        return ["NO_OPEN_BROWSE_REQUEST"]
    if to is _P.VERIFYING and (latest is None or not latest.answered):
        return ["NO_EVIDENCE_TO_VERIFY"]
    if (
        to is _P.NEEDS_EVIDENCE
        and frm is _P.RESEARCHING
        and (latest is None or not latest.exhausted)
    ):
        return ["ACQUISITION_NOT_EXHAUSTED"]
    if to is _P.EVALUATING and frm is _P.VERIFYING and pending_evidence(inv, state):
        return ["EVIDENCE_PENDING_VERIFICATION"]
    if to is _P.EVALUATING and frm is _P.NEEDS_EVIDENCE and latest is not None and latest.open:
        return ["OPEN_REQUEST_OUTSTANDING"]
    if to is _P.COMPLETE:
        reasons = []
        if not active_hypotheses(inv, state):
            reasons.append("NO_ACTIVE_HYPOTHESIS")
        if pending_evidence(inv, state):
            reasons.append("EVIDENCE_PENDING_VERIFICATION")
        if any(r.open for r in requests_of(inv, state)):
            reasons.append("OPEN_REQUEST_OUTSTANDING")
        return reasons
    if to is _P.NEEDS_APPROVAL:
        waiting = [
            exp_id
            for exp_id, record in state.experiments.items()
            if record.experiment.investigation_id == inv and record.status in _AWAITING_EXPERIMENT
        ]
        if not waiting:
            return ["NO_EXPERIMENT_AWAITING_APPROVAL"]
    return []


def check_phase_transition(
    payload: InvestigationPhaseChanged, state: KernelState
) -> PolicyDecision:
    inv = payload.investigation_id
    current = state.investigation_phases.get(inv)
    if current is None:
        return PolicyDecision.from_reasons(["UNKNOWN_INVESTIGATION"], POLICY_VERSION)
    reasons: list[str] = []
    if current is not payload.from_phase:
        reasons.append(f"STALE_PHASE:{current.value}")
    elif payload.to_phase not in PHASE_TRANSITIONS[current]:
        terminal = current in TERMINAL_INVESTIGATION_PHASES
        reasons.append(
            f"TERMINAL_PHASE:{current.value}"
            if terminal
            else f"ILLEGAL_TRANSITION:{current.value}_TO_{payload.to_phase.value}"
        )
    else:
        reasons += _guard(payload.to_phase, current, inv, state)
    if state.investigations.get(inv) in TERMINAL_INVESTIGATION_STATUSES:
        reasons.append("INVESTIGATION_CLOSED")
    return PolicyDecision.from_reasons(reasons, POLICY_VERSION)


def investigation_accepts_work(investigation_id: str, state: KernelState) -> list[str]:
    """Reasons new evidence requests or hypotheses may not attach to an investigation."""
    phase = state.investigation_phases.get(investigation_id)
    if phase is None:
        return ["UNKNOWN_INVESTIGATION"]
    reasons: list[str] = []
    if phase in TERMINAL_INVESTIGATION_PHASES:
        reasons.append(f"INVESTIGATION_PHASE_TERMINAL:{phase.value}")
    if state.investigations.get(investigation_id) in TERMINAL_INVESTIGATION_STATUSES:
        reasons.append("INVESTIGATION_CLOSED")
    return reasons


def hypothesis_admission(investigation_id: str, state: KernelState) -> list[str]:
    """Reasons a new hypothesis may not attach to an investigation right now.

    Enforced at ledger admission, so a writer that bypasses `InvestigationService`
    still cannot add a hypothesis while the investigation is understanding the
    question, gathering evidence, verifying it, awaiting approval, or finished.
    """
    reasons = investigation_accepts_work(investigation_id, state)
    phase = state.investigation_phases.get(investigation_id)
    terminal = phase in TERMINAL_INVESTIGATION_PHASES  # already reported above
    if phase is not None and not terminal and phase not in HYPOTHESIS_PHASES:
        reasons.append(f"WRONG_PHASE:{phase.value}")
    return reasons


def information_value_of(
    predictions: tuple[HypothesisPrediction, ...], live: frozenset[str]
) -> InformationValue:
    """Ordinal value of a request, from what the live hypotheses predict (no model claim)."""
    expected = {p.expected for p in predictions if p.hypothesis_id in live}
    if len(expected) >= 2:
        return InformationValue.HIGH
    if expected:
        return InformationValue.MEDIUM
    return InformationValue.LOW
