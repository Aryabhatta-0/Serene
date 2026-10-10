"""Evidence-acquisition ordering with a cost tie-breaker (cfo.ai seam, issue #55).

Order: safety first, then evidence quality, then information value. Cost is
consulted *only* between options that are equal on all three; it can never
promote a less safe or lower-quality option. Costs come from a `CostModel`
port (later backed by the cfo.ai economics model); a missing estimate sorts
last rather than defaulting to "free".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum

from serene.domain.events import InformationValue
from serene.ports.cost import CostModel


class AcquisitionSafety(IntEnum):
    SAFE = 0
    NEEDS_REVIEW = 1
    UNSAFE = 2  # never selected


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


def rank_acquisition_options(
    options: Sequence[AcquisitionOption], cost_model: CostModel
) -> list[AcquisitionOption]:
    """Deterministic ranking. UNSAFE options are dropped, never ranked."""
    eligible = [o for o in options if o.safety is not AcquisitionSafety.UNSAFE]

    def key(option: AcquisitionOption) -> tuple[int, int, int, int, int, str]:
        estimate = cost_model.estimate_cost_micro_usd(option.option_id)
        missing = 1 if estimate is None else 0
        return (
            int(option.safety),
            int(option.quality),
            _VALUE_RANK[option.information_value],
            missing,
            estimate or 0,
            option.option_id,
        )

    return sorted(eligible, key=key)


@dataclass(frozen=True, slots=True)
class AcquisitionDecision:
    """One recorded evidence-acquisition choice and exactly what decided it."""

    chosen: str | None
    ranking: tuple[str, ...]
    excluded_unsafe: tuple[str, ...]
    # Options equal to the chosen one on safety, quality and information value.
    equivalence_class: tuple[str, ...]
    cost_decisive: bool
    costs_micro_usd: tuple[tuple[str, int | None], ...]


def _class_key(option: AcquisitionOption) -> tuple[int, int, int]:
    return (int(option.safety), int(option.quality), _VALUE_RANK[option.information_value])


def decide_acquisition(
    options: Sequence[AcquisitionOption], cost_model: CostModel
) -> AcquisitionDecision:
    """Rank, then record whether cost broke a tie. Cost can only ever decide inside the
    top equivalence class; it never moves an option across safety or quality."""
    ranking = rank_acquisition_options(options, cost_model)
    chosen = ranking[0] if ranking else None
    tie = tuple(o.option_id for o in ranking if chosen and _class_key(o) == _class_key(chosen))
    return AcquisitionDecision(
        chosen=None if chosen is None else chosen.option_id,
        ranking=tuple(o.option_id for o in ranking),
        excluded_unsafe=tuple(
            sorted(o.option_id for o in options if o.safety is AcquisitionSafety.UNSAFE)
        ),
        equivalence_class=tie,
        cost_decisive=len(tie) > 1,
        costs_micro_usd=tuple(
            (o.option_id, cost_model.estimate_cost_micro_usd(o.option_id))
            for o in sorted(options, key=lambda o: o.option_id)
        ),
    )
