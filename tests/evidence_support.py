"""Scripted browse replies, a fake independent fetcher and an evidence-service rig."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from serene.adapters.browser import HermesBrowser
from serene.adapters.hermes import wire_response
from serene.adapters.hermes.transport import HermesResponse, HermesToolCall
from serene.evidence.service import EvidenceService
from serene.evidence.verifier import FetchedPage, IndependentEvidenceVerifier

POLICY_URL = "https://example.org/policies/pickup"
EXCERPT = (
    "Daycare pickup policy. Children may be collected between 15:00-17:30. "
    "A snack is served at 14:30 every day."
)
PAGE_TEXT = "Welcome to Example Daycare. " + EXCERPT + " Contact the office for questions."


def tool(name: str, **arguments: Any) -> HermesToolCall:
    return HermesToolCall(
        call_id=f"call_{name}", name=name, arguments=json.dumps(arguments), output="(page text)"
    )


def capture(
    *,
    url: str = POLICY_URL,
    subject: str = "daycare_pickup",
    effective: date = date(2026, 9, 1),
    fields: Mapping[str, str] | None = None,
    excerpt: str = EXCERPT,
) -> dict[str, Any]:
    return {
        "url": url,
        "subject": subject,
        "effective_date": effective.isoformat(),
        "fields": dict(fields if fields is not None else {"pickup_window": "15:00-17:30"}),
        "excerpt": excerpt,
    }


def browse_reply(
    captures: Sequence[dict[str, Any]] | None = None,
    *,
    calls: Sequence[HermesToolCall] | None = None,
) -> HermesResponse:
    return wire_response(
        {"captures": list(captures if captures is not None else [capture()])},
        tool_calls=(
            calls
            if calls is not None
            else (
                tool("web_search", query="example daycare pickup"),
                tool("web_extract", urls=[POLICY_URL]),
            )
        ),
    )


@dataclass
class FakeFetcher:
    """Stands in for the verifier's own https read; records what it was asked."""

    pages: dict[str, str] = field(default_factory=lambda: {POLICY_URL: PAGE_TEXT})
    redirect: dict[str, str] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def fetch(self, url: str, allowed_domains: tuple[str, ...]) -> FetchedPage | None:
        self.calls.append(url)
        if url in self.redirect:
            return FetchedPage(url=self.redirect[url], text=self.pages.get(url, ""))
        text = self.pages.get(url)
        return None if text is None else FetchedPage(url=url, text=text)


def evidence_factory(
    fetcher: Any = None, *, pinned_sources: Sequence[str] = (), **kwargs: Any
) -> Any:
    """`make_investigation_rig(evidence=...)` hook: browser + verifier + service."""

    def build(family: Any, telemetry: Any, transport: Any) -> EvidenceService:
        browser = HermesBrowser(
            transport,
            clock=family.clock,
            observer=family.system,
            telemetry=telemetry,
            new_entity_id=family.new_id,
            pinned_sources=pinned_sources,
        )
        verifier = IndependentEvidenceVerifier(family.clock, fetcher=fetcher or FakeFetcher())
        return EvidenceService(
            family.ledger,
            family.clock,
            browser=browser,
            verifier=verifier,
            system_actor=family.system,
            verifier_actor=family.verifier,
            telemetry=telemetry,
            new_source_id=lambda: family.new_id("src"),
            **kwargs,
        )

    return build
