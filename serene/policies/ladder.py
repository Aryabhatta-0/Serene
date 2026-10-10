"""The explicit epistemic transition table (issues #17, #18).

Every legal move on the ladder is listed here exactly once, with the mechanism
that performs it and the only ledger events that may record it. Anything not in
this table - skipping a rung, moving down, re-entering a rung - is illegal, so
the Promotion Gate can reject it before looking at any evidence.

    0 RAW_EVIDENCE -> 1 OBSERVATION -> 2 PATTERN -> 3 HYPOTHESIS
      -> 4 TESTED_HYPOTHESIS -> 5 CONTEXTUAL_LEARNING
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from serene.domain.events import EventType
from serene.domain.values import EpistemicLevel

_L = EpistemicLevel


class TransitionMechanism(StrEnum):
    # A new entity enters one rung above its parents (check_introduction).
    INTRODUCTION = "INTRODUCTION"
    # An existing hypothesis moves one rung (evaluate_promotion, then check_learning for 5).
    PROMOTION = "PROMOTION"


@dataclass(frozen=True, slots=True)
class LadderTransition:
    from_level: EpistemicLevel
    to_level: EpistemicLevel
    mechanism: TransitionMechanism
    # Ledger events that may record this transition, in order.
    recorded_by: tuple[EventType, ...]
    # Machine-readable prerequisites, documented in docs/epistemic-model.md.
    requires: tuple[str, ...]


TRANSITIONS: Final[dict[tuple[EpistemicLevel, EpistemicLevel], LadderTransition]] = {
    (t.from_level, t.to_level): t
    for t in (
        LadderTransition(
            _L.RAW_EVIDENCE,
            _L.OBSERVATION,
            TransitionMechanism.INTRODUCTION,
            (EventType.OBSERVATION_STRUCTURED,),
            ("PARENTS_AT_RAW_EVIDENCE", "EVIDENCE_VERIFIED"),
        ),
        LadderTransition(
            _L.OBSERVATION,
            _L.PATTERN,
            TransitionMechanism.INTRODUCTION,
            (EventType.PATTERN_PROPOSED,),
            ("PARENTS_AT_OBSERVATION", "TWO_DISTINCT_OCCASIONS"),
        ),
        LadderTransition(
            _L.PATTERN,
            _L.HYPOTHESIS,
            TransitionMechanism.INTRODUCTION,
            (EventType.HYPOTHESIS_PROPOSED,),
            ("PARENTS_AT_PATTERN", "ALTERNATIVES_CONSIDERED", "FALSIFIABLE", "OPEN_INVESTIGATION"),
        ),
        LadderTransition(
            _L.HYPOTHESIS,
            _L.TESTED_HYPOTHESIS,
            TransitionMechanism.PROMOTION,
            (EventType.PROMOTION_GRANTED,),
            (
                "COMPLETE_VERIFIED_LINEAGE",
                "APPROVED_COMPLETED_NON_RED_EXPERIMENT",
                "SUPPORTING_OUTCOME",
                "NO_CONTRADICTING_OUTCOME",
            ),
        ),
        LadderTransition(
            _L.TESTED_HYPOTHESIS,
            _L.CONTEXTUAL_LEARNING,
            TransitionMechanism.PROMOTION,
            (EventType.PROMOTION_GRANTED, EventType.LEARNING_RECORDED),
            (
                "COMPLETE_VERIFIED_LINEAGE",
                "NO_CONTRADICTING_OUTCOME",
                "CONFOUNDERS_CONSIDERED",
                "NO_UNRESOLVED_COMPETITOR",
                "SCOPE_WITHIN_TESTED_CONTEXTS",
                "VALIDITY_AND_REVIEW_METADATA",
            ),
        ),
    )
}


def transition_violation(from_level: EpistemicLevel, to_level: EpistemicLevel) -> str | None:
    """Why (from, to) is not a legal single move, or None if the table lists it."""
    if (from_level, to_level) in TRANSITIONS:
        return None
    return "LEVEL_SKIP" if to_level > from_level else "NOT_A_PROMOTION"


def promotion_violation(from_level: EpistemicLevel, to_level: EpistemicLevel) -> str | None:
    """Like `transition_violation`, but only PROMOTION-mechanism moves are acceptable."""
    reason = transition_violation(from_level, to_level)
    if reason is not None:
        return reason
    if TRANSITIONS[(from_level, to_level)].mechanism is not TransitionMechanism.PROMOTION:
        return "PROMOTION_VIA_INTRODUCTION_ONLY"
    return None
