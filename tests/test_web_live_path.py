"""The signed-in web path against real Postgres with Supabase's roles and RLS (#87).

What the web app does once a parent is signed in, as the `authenticated` role
with their JWT claims: list their children from serene.child_guardians, read
one child's projection snapshot, and see it move after a kernel append through
the production ledger (`postgres_ledger`). Supabase Auth and Realtime delivery
themselves need a Supabase stack and are not exercised here.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

pytest.importorskip("psycopg")

import psycopg
from psycopg import sql

from serene.testing import SyntheticFamily

from .conftest import MIGRATIONS

pytestmark = pytest.mark.postgres

PARENT, OTHER_PARENT, CAREGIVER = (uuid.UUID(int=i) for i in (101, 102, 103))


@pytest.fixture
def supabase_like(pg_admin_dsn: str) -> Iterator[str]:
    """A fresh database with Supabase's roles created before the migrations run."""
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    with psycopg.connect(pg_admin_dsn, autocommit=True) as admin:
        for role, attrs in (
            ("anon", "nologin"),
            ("authenticated", "nologin"),
            ("service_role", "nologin bypassrls"),
        ):
            if not admin.execute("select 1 from pg_roles where rolname = %s", (role,)).fetchone():
                admin.execute(sql.SQL("create role {} " + attrs).format(sql.Identifier(role)))
        name = f"serene_web_{uuid.uuid4().hex[:12]}"
        admin.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
    params = conninfo_to_dict(pg_admin_dsn)
    params["dbname"] = name
    dsn = make_conninfo(**params)
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            for migration in MIGRATIONS:
                conn.execute(migration.read_text(encoding="utf-8"))
        yield dsn
    finally:
        with psycopg.connect(pg_admin_dsn, autocommit=True) as admin:
            admin.execute(
                sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(name))
            )


@contextmanager
def signed_in(dsn: str, user: uuid.UUID) -> Iterator[psycopg.Connection[Any]]:
    """What PostgREST does for a request carrying this user's JWT."""
    with psycopg.connect(dsn) as conn:
        conn.execute("set role authenticated")
        conn.execute(
            "select set_config('request.jwt.claims', %s, false)",
            (json.dumps({"sub": str(user), "role": "authenticated"}),),
        )
        yield conn
        conn.rollback()


def _children(conn: psycopg.Connection[Any], user: uuid.UUID) -> list[str]:
    # The query lib/auth/backend.ts makes.
    rows = conn.execute(
        "select child_id from serene.child_guardians where user_id = %s and role = 'PARENT'",
        (user,),
    ).fetchall()
    return sorted(r[0] for r in rows)


def _snapshot(conn: psycopg.Connection[Any], child_id: str) -> dict[str, tuple[int, Any]]:
    # The query lib/projections/supabase.ts makes.
    rows = conn.execute(
        "select projection, last_sequence, state from serene.projection_state where child_id = %s",
        (child_id,),
    ).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def test_a_signed_in_parent_follows_only_their_own_childs_record(supabase_like: str) -> None:
    from serene.adapters.postgres import PostgresEventStore, postgres_ledger

    dsn = supabase_like
    mine = SyntheticFamily(seed="web-mine", store=PostgresEventStore(dsn))
    theirs = SyntheticFamily(seed="web-theirs", store=PostgresEventStore(dsn))
    for fam in (mine, theirs):
        fam.ledger = postgres_ledger(dsn, fam.clock)
        fam.observe("tearful pickup", day=0)
    now = datetime.now(UTC)
    with psycopg.connect(dsn, autocommit=True) as conn:  # the backend registers guardianship
        conn.execute(
            "insert into serene.children (child_id, data_class) values "
            "(%s, 'SYNTHETIC'), (%s, 'SYNTHETIC')",
            (mine.child_id, theirs.child_id),
        )
        conn.execute(
            "insert into serene.child_guardians (child_id, user_id, role) values "
            "(%s, %s, 'PARENT'), (%s, %s, 'PARENT')",
            (mine.child_id, PARENT, theirs.child_id, OTHER_PARENT),
        )
        conn.execute(
            "insert into serene.caregiver_grants "
            "(child_id, caregiver_id, scope, granted_by, granted_at, expires_at) "
            "values (%s, %s, 'learnings:read', %s, %s, %s)",
            (mine.child_id, CAREGIVER, PARENT, now - timedelta(hours=1), now + timedelta(days=7)),
        )

    with signed_in(dsn, PARENT) as conn:
        # Child selection: only their own child is listed, even when asking for another's.
        assert _children(conn, PARENT) == [mine.child_id]
        assert _children(conn, OTHER_PARENT) == []
        before = _snapshot(conn, mine.child_id)
        assert before["investigations"][1] == {}
        assert _snapshot(conn, theirs.child_id) == {}  # another child's record: nothing

    # A kernel append through the production ledger publishes the change.
    inv = mine.open_investigation("why are pickups hard?")
    with signed_in(dsn, PARENT) as conn:
        after = _snapshot(conn, mine.child_id)
    assert after["investigations"][0] > before["investigations"][0]
    assert inv.investigation_id in after["investigations"][1]

    with signed_in(dsn, OTHER_PARENT) as conn:
        assert _children(conn, OTHER_PARENT) == [theirs.child_id]
        assert _snapshot(conn, mine.child_id) == {}
    with signed_in(dsn, CAREGIVER) as conn:
        # Never listed as a parent; the grant shows active learnings only.
        assert _children(conn, CAREGIVER) == []
        assert set(_snapshot(conn, mine.child_id)) == {"active_learnings"}
    with psycopg.connect(dsn) as conn:
        conn.execute("set role anon")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("select child_id from serene.child_guardians").fetchall()
