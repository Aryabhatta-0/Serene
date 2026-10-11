"""Synthetic budget fixtures only; no provider, account or family data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from scripts.economics_report import report
from serene.adapters.cfoai import TableCostModel, pickup_confirmation_decision
from serene.economics import Assumption, EconomicsInputs, evaluate, sensitivity
from serene.observability.telemetry import RecordingSink, SafeTelemetry

ROOT = Path(__file__).resolve().parents[1]


def fixture() -> dict[str, Any]:
    return json.loads((ROOT / "docs/economics/inputs.json").read_text(encoding="utf-8"))


def model() -> EconomicsInputs:
    return EconomicsInputs.model_validate_json(json.dumps(fixture()["inputs"]))


def test_fixture_arithmetic_monthly_margin_burn_and_runway() -> None:
    result = evaluate(model())
    # Monthly LLM = (400,000 + 12 * 1,500) * 6,000 / 1,000.
    expected = {
        "llm": 2_508_000,
        "browser": 120_000,
        "database_write": 6_096,
        "database_read": 60_360,
        "storage": 20_000,
        "memory_write": 3_000,
        "memory_read": 600,
        "verification": 1_200,
        "telemetry": 6_000,
    }
    assert dict(result.driver_costs_micro_usd) == expected
    assert result.monthly_cost_per_family_micro_usd == 2_725_256 == sum(expected.values())
    assert result.acquisition_cost_micro_usd == 9_038
    assert result.gross_margin_bps == 7_728
    assert result.monthly_variable_cost_micro_usd == 1_090_102_400
    assert result.monthly_revenue_micro_usd == 4_800_000_000
    assert result.monthly_burn_micro_usd == 14_290_102_400
    assert result.runway_days == 524


def test_calculations_and_reviewed_report_are_reproducible() -> None:
    inputs = model()
    assert evaluate(inputs) == evaluate(
        EconomicsInputs.model_validate_json(inputs.model_dump_json())
    )
    assert report() == report()
    persisted = json.loads((ROOT / "docs/economics/local-report.json").read_text(encoding="utf-8"))
    assert persisted == json.loads(json.dumps(report()))


def test_all_inputs_have_explicit_provenance_and_are_assumptions() -> None:
    document = fixture()
    assumptions = (
        *model().assumptions(),
        *(Assumption.model_validate(v) for v in document["caregiver_usage"].values()),
    )
    assert len(assumptions) == 36
    for assumption in assumptions:
        assert assumption.name and assumption.source and assumption.unit
        assert assumption.basis == "assumed"
        assert type(assumption.value) is int


def test_sensitivity_is_reproducible_and_llm_is_major_driver() -> None:
    inputs = model()
    double = sensitivity(inputs, revenue_micro_usd=12_000_000, llm_usage_bps=20_000)
    assert double.monthly_cost_per_family_micro_usd == 5_233_256
    assert double.gross_margin_bps == 5_638
    assert (
        sensitivity(inputs, revenue_micro_usd=8_000_000, llm_usage_bps=10_000).gross_margin_bps
        == 6_593
    )
    assert (
        sensitivity(inputs, revenue_micro_usd=16_000_000, llm_usage_bps=10_000).gross_margin_bps
        == 8_296
    )
    assert max(evaluate(inputs).driver_costs_micro_usd, key=lambda item: item[1])[0] == "llm"
    assert inputs == model()  # sensitivity never mutates baseline


def test_zero_revenue_and_no_burn_are_explicit() -> None:
    inputs = model().model_dump()
    inputs["subscription_per_family_month"]["value"] = 0
    assert evaluate(EconomicsInputs.model_validate(inputs)).gross_margin_bps is None
    inputs["families"]["value"] = 0
    inputs["fixed_cost_per_month"]["value"] = 0
    assert evaluate(EconomicsInputs.model_validate(inputs)).runway_days is None
    inputs["fixed_cost_per_month"]["value"] = 1
    inputs["cash"]["value"] = 0
    assert evaluate(EconomicsInputs.model_validate(inputs)).runway_days == 0


@pytest.mark.parametrize("value", [-1, 0.5, True])
def test_noninteger_or_negative_inputs_are_rejected(value: object) -> None:
    data = model().model_dump()
    data["cash"]["value"] = value
    with pytest.raises(ValidationError):
        EconomicsInputs.model_validate(data)
    with pytest.raises(ValueError):
        TableCostModel({"option": value})  # type: ignore[dict-item]


def test_fractional_micro_usd_rounds_up_and_zero_usage_is_zero() -> None:
    telemetry = next(d for d in model().drivers if d.name == "telemetry")
    assert telemetry.cost(1) == 1
    assert telemetry.cost(0) == 0
    assert telemetry.cost(1_001) == 501
    with pytest.raises(ValueError):
        telemetry.cost(-1)


def test_cfo_synthetic_readback_matches_offline_calculations() -> None:
    captured = json.loads((ROOT / "docs/economics/cfo-readback.json").read_text(encoding="utf-8"))
    assert captured["coverage"]["calculation"] == "complete"
    assert captured["coverage"]["delivery"] == "complete"
    values = {
        row["display_name"].removeprefix("Serene55 "): row["values"][0] for row in captured["rows"]
    }
    result = evaluate(model())
    assert values["cost_per_family_month"] == result.monthly_cost_per_family_micro_usd
    assert values["gross_margin_bps"] == result.gross_margin_bps
    assert values["burn_month"] == result.monthly_burn_micro_usd
    assert values["variable_cost_month"] == result.monthly_variable_cost_micro_usd
    assert values["revenue_month"] == result.monthly_revenue_micro_usd
    assert values["runway_days"] == result.runway_days
    for name, cost in result.driver_costs_micro_usd:
        assert values[name + ".monthly_cost"] == cost
    assert values["parent_acquisition_cost"] == result.acquisition_cost_micro_usd
    choice = report()["decision"]
    assert (
        values["caregiver_acquisition_cost"]
        == dict(choice["costs_micro_usd"])["ask_caregiver_telegram"]
    )
    assert values["monthly_saving"] == model().acquisitions_per_family_month.value * (
        values["caregiver_acquisition_cost"] - values["parent_acquisition_cost"]
    )
    for price, multiplier, name in [
        (8_000_000, 10_000, "low"),
        (16_000_000, 10_000, "high"),
        (12_000_000, 20_000, "double_llm"),
    ]:
        assert (
            values["sensitivity." + name + "_margin_bps"]
            == sensitivity(
                model(), revenue_micro_usd=price, llm_usage_bps=multiplier
            ).gross_margin_bps
        )
    assert (
        values["sensitivity.double_llm_cost"]
        == sensitivity(
            model(), revenue_micro_usd=12_000_000, llm_usage_bps=20_000
        ).monthly_cost_per_family_micro_usd
    )


def test_cfo_request_populates_each_assumption_and_preserves_provenance_hash() -> None:
    import hashlib

    request_bytes = (ROOT / "docs/economics/cfo-model-request.json").read_bytes()
    evidence = json.loads((ROOT / "docs/economics/cfo-evidence.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(request_bytes).hexdigest() == evidence["request_sha256"]
    request = json.loads(request_bytes)
    assert request["arguments"]["scenario"] == evidence["scenario"]["name"]
    formulas = {
        r["variable"].removeprefix("Serene55 "): r["formula"]
        for r in request["arguments"]["create"]["rows"]
    }
    convention_bytes = (ROOT / "docs/economics/cfo-convention-request.json").read_bytes()
    assert hashlib.sha256(convention_bytes).hexdigest() == evidence["convention_request_sha256"]
    convention = json.loads(convention_bytes)
    for entry in convention["arguments"]["update"]["structure"]["insert"]:
        node = entry["node"]
        formulas[node["variable"].removeprefix("Serene55 ")] = node["formula"]
    document = fixture()
    assumptions = (
        *model().assumptions(),
        *(Assumption.model_validate(v) for v in document["caregiver_usage"].values()),
    )
    for assumption in assumptions:
        assert formulas[assumption.name] == str(assumption.value)


def test_one_model_driven_decision_and_required_parent_guard() -> None:
    document = fixture()
    inputs = model()
    caregiver = {k: Assumption.model_validate(v) for k, v in document["caregiver_usage"].items()}
    sink = RecordingSink()
    kwargs: dict[str, Any] = {
        "eligible_options": frozenset({"ask_parent_telegram", "ask_caregiver_telegram"}),
        "required_parent_question": False,
        "telemetry": SafeTelemetry(sink),
    }
    choice = pickup_confirmation_decision(inputs, caregiver, **kwargs)
    assert choice.chosen == "ask_parent_telegram" and choice.cost_decisive
    assert dict(choice.costs_micro_usd) == {
        "ask_parent_telegram": 9_038,
        "ask_caregiver_telegram": 14_452,
    }
    # Make the caregiver free; even that cannot suppress a required parent question.
    cheap = {
        d.name: Assumption(
            name="cheap." + d.name,
            unit="unit/acquisition",
            source="synthetic fixture",
            value=0,
            basis="assumed",
        )
        for d in inputs.drivers
    }
    kwargs["required_parent_question"] = True
    guarded = pickup_confirmation_decision(inputs, cheap, **kwargs)
    assert guarded.chosen == "ask_parent_telegram" and not guarded.cost_decisive
    kwargs["eligible_options"] = frozenset({"ask_caregiver_telegram"})
    assert pickup_confirmation_decision(inputs, cheap, **kwargs).chosen is None
    kwargs["eligible_options"] = frozenset()
    assert pickup_confirmation_decision(inputs, cheap, **kwargs).chosen is None
