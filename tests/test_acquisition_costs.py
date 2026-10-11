"""cfo.ai seam: cost breaks ties only, never overrides safety or quality (issue #55)."""

from __future__ import annotations

from dataclasses import replace
from itertools import permutations

import pytest

from serene.adapters.cfoai import TableCostModel
from serene.domain.events import InformationValue
from serene.observability.telemetry import RecordingSink, SafeTelemetry
from serene.policies.acquisition import (
    AcquisitionOption,
    AcquisitionSafety,
    EvidenceQuality,
    decide_acquisition,
    rank_acquisition_options,
)

HIGH = InformationValue.HIGH


def _opt(oid: str, safety: AcquisitionSafety, quality: EvidenceQuality) -> AcquisitionOption:
    return AcquisitionOption(
        oid, safety, quality, HIGH, equivalence_key="synthetic_same_observation"
    )


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


def test_cost_cannot_override_greater_uncertainty_reduction() -> None:
    high = _opt("z_high", AcquisitionSafety.SAFE, EvidenceQuality.FIRST_HAND)
    medium = replace(high, option_id="a_medium", information_value=InformationValue.MEDIUM)
    assert (
        decide_acquisition([medium, high], TableCostModel({"a_medium": 0, "z_high": 10**15})).chosen
        == "z_high"
    )


def test_policy_denial_and_required_parent_question_dominate_cost() -> None:
    parent = _opt("parent", AcquisitionSafety.SAFE, EvidenceQuality.FIRST_HAND)
    blocked = replace(parent, option_id="blocked", policy_eligible=False)
    denied = replace(parent, option_id="unsafe", safety=AcquisitionSafety.UNSAFE)
    costs = TableCostModel({"parent": 10**15, "blocked": 0, "unsafe": 0})
    assert decide_acquisition([blocked, denied, parent], costs).chosen == "parent"
    assert decide_acquisition([blocked, denied], costs).chosen is None
    caregiver = replace(parent, option_id="caregiver")
    required = replace(parent, required_parent_question=True)
    choice = decide_acquisition(
        [caregiver, required], TableCostModel({"caregiver": 0, "parent": 10**15})
    )
    assert choice.chosen == "parent"
    assert not choice.cost_decisive and choice.reason_code == "REQUIRED_PARENT_QUESTION"


@pytest.mark.parametrize("key", [None, "", "different_observation"])
def test_equal_ordinals_without_certified_equivalence_ignore_cost(key: str | None) -> None:
    expensive = _opt("a_expensive", AcquisitionSafety.SAFE, EvidenceQuality.FIRST_HAND)
    cheap = replace(expensive, option_id="z_cheap", equivalence_key=key)
    decision = decide_acquisition(
        [cheap, expensive], TableCostModel({"a_expensive": 100, "z_cheap": 0})
    )
    assert decision.chosen == "a_expensive" and not decision.cost_decisive
    assert decision.reason_code == "EQUIVALENCE_NOT_ESTABLISHED"


def test_equal_or_unknown_prices_are_not_reported_as_cost_decisive() -> None:
    a = _opt("a", AcquisitionSafety.SAFE, EvidenceQuality.FIRST_HAND)
    b = replace(a, option_id="b")
    for table in (TableCostModel({}), TableCostModel({"a": 5, "b": 5})):
        for order in permutations([a, b]):
            decision = decide_acquisition(order, table)
            assert decision.chosen == "a"
            assert not decision.cost_decisive and decision.reason_code == "STABLE_ID_TIE"


def test_estimates_are_snapshotted_once_and_failures_are_unknown() -> None:
    class Costs:
        def __init__(self) -> None:
            self.seen: list[str] = []

        def estimate_cost_micro_usd(self, option_id: str) -> int | None:
            self.seen.append(option_id)
            if option_id == "a":
                raise RuntimeError("synthetic failure")
            return 999

    a = _opt("a", AcquisitionSafety.SAFE, EvidenceQuality.FIRST_HAND)
    b = replace(a, option_id="b")
    costs = Costs()
    decision = decide_acquisition([a, b], costs)
    assert costs.seen == ["a", "b"]
    assert decision.chosen == "b" and dict(decision.costs_micro_usd)["a"] is None


def test_trace_has_tie_cost_status_selection_and_reason_without_pii() -> None:
    a = _opt("synthetic-person-name", AcquisitionSafety.SAFE, EvidenceQuality.FIRST_HAND)
    b = replace(a, option_id="other-synthetic-person")
    sink = RecordingSink()
    decision = decide_acquisition(
        [a, b], TableCostModel({b.option_id: 123}), telemetry=SafeTelemetry(sink)
    )
    assert len(sink.records) == 2
    for name, attrs in sink.records:
        assert name == "policy.acquisition_cost"
        assert attrs["checks_passed"] == "SAFETY_ELIGIBILITY_QUALITY_UNCERTAINTY_TIED"
        assert str(attrs["task_id"]).startswith("candidate_")
        assert attrs["reason_codes"] == "KNOWN_COST_PREFERRED"
        assert attrs["cost_micro_usd"] in {123, "UNKNOWN"}
        assert (attrs["cost_known"] is True) == (attrs["cost_micro_usd"] == 123)
        assert "synthetic-person" not in str(attrs)
    selected = next(attrs for _, attrs in sink.records if attrs["status"] == "SELECTED")
    assert selected["task_id"] == selected["decision"]
    assert decision.chosen == b.option_id


def test_telemetry_failure_does_not_change_selection() -> None:
    class BrokenSink:
        def emit(self, name: str, attributes: object) -> None:
            raise RuntimeError("synthetic sink failure")

    options = [_opt("a", AcquisitionSafety.SAFE, EvidenceQuality.FIRST_HAND)]
    costs = TableCostModel({"a": 1})
    assert decide_acquisition(
        options, costs, telemetry=SafeTelemetry(BrokenSink())
    ) == decide_acquisition(options, costs)
