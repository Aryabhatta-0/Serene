"""GREEN / AMBER / RED intervention classification (issues #22, #23).

Deterministic and fail-closed:
- forbidden categories, forbidden terms, a child left unsupervised in a
  vehicle, irreversibility, excessive duration and anything unclassifiable
  are RED, whatever category the model chose;
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

# Supervision hazard: a child left without an adult in a vehicle. Matched per
# sentence as a co-occurrence of an unsupervised phrase and a vehicle, so the
# model's category, burden or reversibility can never hide it, while a sentence
# that merely mentions a car ("a heads-up in the car") is untouched.
_UNSUPERVISED: Final = re.compile(
    r"\b(alone|unattended|unsupervised|unaccompanied|unwatched|solo|"
    r"by\s+(?:them|him|her|it)sel(?:f|ves)|on\s+(?:their|his|her|its)\s+own|"
    r"without\s+(?:a\s+|an\s+|any\s+)?(?:adult|grown[\s-]?up|parent|caregiver|supervision)|"
    r"(?:no\s*one|nobody)\s+(?:with|watching|supervising))\b",
    re.IGNORECASE,
)
_VEHICLE: Final = (
    r"(?<!toy\s)(?<!toy-)\b(?:cars?|vehicles?|vans?|minivans?|trucks?|suvs?|automobiles?|"
    r"back\s*seat)\b"
)
# Unattended even without the word "alone": "leave the child in the parked car".
_LEFT_IN_VEHICLE: Final = re.compile(
    r"\b(?:leave|leaves|leaving|left)\s+(?:\w+\s+){0,3}?(?:in|inside)\s+"
    r"(?:the\s+|a\s+|their\s+|our\s+|his\s+|her\s+)?(?:parked\s+|locked\s+)?" + _VEHICLE,
    re.IGNORECASE,
)
_IN_VEHICLE: Final = re.compile(_VEHICLE, re.IGNORECASE)
_SENTENCE: Final = re.compile(r"[.;!?\n]+")


def supervision_hazards(text: str) -> tuple[str, ...]:
    """RED reason codes for a child left unsupervised in a vehicle. Pure and deterministic."""
    for sentence in _SENTENCE.split(text):
        if _LEFT_IN_VEHICLE.search(sentence) or (
            _IN_VEHICLE.search(sentence) and _UNSUPERVISED.search(sentence)
        ):
            return ("UNSUPERVISED_IN_VEHICLE",)
    return ()


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
    red += supervision_hazards(intervention.description)
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
