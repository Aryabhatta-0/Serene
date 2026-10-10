"""cfo.ai unit economics and the one cost-constrained decision (issue #55)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from serene.adapters.cfoai import (
    PICKUP_CUTOFF_OPTIONS,
    SERENE_ECONOMICS_V1,
    Company,
    TableCostModel,
    Usage,
    evidence_acquisition_decision,
)
from serene.policies.acquisition import decide_acquisition

ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "eval" / "fixtures" / "cfoai_acquisition_decision.json"
M = SERENE_ECONOMICS_V1


def test_unit_costs_cover_llm_browser_database_memory_and_verification() -> None:
    usage = Usage(
        llm_tokens=2_000,
        browser_sessions=1,
        db_writes=10,
        db_reads=100,
        memory_commits=2,
        verifier_runs=3,
    )
    assert usage.cost(M.unit) == 12_000 + 20_000 + 20 + 100 + 100 + 300


def test_family_cogs_margin_and_runway_fixture() -> None:
    assert M.option_cost("ask_parent_telegram") == 9_038
    assert M.plan.base_usage_per_family_month.cost(M.unit) == 2_590_200
    assert M.cogs_per_family_month("ask_parent_telegram") == 2_590_200 + 12 * 9_038
    assert M.gross_margin_bps("ask_parent_telegram") == 7_751
    assert M.monthly_burn("ask_parent_telegram") == 18_000_000_000 - 400 * (12_000_000 - 2_698_656)
    assert M.runway_days("ask_parent_telegram") == 525
    profitable = dataclasses.replace(
        M, company=Company(families=5_000, fixed_costs_month=1, cash=1)
    )
    assert profitable.runway_days("ask_parent_telegram") is None


def test_persisted_decision_matches_the_model() -> None:
    persisted = json.loads(DECISION.read_text(encoding="utf-8"))
    assert persisted == json.loads(json.dumps(evidence_acquisition_decision()))
    assert persisted["chosen"] == "ask_parent_telegram"
    assert persisted["cost_decisive"] is True
    assert persisted["equivalence_class"] == ["ask_parent_telegram", "ask_caregiver_telegram"]
    assert persisted["excluded_unsafe"] == ["scrape_parent_group_chat"]


def _cost(**overrides: int) -> TableCostModel:
    costs = {oid: M.option_cost(oid) for oid in M.acquisition_usage}
    costs.update(overrides)
    return TableCostModel(costs)


@pytest.mark.parametrize(
    "cheap", ["scrape_parent_group_chat", "infer_from_history", "browse_daycare_site"]
)
def test_no_price_lets_a_less_safe_or_lower_quality_option_win(cheap: str) -> None:
    others = {oid: 10**9 for oid in M.acquisition_usage if oid != cheap}
    decision = decide_acquisition(PICKUP_CUTOFF_OPTIONS, _cost(**others, **{cheap: 0}))
    assert decision.chosen in {"ask_parent_telegram", "ask_caregiver_telegram"}
    assert "scrape_parent_group_chat" not in decision.ranking


def test_cost_decides_only_inside_the_equivalence_class() -> None:
    flipped = decide_acquisition(
        PICKUP_CUTOFF_OPTIONS, _cost(ask_caregiver_telegram=1, ask_parent_telegram=2)
    )
    assert flipped.chosen == "ask_caregiver_telegram" and flipped.cost_decisive
    alone = decide_acquisition(PICKUP_CUTOFF_OPTIONS[2:], _cost())
    assert alone.chosen == "browse_daycare_site" and not alone.cost_decisive
    unknown = decide_acquisition(
        PICKUP_CUTOFF_OPTIONS, TableCostModel({"ask_caregiver_telegram": 5})
    )
    assert unknown.chosen == "ask_caregiver_telegram"  # an unknown cost is never "free"
