"""Runtime trace coverage and central redaction (issue #52, branch-A surface)."""

from __future__ import annotations

from typing import Any

import pytest

import eval.scenarios.runtime_scenarios as rs
from serene.observability.telemetry import RecordingSink, SafeTelemetry
from tests.evidence_support import EXCERPT, POLICY_URL
from tests.runtime_support import PSEUDONYM_KEY

# #52 dimension -> the trace events that carry it.
REQUIRED: dict[str, set[str]] = {
    "context ids": {"context.retrieve"},
    "hypotheses": {"investigation.hypotheses"},
    "tool selection/args": {"evidence.select", "browser.acquire"},
    "browser actions": {"browser.acquire"},
    "verification": {"evidence.verdict"},
    "failures/retries": {"evidence.acquisition_failed", "runtime.call", "browser.call"},
    "state": {"investigation.transition", "ledger.append"},
    "tokens/latency/cost": {"runtime.call", "runtime.run"},
}


@pytest.fixture(scope="module")
def traced() -> list[Any]:
    rigs: list[Any] = []
    original = rs.make_investigation_rig

    def spy(*args: Any, **kwargs: Any) -> Any:
        rig = original(*args, **kwargs)
        rigs.append(rig)
        return rig

    rs.make_investigation_rig = spy  # type: ignore[assignment]
    try:
        for sid in ("browse_verified", "browser_flaky_restart", "ask_discriminates"):
            rs.SCENARIOS[sid].run_serene()
    finally:
        rs.make_investigation_rig = original  # type: ignore[assignment]
    return rigs


def _records(rigs: list[Any]) -> list[tuple[str, dict[str, Any]]]:
    return [r for rig in rigs for r in rig.sink.records]


def test_every_required_dimension_is_traced(traced: list[Any]) -> None:
    names = {name for name, _ in _records(traced)}
    missing = {dim: events - names for dim, events in REQUIRED.items() if events - names}
    assert missing == {}


def test_trace_attributes_answer_the_operator_questions(traced: list[Any]) -> None:
    by_name: dict[str, list[dict[str, Any]]] = {}
    for name, attrs in _records(traced):
        by_name.setdefault(name, []).append(attrs)
    browse = by_name["browser.acquire"]
    assert any(a.get("tool") == "web_extract,web_search" for a in browse)
    assert any(a.get("domain") == "example.org" for a in browse)
    assert all("max_actions" in a and "action_count" in a for a in browse)
    calls = by_name["runtime.call"]
    assert all("duration_ms" in a for a in calls if a["status"] == "OK")
    browser_calls = by_name["browser.call"]
    assert any(
        a.get("retryable") is True and a.get("error_type") == "TRANSIENT"
        for a in browser_calls
        if a["status"] == "FAILED"
    )
    assert any("duration_ms" in a for a in browser_calls if a["status"] == "OK")
    runs = by_name["runtime.run"]
    assert all({"input_tokens", "output_tokens", "cost_known"} <= set(a) for a in runs)
    verdicts = by_name["evidence.verdict"]
    assert any(a["decision"] == "VERIFIED" and a.get("checks_passed") for a in verdicts)
    assert all("child_id" not in a for _, a in _records(traced))


def test_no_child_pii_page_text_or_raw_identifiers_reach_traces(traced: list[Any]) -> None:
    blob = repr(_records(traced))
    sensitive = [text for text, _ in rs.REPORTS] + [EXCERPT, "15:00-17:30", POLICY_URL]
    sensitive += [rig.family.child_id for rig in traced]
    sensitive += ["/policies/pickup", rs.QUESTION]
    leaked = [s for s in sensitive if s in blob]
    assert leaked == []


def test_redaction_is_central_and_cannot_be_bypassed_by_a_caller() -> None:
    sink = RecordingSink()
    telemetry = SafeTelemetry(sink, pseudonym_key=PSEUDONYM_KEY)
    child = "chd_" + "a" * 32
    telemetry.emit(
        "runtime.call",
        {
            "child_id": child,
            "content": "Pickup was awful, crying at the door",  # not an allowed key
            "reason_codes": ("Pickup was awful",),  # allowed key, free-text value
            "domain": "https://example.org/policies/pickup?child=Sam",  # URL, not a host
            "status": "OK",
        },
    )
    ((_, attrs),) = sink.records
    assert attrs.get("status") == "OK"
    assert "content" not in attrs and "reason_codes" not in attrs
    assert "child_id" not in attrs and attrs.get("child_ref") not in (None, child)
    assert "Sam" not in repr(attrs) and "domain" not in attrs
