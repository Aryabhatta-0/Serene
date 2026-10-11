"""SQL migrations stay in sync with the kernel vocabulary."""

from __future__ import annotations

import re
from pathlib import Path

from serene.domain.events import EventType
from serene.projections import PROJECTIONS

ROOT = Path(__file__).resolve().parents[1]
SQL = "\n".join(
    p.read_text(encoding="utf-8") for p in sorted((ROOT / "supabase/migrations").glob("*.sql"))
)


def _check_list(column: str) -> set[str]:
    # Migrations are append-only, so the *latest* definition of a check list is live.
    matches = re.findall(column + r"\s+in\s*\((.*?)\)\)", SQL, flags=re.S)
    assert matches, column
    return set(re.findall(r"'([A-Za-z_]+)'", matches[-1]))


def test_latest_event_type_constraint_is_regenerated_not_edited() -> None:
    foundation = (ROOT / "supabase/migrations/20261010120000_serene_domain_events.sql").read_text(
        encoding="utf-8"
    )
    assert "INVESTIGATION_PHASE_CHANGED" not in foundation  # applied migration left untouched
    assert "drop constraint if exists domain_events_event_type_check" in SQL


def test_event_type_constraint_matches_taxonomy() -> None:
    assert _check_list("event_type") == {e.value for e in EventType}


def test_projection_constraint_matches_projections() -> None:
    assert _check_list("projection") == set(PROJECTIONS)


def test_ledger_has_append_only_triggers_and_rls() -> None:
    for needle in (
        "before update on serene.domain_events",
        "before delete on serene.domain_events",
        "before truncate on serene.domain_events",
        "alter table serene.domain_events enable row level security",
    ):
        assert needle in SQL
