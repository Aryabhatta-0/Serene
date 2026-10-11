"""Serene Telegram ingress server (branch A).

    uv run python app/telegram/webhook_server.py --port 8787

Serves `POST /telegram` for Telegram Update JSON carrying the
`X-Telegram-Bot-Api-Secret-Token` header (Telegram webhook mode, or a Hermes
gateway relay that forwards updates verbatim). Fails closed at start-up unless
every required piece is configured; it never falls back to an in-memory
ledger, an unauthenticated endpoint or a model-free "approval".

Required environment (see .env.example): SUPABASE_DB_URL, TELEGRAM_WEBHOOK_SECRET,
SERENE_TELEGRAM_BINDINGS, HERMES_API_SERVER_KEY (+ HERMES_API_BASE_URL).
Optional: TELEGRAM_BOT_TOKEN (outbound prompts), SERENE_BROWSER_ALLOWED_DOMAINS,
NEATLOGS_API_KEY / SERENE_TELEMETRY_PSEUDONYM_KEY (privacy-safe traces).
"""

from __future__ import annotations

import argparse
import os
import sys
from wsgiref.simple_server import make_server


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    from serene.adapters.browser import HermesBrowser, SafeHttpsFetcher
    from serene.adapters.clock import SystemClock
    from serene.adapters.hermes import HermesAgentRuntime, transport_from_env
    from serene.adapters.neatlogs_sink import build_telemetry
    from serene.adapters.postgres import PostgresEventStore
    from serene.adapters.telegram import (
        BotApiOutbox,
        InMemoryPromptRegistry,
        TelegramChannel,
        bindings_from_env,
    )
    from serene.adapters.telegram.wsgi import make_wsgi_app
    from serene.evidence.service import EvidenceService
    from serene.evidence.verifier import IndependentEvidenceVerifier
    from serene.investigation.assembly import KernelActors, build_stack
    from serene.ledger.service import EventLedger

    missing = [
        name
        for name in ("SUPABASE_DB_URL", "TELEGRAM_WEBHOOK_SECRET", "SERENE_TELEGRAM_BINDINGS")
        if not os.environ.get(name)
    ]
    transport = transport_from_env()
    if transport is None:
        missing.append("HERMES_API_SERVER_KEY")
    if missing:
        print("refusing to start; missing: " + ", ".join(missing), file=sys.stderr)
        return 2

    clock = SystemClock()
    telemetry = build_telemetry("serene-telegram")
    ledger = EventLedger(
        PostgresEventStore(os.environ["SUPABASE_DB_URL"]), clock, telemetry=telemetry
    )

    def runtime_factory(retriever, actors):  # type: ignore[no-untyped-def]
        return HermesAgentRuntime(
            transport,
            context_provider=lambda task: retriever.retrieve(
                ledger.replay_events(task.child_id),
                child_id=task.child_id,
                investigation_id=task.investigation_id,
                focus_ids=task.context_entity_ids,
                now=clock.now(),
            ),
            clock=clock,
            agent_actor=actors.agent,
            telemetry=telemetry,
        )

    allowlist = tuple(
        d.strip().lower()
        for d in os.environ.get("SERENE_BROWSER_ALLOWED_DOMAINS", "").split(",")
        if d.strip()
    )
    actors = KernelActors.derived()
    # Web evidence only with an explicit allowlist; without one every BROWSE
    # candidate is UNSAFE and the investigation asks the parent instead.
    evidence = (
        EvidenceService(
            ledger,
            clock,
            browser=HermesBrowser(
                transport, clock=clock, observer=actors.system, telemetry=telemetry
            ),
            verifier=IndependentEvidenceVerifier(clock, fetcher=SafeHttpsFetcher()),
            system_actor=actors.system,
            verifier_actor=actors.verifier,
            telemetry=telemetry,
        )
        if allowlist
        else None
    )
    stack = build_stack(
        ledger,
        clock,
        runtime_factory=runtime_factory,
        telemetry=telemetry,
        browse_allowlist=allowlist,
        evidence=evidence,
        actors=actors,
    )
    bindings = bindings_from_env()
    prompts = InMemoryPromptRegistry()
    channel = TelegramChannel(
        webhook_secret=os.environ["TELEGRAM_WEBHOOK_SECRET"],
        bindings=bindings,
        ledger=ledger,
        clock=clock,
        ingestion=stack.ingestion,
        prompts=prompts,
        telemetry=telemetry,
    )
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        BotApiOutbox(os.environ["TELEGRAM_BOT_TOKEN"])  # validated; prompts are sent by jobs
    with make_server(args.host, args.port, make_wsgi_app(channel)) as server:
        print(f"serene telegram ingress on http://{args.host}:{args.port}/telegram")
        server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
