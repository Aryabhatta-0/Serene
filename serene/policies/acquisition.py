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
