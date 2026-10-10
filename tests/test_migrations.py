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
    match = re.search(column + r"\s+in\s*\((.*?)\)\)", SQL, flags=re.S)
    assert match, column
    return set(re.findall(r"'([A-Za-z_]+)'", match.group(1)))


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
