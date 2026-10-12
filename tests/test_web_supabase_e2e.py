"""Real-stack preparer mechanics, using disposable PG and synthetic Auth allocation.

This validates the runner, not real Supabase Auth/Realtime availability.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts import web_supabase_e2e as runner


@pytest.mark.postgres
def test_real_proof_preparer_and_append_touch_only_synthetic_records(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import psycopg

    from serene.adapters.postgres import PostgresProjectionStore

    private = tmp_path / "private.json"
    monkeypatch.setattr(runner, "PRIVATE", private)
    monkeypatch.setenv("SUPABASE_DB_URL", pg_dsn)
    ids = iter(str(uuid.UUID(int=i)) for i in (101, 102, 103))
    monkeypatch.setattr(runner, "auth_user", lambda email, password: next(ids))
    with psycopg.connect(pg_dsn) as conn:
        conn.execute("create publication supabase_realtime")
        conn.execute("alter publication supabase_realtime add table serene.projection_state")
    runner.prepare()
    manifest = json.loads(private.read_text("utf-8"))
    assert manifest["ready"] and manifest["classification"] == "SYNTHETIC"
    assert set(manifest["accounts"]) == {"parent", "other", "caregiver"}
    child = manifest["accounts"]["parent"]["child_id"]
    view = PostgresProjectionStore(pg_dsn).load(child)["experiments"]
    pending = [e["approval"] for e in view["experiments"] if e["approval"]]
    assert len(pending) == 2 and all(a["decision_open"] for a in pending)
    # Synthetic builders normally advance simulated minutes; the real-stack
    # runner must never create a request in the production clock's future.
    assert all(datetime.fromisoformat(a["requested_at"]) <= datetime.now(UTC) for a in pending)
    with psycopg.connect(pg_dsn) as conn:
        assert conn.execute("select distinct data_class from serene.children").fetchall() == [
            ("SYNTHETIC",)
        ]
        before = conn.execute("select count(*) from serene.domain_events").fetchone()[0]
    runner.append("Synthetic: runner append proof")
    runner.check()
    with psycopg.connect(pg_dsn) as conn:
        assert conn.execute("select count(*) from serene.domain_events").fetchone()[0] == before + 1
    # An unknown child is not an explicitly synthetic child either.
    manifest = json.loads(private.read_text("utf-8"))
    manifest["accounts"]["parent"]["child_id"] = "chd_" + "f" * 32
    private.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="non-synthetic"):
        runner.append("Synthetic: must be refused")
