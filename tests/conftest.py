"""Shared fixtures. All data is synthetic (serene.testing)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from serene.testing import SyntheticFamily, build_full_ladder

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = sorted((REPO_ROOT / "supabase" / "migrations").glob("*.sql"))


@pytest.fixture
def family() -> SyntheticFamily:
    return SyntheticFamily(seed="test-family")


@pytest.fixture
def ladder() -> dict[str, Any]:
    return build_full_ladder(seed="test-ladder")


# ------------------------------------------------------------------ postgres
@pytest.fixture(scope="session")
def pg_admin_dsn(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """A real PostgreSQL: SERENE_TEST_DATABASE_URL (CI) or a local pgserver instance."""
    dsn = os.environ.get("SERENE_TEST_DATABASE_URL")
    if dsn:
        yield dsn
        return
    try:
        import pgserver
    except ImportError:
        pytest.skip("no SERENE_TEST_DATABASE_URL and pgserver not installed")
    server = pgserver.get_server(str(tmp_path_factory.mktemp("pgdata")), cleanup_mode="stop")
    try:
        yield server.get_uri()
    finally:
        server.cleanup()


@pytest.fixture
def pg_dsn(pg_admin_dsn: str) -> Iterator[str]:
    """A fresh database with every migration applied; dropped afterwards."""
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    name = f"serene_test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(pg_admin_dsn, autocommit=True) as admin:
        admin.execute(f'create database "{name}"')
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
            admin.execute(f'drop database if exists "{name}" with (force)')
