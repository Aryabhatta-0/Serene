"""Deterministic canonicalization and hashing (issue #4)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from serene.domain.canonical import (
    CanonicalizationError,
    canonical_digest,
    canonical_json,
    format_timestamp,
)
from serene.domain.values import EpistemicLevel, VerificationStatus
from serene.lineage.hashing import compute_event_hash

FIXED_VECTOR = {
    "z": [3, "b", None, True],
    "a": {"y": "ü", "x": 1},
    "level": EpistemicLevel.PATTERN,
    "status": VerificationStatus.VERIFIED,
    "at": datetime(2026, 9, 1, 10, 30, tzinfo=timezone(timedelta(hours=2))),
}
FIXED_BYTES = (
    '{"a":{"x":1,"y":"ü"},"at":"2026-09-01T08:30:00.000000Z","level":2,'
    '"status":"VERIFIED","z":[3,"b",null,true]}'
).encode()


def test_fixed_vector_bytes_and_digest() -> None:
    assert canonical_json(FIXED_VECTOR) == FIXED_BYTES
    assert canonical_digest(FIXED_VECTOR) == hashlib.sha256(FIXED_BYTES).hexdigest()
    # Pinned so an accidental change to the canonical form is caught in review.
    assert (
        canonical_digest(FIXED_VECTOR)
        == "d0dd081a226adcb29edda2f9b38c6ba4011d5a71a8ff208f8f8a0c08808a10ce"
    )


def test_key_order_does_not_matter() -> None:
    a = {"b": 1, "a": {"d": 2, "c": 3}}
    b = {"a": {"c": 3, "d": 2}, "b": 1}
    assert canonical_json(a) == canonical_json(b)


@pytest.mark.parametrize(
    "bad",
    [
        {"x": 0.1},
        {"x": float("nan")},
        {"x": "nul\x00byte"},
        {"x": 2**60},
        {1: "non-string key"},
        {"x": datetime(2026, 1, 1)},
        {"x": b"bytes"},
    ],
)
def test_non_canonicalizable_values_are_rejected(bad: Any) -> None:
    with pytest.raises(CanonicalizationError):
        canonical_json(bad)


def test_timestamps_normalize_to_utc_microseconds() -> None:
    local = datetime(2026, 3, 1, 1, 0, 0, 5, tzinfo=timezone(timedelta(hours=-5)))
    assert format_timestamp(local) == "2026-03-01T06:00:00.000005Z"
    assert format_timestamp(local.astimezone(UTC)) == format_timestamp(local)


def test_event_hash_is_reproducible(ladder: dict[str, Any]) -> None:
    fam = ladder["family"]
    for event in fam.ledger.get_events_for_child(fam.child_id):
        assert compute_event_hash(event) == event.event_hash
        assert canonical_digest(event.payload) == event.payload_hash


def test_same_scenario_produces_identical_ledger_hashes() -> None:
    from serene.testing import build_full_ladder

    first = build_full_ladder(seed="determinism")["family"]
    second = build_full_ladder(seed="determinism")["family"]
    a = [e.event_hash for e in first.ledger.get_events_for_child(first.child_id)]
    b = [e.event_hash for e in second.ledger.get_events_for_child(second.child_id)]
    assert a == b
