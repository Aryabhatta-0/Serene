"""Supabase RLS access boundary against a real PostgreSQL (issue #8).

Adversarial: cross-child reads, caregiver scope escalation, self-granting,
forged guardianship, ledger writes by end users, service-role isolation and
synthetic-only evaluation access.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("psycopg")

import psycopg
from psycopg import sql

from serene.adapters.postgres import PostgresEventStore
from serene.testing import build_full_ladder

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
RLS_SQL = (ROOT / "supabase" / "migrations" / "20261011120000_serene_rls_access.sql").read_text(
    encoding="utf-8"
)

P1, P2 = uuid.UUID(int=1), uuid.UUID(int=2)  # parents of child A and child B
C_OBS, C_NONE, C_EXPIRED, C_REVOKED, C_NEW = (uuid.UUID(int=i) for i in (11, 12, 13, 14, 15))


# Built once in memory, then copied verbatim into each fresh database.
_LADDERS = tuple(build_full_ladder(seed=f"rls-{n}")["family"] for n in ("a", "b", "synthetic"))


@pytest.fixture(scope="module")
def rls_db(pg_admin_dsn: str) -> Iterator[dict[str, Any]]:
    """Fresh database with Supabase-like roles created *before* the migrations run."""
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    with psycopg.connect(pg_admin_dsn, autocommit=True) as admin:
        for role, attrs in (
            ("anon", "nologin"),
            ("authenticated", "nologin"),
            ("service_role", "nologin bypassrls"),
        ):
            exists = admin.execute("select 1 from pg_roles where rolname = %s", (role,)).fetchone()
            if not exists:
                admin.execute(sql.SQL("create role {} " + attrs).format(sql.Identifier(role)))
        name = f"serene_rls_{uuid.uuid4().hex[:12]}"
        admin.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
    params = conninfo_to_dict(pg_admin_dsn)
    params["dbname"] = name
    dsn = make_conninfo(**params)
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            for migration in MIGRATIONS:
                conn.execute(migration.read_text(encoding="utf-8"))
        store = PostgresEventStore(dsn)
        a, b, s = _LADDERS
        for fam in _LADDERS:
            for event in fam.store.read_stream(fam.child_id):
                store.append(event, expected_prev_hash=event.prev_event_hash)
        now = datetime.now(UTC)
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(
                "insert into serene.children (child_id, data_class) values "
                "(%s, 'REAL'), (%s, 'REAL'), (%s, 'SYNTHETIC')",
                (a.child_id, b.child_id, s.child_id),
            )
            conn.execute(
                "insert into serene.child_guardians (child_id, user_id, role) values "
                "(%s, %s, 'PARENT'), (%s, %s, 'PARENT')",
                (a.child_id, P1, b.child_id, P2),
            )
            for caregiver, expires, revoked in (
                (C_OBS, now + timedelta(days=30), None),
                (C_EXPIRED, now + timedelta(seconds=1), None),
                (C_REVOKED, now + timedelta(days=30), now),
            ):
                conn.execute(
                    "insert into serene.caregiver_grants "
                    "(child_id, caregiver_id, scope, granted_by, granted_at, expires_at, "
                    "revoked_at) "
                    "values (%s, %s, 'observations:read', %s, %s, %s, %s)",
                    (a.child_id, caregiver, P1, now - timedelta(days=1), expires, revoked),
                )
            conn.execute(
                "update serene.caregiver_grants set expires_at = granted_at + interval '1 hour' "
                "where caregiver_id = %s",
                (C_EXPIRED,),
            )
            for fam in (a, b, s):
                conn.execute(
                    "insert into serene.projection_state "
                    "(child_id, projection, state, last_sequence, last_event_hash) "
                    "values (%s, 'active_learnings', '{}'::jsonb, 1, %s), "
                    "(%s, 'pending_approvals', '{}'::jsonb, 1, %s)",
                    (fam.child_id, "0" * 64, fam.child_id, "0" * 64),
                )
        yield {"dsn": dsn, "a": a.child_id, "b": b.child_id, "s": s.child_id}
    finally:
        with psycopg.connect(pg_admin_dsn, autocommit=True) as admin:
            admin.execute(
                sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(name))
            )


@contextmanager
def session(
    dsn: str, role: str, user: uuid.UUID | None = None
) -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("set role {}").format(sql.Identifier(role)))
        if user is not None:
            conn.execute(
                "select set_config('request.jwt.claims', %s, false)",
                (json.dumps({"sub": str(user), "role": role}),),
            )
        yield conn
        conn.rollback()


def _children_with_events(conn: psycopg.Connection[Any]) -> set[str]:
    return {r[0] for r in conn.execute("select distinct child_id from serene.domain_events")}


def _types(conn: psycopg.Connection[Any]) -> set[str]:
    return {r[0] for r in conn.execute("select distinct event_type from serene.domain_events")}


@pytest.mark.parametrize("projection", ["memory_review", "memory_dream"])
def test_memory_projection_is_parent_only_and_child_scoped(
    rls_db: dict[str, Any], projection: str
) -> None:
    with psycopg.connect(rls_db["dsn"]) as conn:
        for child in (rls_db["a"], rls_db["b"]):
            conn.execute(
                "insert into serene.projection_state "
                "(child_id, projection, state, last_sequence, last_event_hash) "
                "values (%s, %s, '{}'::jsonb, 1, %s) on conflict do nothing",
                (child, projection, "0" * 64),
            )
    for user, child in ((P1, rls_db["a"]), (P2, rls_db["b"])):
        with session(rls_db["dsn"], "authenticated", user) as conn:
            rows = conn.execute(
                "select child_id from serene.projection_state where projection = %s",
                (projection,),
            ).fetchall()
            assert rows == [(child,)]
    for user in (C_OBS, C_NONE, C_EXPIRED, C_REVOKED):
        with session(rls_db["dsn"], "authenticated", user) as conn:
            assert conn.execute(
                "select count(*) from serene.projection_state where projection = %s",
                (projection,),
            ).fetchone() == (0,)


# ------------------------------------------------------------------ parents
def test_parent_reads_own_child_only(rls_db: dict[str, Any]) -> None:
    with session(rls_db["dsn"], "authenticated", P1) as conn:
        assert _children_with_events(conn) == {rls_db["a"]}
        assert "APPROVAL_GRANTED" in _types(conn)
        rows = conn.execute(
            "select count(*) from serene.domain_events where child_id = %s", (rls_db["b"],)
        ).fetchone()
        assert rows == (0,)
        assert {r[0] for r in conn.execute("select child_id from serene.projection_state")} == {
            rls_db["a"]
        }
    with session(rls_db["dsn"], "authenticated", P2) as conn:
        assert _children_with_events(conn) == {rls_db["b"]}


def test_unauthenticated_and_anonymous_sessions_see_nothing(rls_db: dict[str, Any]) -> None:
    with session(rls_db["dsn"], "authenticated") as conn:
        assert _children_with_events(conn) == set()
    with (
        session(rls_db["dsn"], "anon") as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute("select count(*) from serene.domain_events")


@pytest.mark.parametrize(
    "statement",
    [
        "insert into serene.domain_events (event_id) values ('evt_' || repeat('0', 32))",
        "update serene.domain_events set payload = '{}'::jsonb",
        "delete from serene.domain_events",
        "insert into serene.child_guardians (child_id, user_id, role) "
        "select child_id, '00000000-0000-0000-0000-000000000001', 'PARENT' from serene.children",
        "update serene.children set data_class = 'SYNTHETIC'",
    ],
)
def test_end_users_cannot_write_the_ledger_or_claim_guardianship(
    rls_db: dict[str, Any], statement: str
) -> None:
    with (
        session(rls_db["dsn"], "authenticated", P1) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(statement)


# ------------------------------------------------------------------ caregivers
def test_caregiver_sees_only_the_granted_event_family_of_the_granted_child(
    rls_db: dict[str, Any],
) -> None:
    with session(rls_db["dsn"], "authenticated", C_OBS) as conn:
        assert _children_with_events(conn) == {rls_db["a"]}
        assert _types(conn) == {"OBSERVATION_REPORTED", "OBSERVATION_STRUCTURED"}
        assert conn.execute("select count(*) from serene.projection_state").fetchone() == (0,)
        assert {r[0] for r in conn.execute("select child_id from serene.children")} == {rls_db["a"]}


@pytest.mark.parametrize("caregiver", [C_NONE, C_EXPIRED, C_REVOKED])
def test_caregiver_without_a_live_grant_is_denied(
    rls_db: dict[str, Any], caregiver: uuid.UUID
) -> None:
    with session(rls_db["dsn"], "authenticated", caregiver) as conn:
        assert _children_with_events(conn) == set()
        assert conn.execute("select count(*) from serene.children").fetchone() == (0,)


def test_caregiver_cannot_grant_themselves_or_widen_scope(rls_db: dict[str, Any]) -> None:
    expires = datetime.now(UTC) + timedelta(days=1)
    with (
        session(rls_db["dsn"], "authenticated", C_OBS) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(
            "insert into serene.caregiver_grants "
            "(child_id, caregiver_id, scope, granted_by, expires_at)"
            " values (%s, %s, 'experiments:read', %s, %s)",
            (rls_db["a"], C_OBS, P1, expires),
        )
    with (
        session(rls_db["dsn"], "authenticated", C_OBS) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute("update serene.caregiver_grants set scope = 'experiments:read'")


def test_parent_grants_only_on_own_child_and_can_revoke(rls_db: dict[str, Any]) -> None:
    expires = datetime.now(UTC) + timedelta(days=7)
    insert = (
        "insert into serene.caregiver_grants "
        "(child_id, caregiver_id, scope, granted_by, expires_at)"
        " values (%s, %s, 'learnings:read', %s, %s)"
    )
    with (
        session(rls_db["dsn"], "authenticated", P1) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(insert, (rls_db["b"], C_NEW, P1, expires))  # child B is not P1's
    with (
        session(rls_db["dsn"], "authenticated", P1) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(insert, (rls_db["a"], C_NEW, P2, expires))  # forging granted_by
    with session(rls_db["dsn"], "authenticated", P1) as conn:
        conn.execute(insert, (rls_db["a"], C_NEW, P1, expires))
        conn.commit()
    with session(rls_db["dsn"], "authenticated", C_NEW) as conn:
        assert _types(conn) == {"LEARNING_RECORDED"}
        rows = conn.execute("select projection from serene.projection_state").fetchall()
        assert rows == [("active_learnings",)]
    with session(rls_db["dsn"], "authenticated", P2) as conn:
        revoked = conn.execute(
            "update serene.caregiver_grants set revoked_at = now() where caregiver_id = %s",
            (C_NEW,),
        )
        assert revoked.rowcount == 0  # another child's parent cannot revoke (or see) it
    with session(rls_db["dsn"], "authenticated", P1) as conn:
        conn.execute(
            "update serene.caregiver_grants set revoked_at = now() where caregiver_id = %s",
            (C_NEW,),
        )
        conn.commit()
    with session(rls_db["dsn"], "authenticated", C_NEW) as conn:
        assert _children_with_events(conn) == set()


# ------------------------------------------------------------------ backend + evaluation
def test_service_role_is_an_isolated_backend_path(rls_db: dict[str, Any]) -> None:
    with session(rls_db["dsn"], "service_role") as conn:
        assert _children_with_events(conn) == {rls_db["a"], rls_db["b"], rls_db["s"]}
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("delete from serene.domain_events")  # still append-only
    with session(rls_db["dsn"], "authenticated", P1) as conn:
        # End-user roles can never become, inherit from, or bypass like the backend.
        row = conn.execute(
            "select pg_has_role('authenticated', 'service_role', 'member'), "
            "pg_has_role('serene_eval', 'service_role', 'member'), "
            "(select rolbypassrls from pg_roles where rolname = 'authenticated'), "
            "(select rolbypassrls from pg_roles where rolname = 'serene_eval'), "
            "current_user"
        ).fetchone()
        assert row == (False, False, False, False, "authenticated")
        claims = json.dumps({"sub": str(P1), "role": "service_role"})
        conn.execute("select set_config('request.jwt.claims', %s, false)", (claims,))
        # A forged role claim changes nothing: the database role decides, not the claim.
        assert _children_with_events(conn) == {rls_db["a"]}


def test_evaluation_role_reads_synthetic_children_only(rls_db: dict[str, Any]) -> None:
    with session(rls_db["dsn"], "serene_eval") as conn:
        assert _children_with_events(conn) == {rls_db["s"]}
        assert {r[0] for r in conn.execute("select child_id from serene.children")} == {rls_db["s"]}
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("select * from serene.child_guardians")


def test_every_serene_table_has_rls_enabled() -> None:
    tables = set(
        re.findall(
            r"create table serene\.(\w+)",
            "\n".join(m.read_text(encoding="utf-8") for m in MIGRATIONS),
        )
    )
    enabled = set(
        re.findall(
            r"alter table serene\.(\w+) enable row level security",
            "\n".join(m.read_text(encoding="utf-8") for m in MIGRATIONS),
        )
    )
    assert tables and tables <= enabled
    assert "to authenticated" in RLS_SQL and "insert" not in re.findall(
        r"grant (\w+)[^;]*serene\.domain_events", RLS_SQL
    )
