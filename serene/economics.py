"""Offline, exact unit economics. No network, planner or runtime authority."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, Self

from pydantic import Field, model_validator

from serene.domain.base import KernelModel


class Assumption(KernelModel):
    name: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    source: str = Field(min_length=1)
    value: int = Field(ge=0)
    basis: Literal["measured", "assumed"]


class CostDriver(KernelModel):
    name: str
    rate: Assumption
    base_units_per_family_month: Assumption
    units_per_acquisition: Assumption
    # E.g. a token rate quoted per 1,000 tokens. This is a unit conversion,
    # not a price or usage assumption.
    rate_per_units: int = Field(default=1, ge=1)

    def cost(self, units: int) -> int:
        """Round fractional micro-USD up; never silently underprice tiny requests."""
        if type(units) is not int or units < 0:
            raise ValueError("usage must be a nonnegative integer")
        return (units * self.rate.value + self.rate_per_units - 1) // self.rate_per_units


class EconomicsInputs(KernelModel):
    version: str
    drivers: tuple[CostDriver, ...] = Field(min_length=1)
    acquisitions_per_family_month: Assumption
    subscription_per_family_month: Assumption
    families: Assumption
    fixed_cost_per_month: Assumption
    cash: Assumption
    days_per_month: Assumption

    def assumptions(self) -> tuple[Assumption, ...]:
        return (
            *(
                a
                for d in self.drivers
                for a in (d.rate, d.base_units_per_family_month, d.units_per_acquisition)
            ),
            self.acquisitions_per_family_month,
            self.subscription_per_family_month,
            self.families,
            self.fixed_cost_per_month,
            self.cash,
            self.days_per_month,
        )

    @model_validator(mode="after")
    def _unique(self) -> Self:
        names = [a.name for a in self.assumptions()]
        if len(names) != len(set(names)):
            raise ValueError("assumption names must be unique")
        drivers = [d.name for d in self.drivers]
        if len(drivers) != len(set(drivers)):
            raise ValueError("driver names must be unique")
        return self


class EconomicsResult(KernelModel):
    version: str
    driver_costs_micro_usd: tuple[tuple[str, int], ...]
    acquisition_cost_micro_usd: int
    monthly_cost_per_family_micro_usd: int
    subscription_per_family_month_micro_usd: int
    gross_margin_bps: int | None
    monthly_variable_cost_micro_usd: int
    monthly_revenue_micro_usd: int
    monthly_burn_micro_usd: int
    runway_days: int | None


def evaluate(inputs: EconomicsInputs) -> EconomicsResult:
    """All calculations use integers. Zero revenue has undefined margin.

    Monthly usage = base usage + acquisitions * incremental acquisition usage.
    Margin is floored in basis points; runway uses the explicit days/month input.
    A nonpositive burn has no finite runway (None).
    """
    costs = tuple(
        (
            d.name,
            d.cost(
                d.base_units_per_family_month.value
                + inputs.acquisitions_per_family_month.value * d.units_per_acquisition.value
            ),
        )
        for d in inputs.drivers
    )
    cogs = sum(cost for _, cost in costs)
    revenue = inputs.subscription_per_family_month.value
    variable = inputs.families.value * cogs
    total_revenue = inputs.families.value * revenue
    burn = inputs.fixed_cost_per_month.value + variable - total_revenue
    return EconomicsResult(
        version=inputs.version,
        driver_costs_micro_usd=costs,
        acquisition_cost_micro_usd=sum(
            d.cost(d.units_per_acquisition.value) for d in inputs.drivers
        ),
        monthly_cost_per_family_micro_usd=cogs,
        subscription_per_family_month_micro_usd=revenue,
        gross_margin_bps=None if revenue == 0 else (revenue - cogs) * 10_000 // revenue,
        monthly_variable_cost_micro_usd=variable,
        monthly_revenue_micro_usd=total_revenue,
        monthly_burn_micro_usd=burn,
        runway_days=None if burn <= 0 else inputs.cash.value * inputs.days_per_month.value // burn,
    )


def sensitivity(
    inputs: EconomicsInputs, *, revenue_micro_usd: int, llm_usage_bps: int
) -> EconomicsResult:
    """One-factor inputs for scenario review, never policy configuration."""
    if type(revenue_micro_usd) is not int or revenue_micro_usd < 0:
        raise ValueError("revenue must be a nonnegative integer")
    if type(llm_usage_bps) is not int or llm_usage_bps < 0:
        raise ValueError("usage multiplier must be a nonnegative integer")
    data = inputs.model_dump()
    data["subscription_per_family_month"]["value"] = revenue_micro_usd
    data["subscription_per_family_month"]["basis"] = "assumed"
    data["subscription_per_family_month"]["source"] = "sensitivity assumption"
    for driver in data["drivers"]:
        if driver["name"] == "llm":
            for key in ("base_units_per_family_month", "units_per_acquisition"):
                driver[key]["value"] = (driver[key]["value"] * llm_usage_bps + 9_999) // 10_000
                driver[key]["basis"] = "assumed"
                driver[key]["source"] = "sensitivity assumption"
    return evaluate(EconomicsInputs.model_validate(data))


class ReviewedCostTable:
    """Reviewed integer estimates; cfo.ai output cannot modify policy criteria."""

    def __init__(self, costs: Mapping[str, int]) -> None:
        if any(type(v) is not int or v < 0 for v in costs.values()):
            raise ValueError("costs must be nonnegative integer micro-USD")
        self._costs = dict(costs)

    def estimate_cost_micro_usd(self, option_id: str) -> int | None:
        return self._costs.get(option_id)
