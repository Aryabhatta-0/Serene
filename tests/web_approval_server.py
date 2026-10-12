"""Loopback-only browser test kernel; synthetic Auth, real Postgres and admission.

This is NOT a Supabase server/proof. It replaces Auth and PostgREST for the
test-kernel Playwright lane. Realtime delivery is controlled in Playwright.
The production verifier, guardian resolver, HTTP channel, ledger, projection
publisher, migrations and RLS are used unchanged. Nothing imports this module
from the application. Every database is disposable and every child SYNTHETIC.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import time
import uuid
from collections.abc import Callable, Iterable
from socketserver import ThreadingMixIn
from typing import Any
from urllib.parse import parse_qs
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from serene.adapters.postgres import PostgresEventStore, backfill_projections, postgres_ledger
from serene.adapters.web import WebApprovalChannel
from serene.adapters.web.guardians import (
    PostgresGuardianRegistry,
    WebBinding,
    WebBindings,
    WebPrincipals,
)
from serene.adapters.web.http import make_approvals_app
from serene.adapters.web.session import SupabaseSessionVerifier
from serene.testing import SyntheticFamily

from .conftest import MIGRATIONS
from .trust_helpers import C, awaiting_approval, hypothesis, intervention, service

HOST = "http://127.0.0.1:8806"
ORIGIN = "http://127.0.0.1:3278"
PARENT, OTHER, CAREGIVER = (str(uuid.UUID(int=i)) for i in (1, 2, 3))
ACCOUNTS = {
    "parent@example.org": PARENT,
    "other@example.org": OTHER,
    "caregiver@example.org": CAREGIVER,
}


def token(user: str) -> str:
    def part(value: Any) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")

    # Synthetic, unsigned test token; the Auth stub checks exact membership.
    header = part({"alg": "HS256", "typ": "JWT"})
    claims = part({"sub": user, "aud": "authenticated", "exp": int(time.time()) + 3600})
    return f"{header}.{claims}.fake-signature"


class ThreadedServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args: Any) -> None:
        pass


class BrowserKernel:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.tokens = {token(u): u for u in (PARENT, OTHER, CAREGIVER)}
        self.fam = SyntheticFamily(seed="browser-http-kernel")
        awaiting_approval(self.fam)
        awaiting_approval(
            self.fam, intervention(C.ENVIRONMENT, "Synthetic: dim the hallway lights")
        )
        _inv, hyp = hypothesis(self.fam)
        red = self.fam.propose_experiment(
            hyp, intervention(C.MEDICATION, "Synthetic: medication change")
        )
        service(self.fam).classify(self.fam.child_id, red.experiment_id)
        awaiting_approval(self.fam, intervention(C.SLEEP_SCHEDULE, "Synthetic: shift bedtime"))
        store = PostgresEventStore(dsn)
        for event in self.fam.store.read_stream(self.fam.child_id):
            store.append(event, expected_prev_hash=event.prev_event_hash)
        self.fam.store = store
        self.fam.ledger = postgres_ledger(dsn, self.fam.clock)
        with psycopg.connect(dsn) as conn:
            conn.execute(
                "insert into serene.children values (%s, 'SYNTHETIC', now())", (self.fam.child_id,)
            )
            conn.execute(
                "insert into serene.child_guardians (child_id, user_id, role) "
                "values (%s, %s, 'PARENT')",
                (self.fam.child_id, PARENT),
            )
            conn.execute(
                "insert into serene.caregiver_grants "
                "(child_id, caregiver_id, scope, granted_by, expires_at) "
                "values (%s, %s, 'learnings:read', %s, now() + interval '1 day')",
                (self.fam.child_id, CAREGIVER, PARENT),
            )
        backfill_projections(dsn)
        self.approvals = make_approvals_app(
            WebApprovalChannel(self.fam.ledger, self.fam.clock),
            SupabaseSessionVerifier(HOST, "fake-anon-key"),
            WebPrincipals(
                PostgresGuardianRegistry(dsn),
                WebBindings.of(
                    [
                        WebBinding(
                            user_id=uuid.UUID(PARENT),
                            child_id=self.fam.child_id,
                            actor=self.fam.parent,
                        )
                    ]
                ),
            ),
            allowed_origins=frozenset({ORIGIN}),
        )

    def rows(self, user: str | None, table: str) -> list[dict[str, Any]]:
        if not user:
            return []
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            conn.execute("set local role authenticated")
            conn.execute("select set_config('request.jwt.claim.sub', %s, true)", (user,))
            if table == "child_guardians":
                return conn.execute("select child_id from serene.child_guardians").fetchall()
            return conn.execute(
                "select child_id, projection, state, last_sequence, last_event_hash "
                "from serene.projection_state"
            ).fetchall()

    def __call__(self, env: dict[str, Any], respond: Any) -> Iterable[bytes]:
        path = env["PATH_INFO"]
        if path == "/web/approvals":
            return self.approvals(env, respond)
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
            child = (
                parse_qs(env.get("QUERY_STRING", "")).get("child_id", [""])[0].removeprefix("eq.")
            )
            body = [
                r
                for r in self.rows(user, "projection_state")
                if not child or r["child_id"] == child
            ]
        elif path == "/__test/head":
            events = self.fam.ledger.get_events_for_child(self.fam.child_id)
            body = {
                "child_id": self.fam.child_id,
                "events": len(events),
                "decisions": sum(
                    e.event_type.value in {"APPROVAL_GRANTED", "APPROVAL_REJECTED"} for e in events
                ),
            }
        elif path == "/__test/check":
            body = {"verified": self.fam.ledger.verify_hash_chain(self.fam.child_id).ok}
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


def serve(make_kernel: Callable[[str], Any]) -> None:
    """Migrate a disposable database, build the kernel on it and serve it on 8806."""
    import pgserver

    with tempfile.TemporaryDirectory(prefix="serene-browser-") as temp:
        server = None
        admin_dsn = os.environ.get("SERENE_TEST_DATABASE_URL")
        if not admin_dsn:
            server = pgserver.get_server(temp, cleanup_mode="stop")
            admin_dsn = server.get_uri()
        name = "serene_browser_" + uuid.uuid4().hex[:12]
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute(f'create database "{name}"')
        params = conninfo_to_dict(admin_dsn) | {"dbname": name}
        dsn = make_conninfo(**params)
        try:
            with psycopg.connect(dsn, autocommit=True) as conn:
                for migration in MIGRATIONS:
                    conn.execute(migration.read_text("utf-8"))
            kernel = make_kernel(dsn)
            with make_server(
                "127.0.0.1", 8806, kernel, server_class=ThreadedServer, handler_class=QuietHandler
            ) as http:
                http.serve_forever()
        finally:
            with psycopg.connect(admin_dsn, autocommit=True) as admin:
                admin.execute(f'drop database "{name}" with (force)')
            if server:
                server.cleanup()


def main() -> None:
    serve(BrowserKernel)


if __name__ == "__main__":
    main()
