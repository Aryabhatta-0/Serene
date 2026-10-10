"""cfo.ai integration seam and Serene unit economics (issue #55).

cfo.ai is a hosted financial-modelling product reached over a remote MCP
server (https://api.cfo.ai/mcp, browser sign-in). Serene's use is narrow:
unit economics for evidence acquisition, consulted *only* to break ties between
options that `serene.policies.acquisition` already ranks equal on safety,
evidence quality and information value.

At runtime the kernel never calls cfo.ai. Engineers maintain the economics model
in cfo.ai (via the MCP server registered in `.mcp.json`) and export per-option
unit costs into a reviewed table; `TableCostModel` serves that table.

`EconomicsModel` mirrors that model's structure in exact integer micro-USD:
LLM / browser / database / memory unit costs, per-family usage, pricing, gross
margin and runway. `SERENE_ECONOMICS_V1` holds the reviewed assumptions; replace
it with the cfo.ai export when one is published (docs/safety.md section 7).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from serene.domain.events import InformationValue
from serene.policies.acquisition import (
    AcquisitionOption,
    AcquisitionSafety,
    EvidenceQuality,
    decide_acquisition,
)


class TableCostModel:
    """`CostModel` backed by a reviewed, exported cost table (integer micro-USD)."""

    def __init__(self, costs: Mapping[str, int]) -> None:
        for option_id, cost in costs.items():
            if cost < 0:
                raise ValueError(f"negative cost for {option_id}")
        self._costs = dict(costs)

    def estimate_cost_micro_usd(self, option_id: str) -> int | None:
        return self._costs.get(option_id)


# ------------------------------------------------------------------ economics model
@dataclass(frozen=True, slots=True)
class UnitCosts:
    """Marginal costs in micro-USD (1 USD = 1_000_000)."""

    llm_per_1k_tokens: int
    browser_session: int
    db_write: int
    db_read: int
    memory_commit: int
    verifier_run: int


@dataclass(frozen=True, slots=True)
class Usage:
    llm_tokens: int = 0
    browser_sessions: int = 0
    db_writes: int = 0
    db_reads: int = 0
    memory_commits: int = 0
    verifier_runs: int = 0

    def cost(self, unit: UnitCosts) -> int:
        return (
            self.llm_tokens * unit.llm_per_1k_tokens // 1000
            + self.browser_sessions * unit.browser_session
            + self.db_writes * unit.db_write
            + self.db_reads * unit.db_read
            + self.memory_commits * unit.memory_commit
            + self.verifier_runs * unit.verifier_run
        )


@dataclass(frozen=True, slots=True)
class FamilyPlan:
    price_per_family_month: int
    base_usage_per_family_month: Usage
    acquisitions_per_family_month: int


@dataclass(frozen=True, slots=True)
class Company:
    families: int
    fixed_costs_month: int
    cash: int


@dataclass(frozen=True, slots=True)
class EconomicsModel:
    version: str
    unit: UnitCosts
    plan: FamilyPlan
    company: Company
    acquisition_usage: Mapping[str, Usage] = field(default_factory=dict)

    def option_cost(self, option_id: str) -> int:
        return self.acquisition_usage[option_id].cost(self.unit)

    def cost_table(self) -> TableCostModel:
        return TableCostModel({oid: self.option_cost(oid) for oid in self.acquisition_usage})

    def cogs_per_family_month(self, acquisition_option: str) -> int:
        base = self.plan.base_usage_per_family_month.cost(self.unit)
        return base + self.plan.acquisitions_per_family_month * self.option_cost(acquisition_option)

    def gross_margin_bps(self, acquisition_option: str) -> int:
        price = self.plan.price_per_family_month
        return (price - self.cogs_per_family_month(acquisition_option)) * 10_000 // price

    def monthly_burn(self, acquisition_option: str) -> int:
        contribution = self.company.families * (
            self.plan.price_per_family_month - self.cogs_per_family_month(acquisition_option)
        )
        return self.company.fixed_costs_month - contribution

    def runway_days(self, acquisition_option: str) -> int | None:
        """Days of cash at the current burn; None when the business is not burning."""
        burn = self.monthly_burn(acquisition_option)
        return None if burn <= 0 else self.company.cash * 30 // burn


SERENE_ECONOMICS_V1: Final = EconomicsModel(
    version="serene-economics/1 (local assumptions; awaiting cfo.ai scenario export)",
    unit=UnitCosts(
        llm_per_1k_tokens=6_000,  # blended input/output, USD 6 per 1M tokens
        browser_session=20_000,
        db_write=2,
        db_read=1,
        memory_commit=50,
        verifier_run=100,
    ),
    plan=FamilyPlan(
        price_per_family_month=12_000_000,
        base_usage_per_family_month=Usage(
            llm_tokens=400_000,
            browser_sessions=6,
            db_writes=3_000,
            db_reads=60_000,
            memory_commits=60,
            verifier_runs=12,
        ),
        acquisitions_per_family_month=12,
    ),
    company=Company(families=400, fixed_costs_month=18_000_000_000, cash=250_000_000_000),
    acquisition_usage={
        "ask_parent_telegram": Usage(llm_tokens=1_500, db_writes=4, db_reads=30),
        "ask_caregiver_telegram": Usage(llm_tokens=2_400, db_writes=6, db_reads=40),
        "browse_daycare_site": Usage(
            llm_tokens=6_000, browser_sessions=1, db_writes=6, db_reads=40, verifier_runs=1
        ),
        "infer_from_history": Usage(llm_tokens=900, db_reads=120),
        "scrape_parent_group_chat": Usage(llm_tokens=800, db_reads=10),
    },
)

# The ONE decision cost is allowed to inform: who to ask to confirm the daycare's
# new pickup cut-off time (an evidence request in the pickup-distress investigation).
PICKUP_CUTOFF_OPTIONS: Final = (
    AcquisitionOption(
        "ask_parent_telegram",
        AcquisitionSafety.SAFE,
        EvidenceQuality.FIRST_HAND,
        InformationValue.HIGH,
    ),
    AcquisitionOption(
        "ask_caregiver_telegram",
        AcquisitionSafety.SAFE,
        EvidenceQuality.FIRST_HAND,
        InformationValue.HIGH,
    ),
    AcquisitionOption(
        "browse_daycare_site",
        AcquisitionSafety.SAFE,
        EvidenceQuality.AUTHORITATIVE_DOCUMENT,
        InformationValue.HIGH,
    ),
    AcquisitionOption(
        "infer_from_history",
        AcquisitionSafety.SAFE,
        EvidenceQuality.SECOND_HAND,
        InformationValue.MEDIUM,
    ),
    AcquisitionOption(
        "scrape_parent_group_chat",
        AcquisitionSafety.UNSAFE,  # third-party private messages: never
        EvidenceQuality.SECOND_HAND,
        InformationValue.HIGH,
    ),
)


def evidence_acquisition_decision(model: EconomicsModel = SERENE_ECONOMICS_V1) -> dict[str, Any]:
    """The persisted, constrained decision (eval/fixtures/cfoai_acquisition_decision.json)."""
    decision = decide_acquisition(PICKUP_CUTOFF_OPTIONS, model.cost_table())
    assert decision.chosen is not None
    alternatives = [o for o in decision.equivalence_class if o != decision.chosen]
    per_option = {
        oid: {
            "cost_micro_usd": model.option_cost(oid),
            "cogs_per_family_month_micro_usd": model.cogs_per_family_month(oid),
            "gross_margin_bps": model.gross_margin_bps(oid),
            "runway_days": model.runway_days(oid),
        }
        for oid in sorted(model.acquisition_usage)
    }
    return {
        "decision": "pickup_cutoff_evidence_source",
        "economics_version": model.version,
        "rule": "safety > evidence quality > information value > cost (tie-break only)",
        "chosen": decision.chosen,
        "ranking": list(decision.ranking),
        "excluded_unsafe": list(decision.excluded_unsafe),
        "equivalence_class": list(decision.equivalence_class),
        "cost_decisive": decision.cost_decisive,
        "cost_decided_between": [decision.chosen, *alternatives],
        "savings_vs_alternative_per_family_month_micro_usd": {
            alt: model.plan.acquisitions_per_family_month
            * (model.option_cost(alt) - model.option_cost(decision.chosen))
            for alt in alternatives
        },
        "options": per_option,
        "plan": {
            "price_per_family_month_micro_usd": model.plan.price_per_family_month,
            "acquisitions_per_family_month": model.plan.acquisitions_per_family_month,
            "families": model.company.families,
            "fixed_costs_month_micro_usd": model.company.fixed_costs_month,
            "cash_micro_usd": model.company.cash,
        },
    }
