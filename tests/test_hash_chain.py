"""Tamper detection over the hash chain, including property-based invariants (issue #4)."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from serene.domain.canonical import canonical_digest
from serene.domain.events import DomainEvent
from serene.domain.values import VerificationStatus
from serene.lineage.chain import LedgerIntegrityError, verify_hash_chain
from serene.testing import SyntheticFamily


def _events(ladder: dict[str, Any]) -> list[DomainEvent]:
    fam = ladder["family"]
    return list(fam.ledger.get_events_for_child(fam.child_id))


def test_intact_chain_verifies(ladder: dict[str, Any]) -> None:
    result = verify_hash_chain(_events(ladder))
    assert result.ok and result.checked == len(_events(ladder))


def test_payload_mutation_is_detected_at_its_index(ladder: dict[str, Any]) -> None:
    events = _events(ladder)
    target = 3
    payload = dict(events[target].payload)
    payload["observation"] = {**payload["observation"], "statement": "rewritten history"}
    events[target] = events[target].model_copy(update={"payload": payload})
    result = verify_hash_chain(events)
    assert not result.ok
    assert result.failure_index == target
    assert result.reason == "PAYLOAD_HASH_MISMATCH"


def test_rehashed_payload_still_breaks_event_hash(ladder: dict[str, Any]) -> None:
    """An attacker who also recomputes payload_hash is caught by event_hash."""
    events = _events(ladder)
    target = next(i for i, e in enumerate(events) if e.event_type == "PATTERN_PROPOSED")
    payload = dict(events[target].payload)
    payload["schema_version"] = 1
    payload["pattern"] = {**payload["pattern"], "description": "forged"}
    events[target] = events[target].model_copy(
        update={"payload": payload, "payload_hash": canonical_digest(payload)}
    )
    result = verify_hash_chain(events)
    assert (result.ok, result.failure_index, result.reason) == (
        False,
        target,
        "EVENT_HASH_MISMATCH",
    )


def test_broken_link_is_detected(ladder: dict[str, Any]) -> None:
    events = _events(ladder)
    events[7] = events[7].model_copy(update={"prev_event_hash": "f" * 64})
    result = verify_hash_chain(events)
    assert (result.failure_index, result.reason) == (7, "PREV_HASH_MISMATCH")


def test_reordering_and_deletion_are_detected(ladder: dict[str, Any]) -> None:
    events = _events(ladder)
    swapped = [*events[:2], events[3], events[2], *events[4:]]
    assert verify_hash_chain(swapped).failure_index == 2
    deleted = [*events[:4], *events[5:]]
    result = verify_hash_chain(deleted)
    assert (result.failure_index, result.reason) == (4, "SEQUENCE_GAP")


def test_metadata_mutation_is_detected(ladder: dict[str, Any]) -> None:
    events = _events(ladder)
    events[0] = events[0].model_copy(update={"actor": ladder["family"].agent})
    assert verify_hash_chain(events).reason == "EVENT_HASH_MISMATCH"


def test_ledger_refuses_reads_and_appends_on_a_tampered_stream(ladder: dict[str, Any]) -> None:
    fam = ladder["family"]
    stream = fam.store._streams[fam.child_id]
    stream[1] = stream[1].model_copy(update={"verification_status": VerificationStatus.REJECTED})
    with pytest.raises(LedgerIntegrityError):
        fam.ledger.get_events_for_child(fam.child_id)
    with pytest.raises(LedgerIntegrityError):
        fam.report("this must not be appended to a tampered stream")
    assert not fam.ledger.verify_hash_chain(fam.child_id).ok


# ------------------------------------------------------------------ properties
_reports = st.lists(
    st.text(
        alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
        min_size=1,
        max_size=40,
    ),
    min_size=1,
    max_size=8,
)


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(contents=_reports, data=st.data())
def test_any_single_mutation_is_detected_at_or_before_its_index(
    contents: list[str], data: st.DataObject
) -> None:
    """Invariant: an appended stream verifies; mutating any one event breaks verification
    exactly at that event (never later, never silently)."""
    fam = SyntheticFamily(seed="property")
    for text in contents:
        fam.report(text)
    events = list(fam.store.read_stream(fam.child_id))
    assert verify_hash_chain(events).ok

    index = data.draw(st.integers(min_value=0, max_value=len(events) - 1))
    field = data.draw(st.sampled_from(["payload", "occurred_at", "derived_from", "event_hash"]))
    original = events[index]
    if field == "payload":
        payload = dict(original.payload)
        payload["evidence"] = {**payload["evidence"], "content": original.event_id}
        mutated = original.model_copy(update={"payload": payload})
    elif field == "occurred_at":
        mutated = original.model_copy(
            update={"occurred_at": original.occurred_at.replace(microsecond=1)}
        )
    elif field == "derived_from":
        mutated = original.model_copy(update={"derived_from": (fam.new_id("evt"),)})
    else:
        mutated = original.model_copy(update={"event_hash": "0" * 64})
    events[index] = mutated
    result = verify_hash_chain(events)
    assert not result.ok
    assert result.failure_index == index
