"""Cost is advisory inside a policy-certified evidence equivalence class only.

Inputs are trusted policy results, never planner assertions. The existing
investigation policy still owns domain bounds, verification and authorization.
This module cannot grant any of those permissions.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum

from serene.domain.events import InformationValue
from serene.ports.cost import CostModel
from serene.ports.observability import ObservabilitySink


class AcquisitionSafety(IntEnum):
    SAFE = 0
    NEEDS_REVIEW = 1
    UNSAFE = 2


class EvidenceQuality(IntEnum):
    FIRST_HAND = 0
    AUTHORITATIVE_DOCUMENT = 1
    SECOND_HAND = 2


_VALUE_RANK = {InformationValue.HIGH: 0, InformationValue.MEDIUM: 1, InformationValue.LOW: 2}


@dataclass(frozen=True, slots=True)
class AcquisitionOption:
    option_id: str
    safety: AcquisitionSafety
    quality: EvidenceQuality
    information_value: InformationValue
    policy_eligible: bool = True
    required_parent_question: bool = False
    # Trusted code certifies the SAME observation, evidence requirements and
    # hypothesis predictions. Matching HIGH ordinals alone is insufficient.
    equivalence_key: str | None = None


def _class_key(option: AcquisitionOption) -> tuple[int, int, int, int]:
    return (
        int(option.safety),
        0 if option.required_parent_question else 1,
        int(option.quality),
        _VALUE_RANK[option.information_value],
    )


def _cost_key(cost: int | None) -> tuple[int, int]:
    return (1 if cost is None else 0, 0 if cost is None else cost)


@dataclass(frozen=True, slots=True)
class AcquisitionDecision:
    chosen: str | None
    ranking: tuple[str, ...]
    excluded_unsafe: tuple[str, ...]
    equivalence_class: tuple[str, ...]
    cost_decisive: bool
    costs_micro_usd: tuple[tuple[str, int | None], ...]
    higher_order_tied: bool
    reason_code: str


def decide_acquisition(
    options: Sequence[AcquisitionOption],
    cost_model: CostModel,
    *,
    telemetry: ObservabilitySink | None = None,
) -> AcquisitionDecision:
    """Safety/eligibility first; cost may reorder only the certified top class.

    Snapshot each estimate once. Invalid estimates and provider failures are
    unknown, never zero. Required parent questions disable the cost tie-break.
    """
    if len({o.option_id for o in options}) != len(options):
        raise ValueError("duplicate option identifiers")
    costs: dict[str, int | None] = {}
    for option in options:
        try:
            estimate = cost_model.estimate_cost_micro_usd(option.option_id)
        except Exception:  # an advisory price source cannot change safety policy
            estimate = None
        costs[option.option_id] = estimate if type(estimate) is int and estimate >= 0 else None
    ranking = sorted(
        (o for o in options if o.safety is not AcquisitionSafety.UNSAFE and o.policy_eligible),
        key=lambda o: (*_class_key(o), o.option_id),
    )
    top = [o for o in ranking if _class_key(o) == _class_key(ranking[0])] if ranking else []
    certified = (
        bool(top)
        and bool(top[0].equivalence_key)
        and all(o.equivalence_key == top[0].equivalence_key for o in top)
    )
    tied = len(top) > 1 and certified
    decisive = False
    reason = "NO_ELIGIBLE_OPTION"
    if top:
        if top[0].required_parent_question:
            reason = "REQUIRED_PARENT_QUESTION"
        elif len(top) == 1:
            reason = "HIGHER_ORDER_NOT_TIED"
        elif not certified:
            reason = "EQUIVALENCE_NOT_ESTABLISHED"
        else:
            top.sort(key=lambda o: (*_cost_key(costs[o.option_id]), o.option_id))
            ranking[: len(top)] = top
            decisive = len({_cost_key(costs[o.option_id]) for o in top}) > 1
            if not decisive:
                reason = "STABLE_ID_TIE"
            elif any(costs[o.option_id] is None for o in top):
                reason = "KNOWN_COST_PREFERRED"
            else:
                reason = "LOWER_EXPECTED_COST"
    decision = AcquisitionDecision(
        chosen=ranking[0].option_id if ranking else None,
        ranking=tuple(o.option_id for o in ranking),
        excluded_unsafe=tuple(
            sorted(o.option_id for o in options if o.safety is AcquisitionSafety.UNSAFE)
        ),
        equivalence_class=tuple(o.option_id for o in top) if certified else (),
        cost_decisive=decisive,
        costs_micro_usd=tuple(sorted(costs.items())),
        higher_order_tied=tied,
        reason_code=reason,
    )
    if telemetry is not None:
        # Hash even token-like candidate IDs, which callers might fill with PII.
        # No question, domain, child/family ID or equivalence text is emitted.
        def ref(identifier: str) -> str:
            return "candidate_" + hashlib.sha256(identifier.encode()).hexdigest()[:24]

        for option in sorted(options, key=lambda o: o.option_id):
            cost = costs[option.option_id]
            telemetry.emit(
                "policy.acquisition_cost",
                {
                    "task_id": ref(option.option_id),
                    "decision": "NONE" if decision.chosen is None else ref(decision.chosen),
                    "checks_passed": "SAFETY_ELIGIBILITY_QUALITY_UNCERTAINTY_TIED"
                    if tied and option in top
                    else "NOT_TIED",
                    "admitted": option.policy_eligible,
                    "safety_class": option.safety.name,
                    "source_kind": option.quality.name,
                    "information_value": option.information_value.value,
                    "cost_known": cost is not None,
                    "cost_micro_usd": "UNKNOWN" if cost is None else cost,
                    "status": "SELECTED" if option.option_id == decision.chosen else "NOT_SELECTED",
                    "reason_codes": reason,
                },
            )
    return decision


def rank_acquisition_options(
    options: Sequence[AcquisitionOption], cost_model: CostModel
) -> list[AcquisitionOption]:
    decision = decide_acquisition(options, cost_model)
    by_id = {o.option_id: o for o in options}
    return [by_id[oid] for oid in decision.ranking]
