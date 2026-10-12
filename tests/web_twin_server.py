"""Loopback-only browser test kernel for the live Causal Twin; synthetic Auth, real Postgres.

This is NOT a Supabase server/proof. Like `tests.web_approval_server` it
replaces Auth and PostgREST for a Playwright lane, and Realtime delivery is
controlled in Playwright. The production ledger, projection publisher,
migrations and RLS are used unchanged: every row the browser receives is read
from `serene.projection_state` as the signed-in user. Nothing imports this
module from the application. The database is disposable and every child
SYNTHETIC.

- parent@example.org is the parent of two children, each with a twin;
- other@example.org is the parent of a third child only;
- caregiver@example.org holds every caregiver scope on the parent's first child.

`POST /__test/append?child=<id>` admits one more hypothesis for that child
through the production ledger, which republishes its projections.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any
from urllib.parse import parse_qs

import psycopg
from psycopg.rows import dict_row

from serene.adapters.postgres import PostgresEventStore, backfill_projections, postgres_ledger
from serene.domain.entities import Hypothesis, OutcomeResult
from serene.domain.events import EventType, HypothesisRefuted
from serene.testing import SyntheticFamily

from .web_approval_server import ACCOUNTS, CAREGIVER, ORIGIN, OTHER, PARENT, serve, token


def _move_to_postgres(fam: SyntheticFamily, dsn: str) -> None:
    store = PostgresEventStore(dsn)
    for event in fam.store.read_stream(fam.child_id):
        store.append(event, expected_prev_hash=event.prev_event_hash)
    fam.store = store
    fam.ledger = postgres_ledger(dsn, fam.clock)


def _family(seed: str, explanations: tuple[str, ...]) -> tuple[SyntheticFamily, list[Hypothesis]]:
    fam = SyntheticFamily(seed=seed)
    o1 = fam.observe("Synthetic: tearful pickup", day=0)
    o2 = fam.observe("Synthetic: tearful pickup again", day=1)
    pattern = fam.pattern((o1, o2), "Synthetic: pickups are tearful")
    inv = fam.open_investigation("Synthetic: why are pickups hard?")
    return fam, [fam.hypothesis(inv, (pattern,), statement) for statement in explanations]


def _refute(fam: SyntheticFamily, hyp: Hypothesis) -> None:
    """Test a hypothesis, contradict it and refute it by policy."""
    exp = fam.propose_experiment(hyp)
    fam.classify(exp)
    apr = fam.request_approval(exp)
    fam.grant(exp, apr)
    fam.start(exp, apr)
    r1 = fam.observe("Synthetic: tearful despite a snack", day=3)
    r2 = fam.observe("Synthetic: tearful despite a snack again", day=4)
    outcome = fam.outcome(exp, (r1, r2), result=OutcomeResult.CONTRADICTS)
    fam.complete(exp, (outcome,))
    fam.append(
        fam.draft(
            EventType.HYPOTHESIS_REFUTED,
            fam.policy,
            HypothesisRefuted(
                hypothesis_id=hyp.hypothesis_id,
                outcome_ids=(outcome.outcome_id,),
                reason_codes=("CONTRADICTING_OUTCOME",),
            ),
        )
    )


class TwinKernel:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.tokens = {token(u): u for u in (PARENT, OTHER, CAREGIVER)}
        first, (_kept, hunger) = _family(
            "browser-twin-first",
            ("Synthetic: abrupt transitions drive distress", "Synthetic: hunger after daycare"),
        )
        _refute(first, hunger)
        second, _ = _family("browser-twin-second", ("Synthetic: a noisy pickup room",))
        theirs, _ = _family("browser-twin-other-parent", ("Synthetic: another family's idea",))
        self.theirs = theirs.child_id
        self.families = {f.child_id: f for f in (first, second, theirs)}
        for fam in self.families.values():
            _move_to_postgres(fam, dsn)
        with psycopg.connect(dsn) as conn:
            for fam, guardian in ((first, PARENT), (second, PARENT), (theirs, OTHER)):
                conn.execute(
                    "insert into serene.children values (%s, 'SYNTHETIC', now())", (fam.child_id,)
                )
                conn.execute(
                    "insert into serene.child_guardians (child_id, user_id, role) "
                    "values (%s, %s, 'PARENT')",
                    (fam.child_id, guardian),
                )
            for scope in ("observations:read", "experiments:read", "learnings:read"):
                conn.execute(
                    "insert into serene.caregiver_grants "
                    "(child_id, caregiver_id, scope, granted_by, expires_at) "
                    "values (%s, %s, %s, %s, now() + interval '1 day')",
                    (first.child_id, CAREGIVER, scope, PARENT),
                )
        backfill_projections(dsn)
        self.appended = 0

    def rows(self, user: str | None, table: str) -> list[dict[str, Any]]:
        if not user:
            return []
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            conn.execute("set local role authenticated")
            conn.execute("select set_config('request.jwt.claim.sub', %s, true)", (user,))
            if table == "child_guardians":
                return conn.execute(
                    "select child_id from serene.child_guardians order by child_id"
                ).fetchall()
            return conn.execute(
                "select child_id, projection, state, last_sequence, last_event_hash "
                "from serene.projection_state order by child_id, projection"
            ).fetchall()

    def append(self, child_id: str) -> dict[str, Any]:
        fam = self.families[child_id]
        self.appended += 1
        o1 = fam.observe(f"Synthetic: calm pickup {self.appended}", day=10 + self.appended)
        o2 = fam.observe(f"Synthetic: calm pickup again {self.appended}", day=11 + self.appended)
        inv = fam.open_investigation(f"Synthetic: what helps pickups? {self.appended}")
        pattern = fam.pattern((o1, o2), f"Synthetic: calm pickups {self.appended}")
        hyp = fam.hypothesis(inv, (pattern,), f"Synthetic: a heads-up helps {self.appended}")
        return {"hypothesis_id": hyp.hypothesis_id, "statement": hyp.statement}

    def __call__(self, env: dict[str, Any], respond: Any) -> Iterable[bytes]:
        path = env["PATH_INFO"]
        query = parse_qs(env.get("QUERY_STRING", ""))
        user = self.tokens.get(env.get("HTTP_AUTHORIZATION", "").removeprefix("Bearer "))
        status, body = 200, {}
        if env["REQUEST_METHOD"] == "OPTIONS":
            pass
        elif path == "/auth/v1/token":
            raw = env["wsgi.input"].read(int(env.get("CONTENT_LENGTH") or 0))
            credentials = json.loads(raw)
            account = ACCOUNTS.get(credentials.get("email"))
            if not account or credentials.get("password") != "fake-synthetic-only":
                status, body = 400, {"error": "invalid_credentials"}
            else:
                body = {
                    "access_token": next(t for t, u in self.tokens.items() if u == account),
                    "token_type": "bearer",
                    "expires_in": 3600,
                    "refresh_token": "fake-refresh-token",
                    "user": {"id": account, "aud": "authenticated", "email": credentials["email"]},
                }
        elif path == "/auth/v1/user":
            status, body = (200, {"id": user, "aud": "authenticated"}) if user else (401, {})
        elif path == "/rest/v1/child_guardians":
            body = self.rows(user, "child_guardians")
        elif path == "/rest/v1/projection_state":
            child = query.get("child_id", [""])[0].removeprefix("eq.")
            body = [
                r
                for r in self.rows(user, "projection_state")
                if not child or r["child_id"] == child
            ]
        elif path == "/__test/children":
            body = {
                "parent": sorted(c for c in self.families if c != self.theirs),
                "other": [self.theirs],
            }
        elif path == "/__test/append" and env["REQUEST_METHOD"] == "POST":
            body = self.append(query["child"][0])
        elif path == "/__test/check":
            body = {
                "verified": all(f.ledger.verify_hash_chain(c).ok for c, f in self.families.items())
            }
        elif path == "/auth/v1/logout":
            pass
        else:
            status = 404
        data = json.dumps(body).encode()
        respond(
            f"{status} {'OK' if status == 200 else 'Refused'}",
            [
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(data))),
                ("Access-Control-Allow-Origin", ORIGIN),
                ("Cache-Control", "no-store"),
                (
                    "Access-Control-Allow-Headers",
                    "authorization,apikey,content-type,x-client-info,accept-profile,x-supabase-api-version",
                ),
                ("Access-Control-Allow-Methods", "GET,POST,OPTIONS"),
            ],
        )
        return [data]


if __name__ == "__main__":
    serve(TwinKernel)
