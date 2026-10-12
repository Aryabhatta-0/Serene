"""Prepare/append/check SYNTHETIC records for the opt-in real Supabase browser proof.

Requires an already migrated, exposed Serene project and real operator-supplied
SUPABASE_URL, SUPABASE_ANON_KEY and SUPABASE_DB_URL. Preparing Auth users also
requires the server-only SUPABASE_SERVICE_ROLE_KEY; append/check do not.
No fallback, migrations, production identity changes, or real children. The
private test accounts/bindings go only in ignored .demo/web-e2e.json. No secrets
are printed. Keep the synthetic ledger for evidence; use a disposable local
stack when records must be removed afterwards.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg

from serene.adapters.clock import FixedClock
from serene.adapters.postgres import PostgresEventStore, postgres_ledger
from serene.testing import SyntheticFamily
from tests.trust_helpers import C, awaiting_approval, hypothesis, intervention, service

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / ".demo" / "web-e2e.json"


class LiveFixtureClock(FixedClock):
    """Use wall time with the synthetic builders, never their simulated minute ticks.

    Production approvals use SystemClock; a synthetic request recorded in the
    future would correctly be refused there. No kernel/eval clock is changed.
    """

    def __init__(self) -> None:
        super().__init__(datetime.now(UTC))

    def now(self) -> datetime:
        return datetime.now(UTC)

    def advance(self, delta: timedelta) -> None:
        pass


def auth_user(email: str, password: str) -> str:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    if not url.startswith(("https://", "http://127.0.0.1:", "http://localhost:")):
        raise ValueError("Supabase must be HTTPS or loopback")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    req = urllib.request.Request(  # noqa: S310 - checked scheme
        url + "/auth/v1/admin/users",
        data=json.dumps({"email": email, "password": password, "email_confirm": True}).encode(),
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as response:  # noqa: S310
        return str(uuid.UUID(json.load(response)["id"]))


def prepare() -> None:
    if PRIVATE.exists():
        raise RuntimeError("private run manifest already exists; preserve it and use that run")
    dsn = os.environ["SUPABASE_DB_URL"]
    with psycopg.connect(dsn) as conn:
        # Refuse before creating users if the latest migration is absent.
        constraint = conn.execute(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid = 'serene.projection_state'::regclass "
            "and conname = 'projection_state_projection_check'"
        ).fetchone()
        if not constraint or "'experiments'" not in constraint[0]:
            raise RuntimeError("apply current migrations before preparing the real proof")
        published = conn.execute(
            "select tablename from pg_publication_tables where pubname = 'supabase_realtime' "
            "and schemaname = 'serene'"
        ).fetchall()
        if ("projection_state",) not in published or ("domain_events",) in published:
            raise RuntimeError("publish projection_state only before preparing the real proof")
    run = uuid.uuid4().hex
    manifest: dict[str, Any] = {"classification": "SYNTHETIC", "accounts": {}, "bindings": []}
    PRIVATE.parent.mkdir(parents=True, exist_ok=True)
    # Persist after each allocation, so a partial failure cannot lose the
    # identity of synthetic accounts that were already created.
    for role in ("parent", "other", "caregiver"):
        email = f"serene-e2e-{role}-{run}@example.org"
        password = secrets.token_urlsafe(24)
        user = auth_user(email, password)
        manifest["accounts"][role] = {"email": email, "password": password, "user_id": user}
        PRIVATE.write_text(json.dumps(manifest), encoding="utf-8")
    for role in ("parent", "other"):
        fam = SyntheticFamily(
            seed=f"web-e2e-{role}-{run}",
            store=PostgresEventStore(dsn),
            clock=LiveFixtureClock(),
        )
        fam.ledger = postgres_ledger(dsn, fam.clock)
        awaiting_approval(fam)
        awaiting_approval(fam, intervention(C.ENVIRONMENT, "Synthetic: dim the hallway lights"))
        _inv, hyp = hypothesis(fam)
        red = fam.propose_experiment(
            hyp, intervention(C.MEDICATION, "Synthetic: medication change")
        )
        service(fam).classify(fam.child_id, red.experiment_id)
        user = manifest["accounts"][role]["user_id"]
        with psycopg.connect(dsn) as conn:
            conn.execute(
                "insert into serene.children values (%s, 'SYNTHETIC', now())", (fam.child_id,)
            )
            conn.execute(
                "insert into serene.child_guardians (child_id, user_id, role) "
                "values (%s, %s, 'PARENT')",
                (fam.child_id, user),
            )
        manifest["accounts"][role].update(
            child_id=fam.child_id, seed=fam.seed, counter=fam._counter
        )
        manifest["bindings"].append(
            {"user_id": user, "child_id": fam.child_id, "actor": fam.parent.model_dump(mode="json")}
        )
        PRIVATE.write_text(json.dumps(manifest), encoding="utf-8")
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "insert into serene.caregiver_grants "
            "(child_id, caregiver_id, scope, granted_by, expires_at) "
            "values (%s, %s, 'learnings:read', %s, now() + interval '1 day')",
            (
                manifest["accounts"]["parent"]["child_id"],
                manifest["accounts"]["caregiver"]["user_id"],
                manifest["accounts"]["parent"]["user_id"],
            ),
        )
    manifest["ready"] = True
    PRIVATE.write_text(json.dumps(manifest), encoding="utf-8")
    print("Prepared 3 synthetic users, 2 synthetic children, guardians and web bindings.")


def append(question: str) -> None:
    manifest = json.loads(PRIVATE.read_text("utf-8"))
    if manifest.get("classification") != "SYNTHETIC" or not manifest.get("ready"):
        raise RuntimeError("a completed synthetic run is required")
    account = manifest["accounts"]["parent"]
    dsn = os.environ["SUPABASE_DB_URL"]
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "select data_class from serene.children where child_id = %s", (account["child_id"],)
        ).fetchone()
        if row != ("SYNTHETIC",):
            raise RuntimeError("refusing to append to a non-synthetic child")
    fam = SyntheticFamily(
        seed=account["seed"], store=PostgresEventStore(dsn), clock=LiveFixtureClock()
    )
    if fam.child_id != account["child_id"]:
        raise RuntimeError("synthetic child binding mismatch")
    fam._counter = account["counter"]
    fam.ledger = postgres_ledger(dsn, fam.clock)
    fam.open_investigation(question)
    account["counter"] = fam._counter
    PRIVATE.write_text(json.dumps(manifest), encoding="utf-8")
    assert fam.ledger.verify_hash_chain(fam.child_id).ok
    print("Appended and published one synthetic kernel event; hash chain verified.")


def check() -> None:
    """Report real ledger/projection agreement without printing private bindings."""
    manifest = json.loads(PRIVATE.read_text("utf-8"))
    if manifest.get("classification") != "SYNTHETIC" or not manifest.get("ready"):
        raise RuntimeError("a completed synthetic run is required")
    dsn = os.environ["SUPABASE_DB_URL"]
    child = manifest["accounts"]["parent"]["child_id"]
    ledger = postgres_ledger(dsn, LiveFixtureClock())
    assert ledger.verify_hash_chain(child).ok
    with psycopg.connect(dsn) as conn:
        assert conn.execute(
            "select data_class from serene.children where child_id = %s", (child,)
        ).fetchone() == ("SYNTHETIC",)
        head = conn.execute(
            "select sequence, event_hash from serene.domain_events "
            "where child_id = %s order by sequence desc limit 1",
            (child,),
        ).fetchone()
        rows = conn.execute(
            "select last_sequence, last_event_hash from serene.projection_state "
            "where child_id = %s",
            (child,),
        ).fetchall()
        assert head and rows and all(row == head for row in rows)
        decisions = conn.execute(
            "select count(*) from serene.domain_events "
            "where child_id = %s and event_type in ('APPROVAL_GRANTED', 'APPROVAL_REJECTED')",
            (child,),
        ).fetchone()[0]
    print(json.dumps({"sequence": head[0], "decisions": decisions, "verified": True}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "append", "check"))
    parser.add_argument("--question", default="Synthetic: live Realtime proof")
    args = parser.parse_args()
    configured = (
        os.environ.get("SUPABASE_URL"),
        os.environ.get("SUPABASE_ANON_KEY"),
        os.environ.get("SUPABASE_DB_URL"),
    )
    if not all(configured):
        raise RuntimeError("real Supabase configuration is required; there is no fallback")
    if args.action == "prepare":
        if not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
            raise RuntimeError("preparing Auth users requires the server-only admin key")
        prepare()
    elif args.action == "append":
        append(args.question)
    else:
        check()


if __name__ == "__main__":
    main()
