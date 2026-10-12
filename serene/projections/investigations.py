"""The `investigations` read projection: what Serene is working on (issue #35).

For each investigation: its question, status and reasoning phase; every
hypothesis (live, refuted or superseded); every evidence request with the
source the minimum-data policy selected, what each live hypothesis predicts,
and how each piece of acquired evidence was verified; the uncertainty that
remains, as explicit facts; and the next action, from
`serene.policies.investigation.next_action`. A pure function of KernelState,
like every projection: no clock, no model, nothing decided here.

Privacy: no evidence content, observation text or actor ids. Hypotheses,
questions and rationales are the investigation's own derived text.
"""

from __future__ import annotations

from typing import Any, Final

from serene.domain.entities import InvestigationPhase
from serene.domain.values import EpistemicLevel, VerificationStatus
from serene.policies.investigation import (
    active_hypotheses,
    next_action,
    pending_evidence,
    requests_of,
)
from serene.projections.state import EvidenceRequestRecord, KernelState

# Facts about what is not yet known, in a fixed order. Never a score.
UNCERTAINTY_ORDER: Final = (
    "NO_LIVE_EXPLANATION",
    "COMPETING_EXPLANATIONS",
    "NOTHING_TESTED",
    "PREDICTIONS_DISAGREE",
    "EVIDENCE_REQUESTED",
    "EVIDENCE_UNVERIFIED",
    "EVIDENCE_REJECTED",
    "ACQUISITION_EXHAUSTED",
    "PARKED_UNRESOLVED",
)


def _request_status(record: EvidenceRequestRecord) -> str:
    if record.answered:
        return "ANSWERED"
    return "EXHAUSTED" if record.exhausted else "OPEN"


def _evidence(evidence_id: str, state: KernelState) -> dict[str, Any]:
    record = state.entities[evidence_id]
    entity = record.entity
    return {
        "evidence_id": evidence_id,
        "kind": entity.kind.value,
        "source_kind": entity.source.kind.value,
        "verification_status": record.verification_status.value,
        "checks_passed": list(state.evidence_checks.get(evidence_id, ())),
        "rejection_reason_codes": list(state.evidence_rejections.get(evidence_id, ())),
    }


def _uncertainty(inv: str, state: KernelState, live: list[str]) -> list[str]:
    facts: set[str] = set()
    if not live:
        facts.add("NO_LIVE_EXPLANATION")
    if len(live) >= 2:
        facts.add("COMPETING_EXPLANATIONS")
    if not any(
        (state.hypothesis_levels.get(h) or EpistemicLevel.HYPOTHESIS)
        >= EpistemicLevel.TESTED_HYPOTHESIS
        for h in live
    ):
        facts.add("NOTHING_TESTED")
    for record in requests_of(inv, state):
        if record.open:
            facts.add("EVIDENCE_REQUESTED")
            expected = {
                p.expected for p in record.request.predictions if p.hypothesis_id in set(live)
            }
            if len(expected) >= 2:
                facts.add("PREDICTIONS_DISAGREE")
        if record.exhausted and not record.answered:
            facts.add("ACQUISITION_EXHAUSTED")
        for evidence_id in record.evidence_ids:
            if state.verification_of(evidence_id) is VerificationStatus.REJECTED:
                facts.add("EVIDENCE_REJECTED")
    if pending_evidence(inv, state):
        facts.add("EVIDENCE_UNVERIFIED")
    if state.investigation_phases[inv] is InvestigationPhase.PARKED_UNRESOLVED:
        facts.add("PARKED_UNRESOLVED")
    return [f for f in UNCERTAINTY_ORDER if f in facts]


def _investigation(inv: str, state: KernelState) -> dict[str, Any]:
    investigation = state.entities[inv].entity
    live = active_hypotheses(inv, state)
    hypotheses = []
    for hyp_id in state.investigation_hypotheses.get(inv, []):
        record = state.entities[hyp_id]
        hyp = record.entity
        level = state.hypothesis_levels.get(hyp_id)
        hypotheses.append(
            {
                "hypothesis_id": hyp_id,
                "statement": hyp.statement,
                "level": None if level is None else level.name,
                "status": record.status.value,
                "superseded_by": record.superseded_by,
                "competing_hypothesis_ids": list(hyp.competing_hypothesis_ids),
                "falsification_criteria": list(hyp.falsification_criteria),
                "known_confounders": list(hyp.known_confounders),
                "alternative_explanations": list(hyp.alternative_explanations),
            }
        )
    requests = []
    for req in requests_of(inv, state):
        request = req.request
        requests.append(
            {
                "request_id": request.request_id,
                "status": _request_status(req),
                "requested_fields": list(request.requested_fields),
                "acquisition_mode": (
                    None if request.acquisition_mode is None else request.acquisition_mode.value
                ),
                "question": request.question,
                "subject": request.subject,
                "allowed_domains": list(request.allowed_domains),
                "information_value": request.information_value.value,
                "rationale": request.rationale,
                "predictions": [
                    {
                        "hypothesis_id": p.hypothesis_id,
                        "expected": p.expected.value,
                        "live": p.hypothesis_id in live,
                    }
                    for p in request.predictions
                ],
                "failed_attempts": req.failed_attempts,
                "evidence": [_evidence(e, state) for e in req.evidence_ids],
            }
        )
    action = next_action(inv, state)
    return {
        "question": investigation.question,
        "status": state.investigations[inv].value,
        "phase": state.investigation_phases[inv].value,
        "opened_at": investigation.opened_at,
        "phase_reason_codes": list(state.investigation_phase_reasons.get(inv, ())),
        "hypotheses": hypotheses,
        "evidence_requests": requests,
        "uncertainty": _uncertainty(inv, state, live),
        "next_action": {
            "kind": action.kind.value,
            "phase": action.phase.value,
            "request_id": action.request_id,
            "acquisition_mode": (
                None if action.acquisition_mode is None else action.acquisition_mode.value
            ),
            "question": action.question,
            "subject": action.subject,
            "allowed_domains": list(action.allowed_domains),
            "evidence_ids": list(action.evidence_ids),
            "experiment_ids": list(action.experiment_ids),
            "reason_codes": list(action.reason_codes),
        },
    }


def investigations(state: KernelState) -> dict[str, Any]:
    return {inv: _investigation(inv, state) for inv in sorted(state.investigations)}


__all__ = ["UNCERTAINTY_ORDER", "investigations"]
