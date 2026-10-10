"""cfo.ai seam: cost breaks ties only, never overrides safety or quality (issue #55)."""

from __future__ import annotations

from serene.adapters.cfoai import TableCostModel
from serene.domain.events import InformationValue
from serene.policies.acquisition import (
    AcquisitionOption,
    AcquisitionSafety,
    EvidenceQuality,
    rank_acquisition_options,
)

HIGH = InformationValue.HIGH


def _opt(oid: str, safety: AcquisitionSafety, quality: EvidenceQuality) -> AcquisitionOption:
    return AcquisitionOption(oid, safety, quality, HIGH)


def test_cost_cannot_override_safety() -> None:
    options = [
        _opt("cheap_needs_review", AcquisitionSafety.NEEDS_REVIEW, EvidenceQuality.FIRST_HAND),
        _opt("pricey_safe", AcquisitionSafety.SAFE, EvidenceQuality.FIRST_HAND),
    ]
    costs = TableCostModel({"cheap_needs_review": 1, "pricey_safe": 9_000_000})
    assert next(o.option_id for o in rank_acquisition_options(options, costs)) == "pricey_safe"


def test_cost_cannot_override_quality() -> None:
    options = [
        _opt("cheap_hearsay", AcquisitionSafety.SAFE, EvidenceQuality.SECOND_HAND),
        _opt("pricey_first_hand", AcquisitionSafety.SAFE, EvidenceQuality.FIRST_HAND),
    ]
    costs = TableCostModel({"cheap_hearsay": 1, "pricey_first_hand": 9_000_000})
    assert rank_acquisition_options(options, costs)[0].option_id == "pricey_first_hand"


def test_cost_decides_only_between_equivalent_options() -> None:
    options = [
        _opt("ask_caregiver", AcquisitionSafety.SAFE, EvidenceQuality.FIRST_HAND),
        _opt("ask_parent", AcquisitionSafety.SAFE, EvidenceQuality.FIRST_HAND),
    ]
    costs = TableCostModel({"ask_caregiver": 3_000, "ask_parent": 1_000})
    assert [o.option_id for o in rank_acquisition_options(options, costs)] == [
        "ask_parent",
        "ask_caregiver",
    ]


def test_unsafe_options_are_never_ranked_and_unknown_cost_sorts_last() -> None:
    options = [
        _opt("unsafe", AcquisitionSafety.UNSAFE, EvidenceQuality.FIRST_HAND),
        _opt("unknown_cost", AcquisitionSafety.SAFE, EvidenceQuality.FIRST_HAND),
        _opt("known_cost", AcquisitionSafety.SAFE, EvidenceQuality.FIRST_HAND),
    ]
    ranked = rank_acquisition_options(options, TableCostModel({"known_cost": 10**9}))
    assert [o.option_id for o in ranked] == ["known_cost", "unknown_cost"]
