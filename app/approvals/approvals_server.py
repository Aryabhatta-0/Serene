"""Serene web approval endpoint (issue #84).

    uv run python app/approvals/approvals_server.py --port 8788

Serves `POST /web/approvals` for the web app's Next.js route `/api/approvals`.
Fails closed at start-up unless every required piece is configured; it never
falls back to an in-memory ledger, an unverified session or an unbound actor.

Required environment (see .env.example): SUPABASE_DB_URL (service role),
SUPABASE_URL + SUPABASE_ANON_KEY (to verify sessions with Supabase Auth),
SERENE_WEB_BINDINGS (user + child -> opaque PARENT actor) and
SERENE_WEB_ORIGINS (the web app's origin(s), comma-separated).
Optional: NEATLOGS_API_KEY / SERENE_TELEMETRY_PSEUDONYM_KEY.
"""

from __future__ import annotations

import argparse
import os
import sys
from wsgiref.simple_server import make_server


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()

    from serene.adapters.clock import SystemClock
    from serene.adapters.neatlogs_sink import build_telemetry
    from serene.adapters.postgres import postgres_ledger
    from serene.adapters.web import WebApprovalChannel
    from serene.adapters.web.guardians import (
        PostgresGuardianRegistry,
        WebPrincipals,
        web_bindings_from_env,
    )
    from serene.adapters.web.http import PATH, make_approvals_app
    from serene.adapters.web.session import SupabaseSessionVerifier

    required = (
        "SUPABASE_DB_URL",
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SERENE_WEB_BINDINGS",
        "SERENE_WEB_ORIGINS",
    )
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print("refusing to start; missing: " + ", ".join(missing), file=sys.stderr)
        return 2
    origins = frozenset(
        o.strip().rstrip("/") for o in os.environ["SERENE_WEB_ORIGINS"].split(",") if o.strip()
    )

    dsn = os.environ["SUPABASE_DB_URL"]
    clock = SystemClock()
    # Every admitted decision also publishes serene.projection_state (#87), so
    # the web app sees the lifecycle move only once the kernel has recorded it.
    ledger = postgres_ledger(dsn, clock, telemetry=build_telemetry("serene-web-approvals"))
    app = make_approvals_app(
        WebApprovalChannel(ledger, clock),
        SupabaseSessionVerifier(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"]),
        WebPrincipals(PostgresGuardianRegistry(dsn), web_bindings_from_env()),
        allowed_origins=origins,
    )
    with make_server(args.host, args.port, app) as server:
        print(f"serene web approvals on http://{args.host}:{args.port}{PATH}")
        server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
