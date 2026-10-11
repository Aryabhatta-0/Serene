"""Privacy-safe telemetry that can never affect correctness (issue #52)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from serene.adapters.neatlogs_sink import build_telemetry
from serene.ledger import EventLedger
from serene.observability import RecordingSink, SafeTelemetry, redact
from serene.testing import SyntheticFamily

KEY = b"test-pseudonym-key"


def test_redaction_drops_free_text_and_unknown_keys() -> None:
    out = redact(
        {
            "event_type": "OBSERVATION_REPORTED",
            "reason_codes": ("LEVEL_SKIP", "UNVERIFIED_EVIDENCE"),
            "statement": "Maya cried at pickup",  # not allow-listed
            "decision": "Maya cried at pickup",  # allow-listed key, prose value
            "child_name": "Maya",
            "sequence": 4,
        },
        pseudonym_key=KEY,
    )
    assert out == {
        "event_type": "OBSERVATION_REPORTED",
        "reason_codes": "LEVEL_SKIP,UNVERIFIED_EVIDENCE",
        "sequence": 4,
    }


def test_child_ids_are_pseudonymized_or_dropped() -> None:
    child = "chd_" + "1" * 32
    with_key = redact({"child_id": child}, pseudonym_key=KEY)
    assert with_key["child_ref"].startswith("cref_") and child not in str(with_key)
    assert redact({"child_id": child}, pseudonym_key=None) == {}


class ExplodingSink:
    def emit(self, name: str, attributes: Mapping[str, Any]) -> None:
        raise RuntimeError("telemetry backend down")


def test_sink_failure_never_changes_ledger_outcomes() -> None:
    healthy = SyntheticFamily(seed="obs")
    broken = SyntheticFamily(seed="obs")
    broken.ledger = EventLedger(
        broken.store,
        broken.clock,
        telemetry=SafeTelemetry(ExplodingSink(), pseudonym_key=KEY),
        new_event_id=lambda: broken.new_id("evt"),
    )
    healthy.ledger = EventLedger(
        healthy.store, healthy.clock, new_event_id=lambda: healthy.new_id("evt")
    )
    for fam in (healthy, broken):
        fam.observe("fine day", day=0)
    a = [e.event_hash for e in healthy.ledger.get_events_for_child(healthy.child_id)]
    b = [e.event_hash for e in broken.ledger.get_events_for_child(broken.child_id)]
    assert a == b


def test_ledger_telemetry_carries_only_opaque_ids() -> None:
    sink = RecordingSink()
    fam = SyntheticFamily(seed="trace")
    fam.ledger = EventLedger(
        fam.store,
        fam.clock,
        telemetry=SafeTelemetry(sink, pseudonym_key=KEY),
        new_event_id=lambda: fam.new_id("evt"),
    )
    fam.observe("Long tearful pickup at the daycare door", day=0)
    assert [name for name, _ in sink.records] == ["ledger.append", "ledger.append"]
    blob = repr(sink.records)
    assert "tearful" not in blob and fam.child_id not in blob


def test_build_telemetry_without_a_key_is_a_noop(monkeypatch: Any) -> None:
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    telemetry = build_telemetry()
    telemetry.emit("ledger.append", {"event_type": "X"})
    assert telemetry.dropped == 0
