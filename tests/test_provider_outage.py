"""Provider outage is attributed to the provider, not the model (issue #53).

Observed live on 2026-10-10 (eval/reports/local/live/before-*): the Hermes API
server answered every call with a provider-auth failure envelope (HTTP 200,
status "completed", zero usage, a "Provider authentication failed" line). Serene
read that line as model output: each report cost two calls (one "repair"), the
trace said `runtime.call status=OK` and blamed the model (`WIRE_NOT_JSON`), the
structuring failure was marked retryable, and browse attempts were scheduled
for retry as MALFORMED. These tests replay the captured payload through the
production parser and pin the corrected behaviour.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from serene.adapters.hermes import parse_responses_payload
from serene.adapters.hermes.transport import HermesRequest, HermesResponse
from serene.domain.events import EventType
from tests.investigation_support import TelegramScript, make_investigation_rig

PAYLOAD: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures" / "hermes_provider_auth_failure.json").read_text("utf-8")
)


class ReplayedOutage:
    """Every call gets the captured live payload, parsed by the production parser."""

    def __init__(self) -> None:
        self.requests: list[HermesRequest] = []

    def respond(self, request: HermesRequest) -> HermesResponse:
        self.requests.append(request)
        return parse_responses_payload(PAYLOAD)


def test_outage_costs_one_call_and_names_the_provider_in_the_trace() -> None:
    transport = ReplayedOutage()
    rig = make_investigation_rig("outage", transport=transport)
    outcome = TelegramScript(rig).say("Pickup was awful, crying at the door").outcome
    assert outcome == "RECORDED_UNSTRUCTURED"
    assert len(transport.requests) == 1  # no "repair" of a reply no model wrote
    calls = [a for name, a in rig.sink.records if name == "runtime.call"]
    assert [(c["status"], c.get("error_type"), c.get("retryable")) for c in calls] == [
        ("FAILED", "AUTH", False)
    ]
    (run,) = [a for name, a in rig.sink.records if name == "runtime.run"]
    assert "WIRE_" not in str(run["reason_codes"]) and "TRANSPORT_AUTH" in str(run["reason_codes"])
    types = [e.event_type for e in rig.events()]
    assert EventType.OBSERVATION_REPORTED in types  # the parent's words are kept verbatim
    assert EventType.OBSERVATION_STRUCTURED not in types
