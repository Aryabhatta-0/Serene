"""GREEN / AMBER / RED intervention classification (issues #22, #23).

Deterministic and fail-closed:
- forbidden categories, forbidden terms, irreversibility, excessive duration
  and anything unclassifiable are RED;
- RED never enters experimentation, regardless of approvals or model output;
- lexical screening can only *escalate* a class, never lower it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from serene.domain.canonical import canonical_digest
from serene.domain.entities import Burden, Intervention, InterventionCategory
from serene.domain.events import SafetyClass

POLICY_VERSION: Final = "safety/1"

_C = InterventionCategory

FORBIDDEN_CATEGORIES: Final = frozenset(
    {
        _C.MEDICATION,
        _C.SUPPLEMENT,
        _C.ALLERGEN_EXPOSURE,
        _C.SYMPTOM_TREATMENT,
        _C.RESTRAINT,
        _C.PUNISHMENT,
        _C.DANGEROUS_ACTIVITY,
        _C.FOOD_DEPRIVATION,
        _C.SLEEP_DEPRIVATION,
    }
)
AMBER_CATEGORIES: Final = frozenset(
    {_C.CAREGIVER_COORDINATION, _C.SLEEP_SCHEDULE, _C.MEAL_TIMING, _C.SCREEN_TIME}
)
GREEN_CANDIDATE_CATEGORIES: Final = frozenset(
    {_C.ROUTINE_TIMING, _C.ENVIRONMENT, _C.TRANSITION_SUPPORT, _C.COMMUNICATION, _C.PLAY_ACTIVITY}
)

MAX_GREEN_DAYS: Final = 14
MAX_EXPERIMENT_DAYS: Final = 28

# Term screen over free text. Matching escalates to RED; absence proves nothing.
_FORBIDDEN_TERMS: Final = re.compile(
    r"\b(medic\w*|dose|dosage|drug\w*|pill\w*|ibuprofen|paracetamol|acetaminophen|"
    r"tylenol|melatonin|antihistamine\w*|supplement\w*|vitamin\w*|cbd|allerg\w*|epipen|"
    r"peanut\w*|restrain\w*|tie\s+down|hold\s+down|punish\w*|spank\w*|smack\w*|hit|"
    r"withhold\w*\s+food|no\s+(dinner|lunch|breakfast|food)|skip\w*\s+meals?|fasting|"
    r"depriv\w*|keep\s+awake|no\s+sleep|stay\s+up\s+all\s+night)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    safety_class: SafetyClass
    reason_codes: tuple[str, ...]
    policy_version: str = POLICY_VERSION


def intervention_digest(intervention: Intervention) -> str:
    return canonical_digest(intervention)


def classify_intervention(intervention: Intervention) -> SafetyDecision:
    red: list[str] = []
    amber: list[str] = []
    category = intervention.category

    if category in FORBIDDEN_CATEGORIES:
        red.append(f"FORBIDDEN_CATEGORY:{category.value}")
    elif category not in AMBER_CATEGORIES | GREEN_CANDIDATE_CATEGORIES:
        red.append(f"UNCLASSIFIABLE:{category.value}")

    term = _FORBIDDEN_TERMS.search(intervention.description)
    if term is not None:
        red.append("FORBIDDEN_TERM")
    if not intervention.reversible:
        red.append("IRREVERSIBLE")
    if intervention.max_duration_days > MAX_EXPERIMENT_DAYS:
        red.append("EXCEEDS_MAX_DURATION")

    if red:
        return SafetyDecision(SafetyClass.RED, tuple(red))

    if category in AMBER_CATEGORIES:
        amber.append(f"ESCALATED_CATEGORY:{category.value}")
    if intervention.burden is not Burden.LOW:
        amber.append(f"BURDEN:{intervention.burden.value}")
    if intervention.max_duration_days > MAX_GREEN_DAYS:
        amber.append("EXTENDED_DURATION")
    if amber:
        return SafetyDecision(SafetyClass.AMBER, tuple(amber))
    return SafetyDecision(SafetyClass.GREEN, ("LOW_RISK_REVERSIBLE",))
