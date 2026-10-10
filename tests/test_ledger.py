"""Append-only ledger semantics (issues #3, #5)."""

from __future__ import annotations

import itertools
from typing import Any

import pytest

from serene.adapters.in_memory_event_store import InMemoryEventStore
from serene.domain.base import new_id
from serene.domain.events import (
    EVENT_TAXONOMY,
    GENESIS_HASH,
    ApprovalGranted,
    EventType,
    HypothesisSuperseded,
    ObservationReported,
)
from serene.domain.values import SourceKind, VerificationStatus
from serene.ledger import AdmissionRejected, EventLedger
from serene.ports.event_store import ConcurrencyConflict, EventStore
from serene.testing import SyntheticFamily


def test_append_and_read_back(family: SyntheticFamily) -> None:
    evidence = family.report("Napped for an hour")
    events = family.ledger.get_events_for_child(family.child_id)
    assert len(events) == 1
    event = events[0]
    assert event.sequence == 1 and event.prev_event_hash == GENESIS_HASH
    assert event.typed_payload() == ObservationReported(evidence=evidence)
    assert event.source.kind is SourceKind.TELEGRAM
    assert event.actor == family.parent
    assert event.recorded_at >= event.occurred_at


def test_every_event_links_to_its_predecessor(ladder: dict[str, Any]) -> None:
    fam = ladder["family"]
    events = fam.ledger.get_events_for_child(fam.child_id)
    for prev, event in itertools.pairwise(events):
        assert event.sequence == prev.sequence + 1
        assert event.prev_event_hash == prev.event_hash


def test_no_update_or_delete_paths_exist() -> None:
    for obj in (EventLedger, InMemoryEventStore, EventStore):
        names = {n.lower() for n in dir(obj)}
        assert not any(
            verb in name for name in names for verb in ("update", "delete", "remove", "truncate")
        ), obj


def test_changed_understanding_appends_instead_of_mutating(ladder: dict[str, Any]) -> None:
    fam: SyntheticFamily = ladder["family"]
    before = list(fam.ledger.get_events_for_child(fam.child_id))
    rival = fam.hypothesis(
        ladder["investigation"], (ladder["pattern"],), "Hunger at pickup drives the distress"
    )
    fam.append(
        fam.draft(
            EventType.HYPOTHESIS_SUPERSEDED,
            fam.system,
            HypothesisSuperseded(
                hypothesis_id=ladder["hypothesis"].hypothesis_id,
                superseded_by=rival.hypothesis_id,
                reason="caregiver notes that snacks change the picture",
            ),
        )
    )
    after = fam.ledger.get_events_for_child(fam.child_id)
    assert list(after[: len(before)]) == before  # history untouched
    record = fam.state().entities[ladder["hypothesis"].hypothesis_id]
    assert record.status.value == "SUPERSEDED" and record.superseded_by == rival.hypothesis_id
    assert record.entity == ladder["hypothesis"]  # superseded object preserved


def test_unknown_ancestor_is_rejected(family: SyntheticFamily) -> None:
    evidence = family.report("ok")
    draft = family.draft(
        EventType.OBSERVATION_REPORTED,
        family.parent,
        ObservationReported(evidence=evidence.model_copy(update={"evidence_id": new_id("evd")})),
        status=VerificationStatus.VERIFIED,
        source=evidence.source,
        derived_from=(new_id("evt"),),
    )
    with pytest.raises(AdmissionRejected) as info:
        family.ledger.append_event(draft)
    assert [r for r in info.value.reason_codes if r.startswith("UNKNOWN_ANCESTOR")]


def test_payload_must_match_registered_schema(family: SyntheticFamily) -> None:
    evidence = family.report("ok")
    draft = family.draft(
        EventType.EVIDENCE_ACQUIRED,  # registered payload is EvidenceAcquired
        family.system,
        ObservationReported(evidence=evidence),
        status=VerificationStatus.UNVERIFIED,
    )
    with pytest.raises(AdmissionRejected, match="PAYLOAD_SCHEMA_MISMATCH"):
        family.ledger.append_event(draft)


def test_every_event_type_has_a_payload_schema_and_actor_set() -> None:
    assert set(EVENT_TAXONOMY) == set(EventType)
    for spec in EVENT_TAXONOMY.values():
        assert spec.actors and spec.statuses
        assert spec.payload.model_fields["schema_version"].default == 1


def test_agent_cannot_append_authority_events(ladder: dict[str, Any]) -> None:
    fam: SyntheticFamily = ladder["family"]
    authority = {
        EventType.APPROVAL_GRANTED,
        EventType.PROMOTION_GRANTED,
        EventType.EXPERIMENT_STARTED,
        EventType.EVIDENCE_VERIFIED,
        EventType.LEARNING_RECORDED,
        EventType.MEMORY_PATCH_COMMITTED,
    }
    for event_type in authority:
        assert "AGENT" not in {a.value for a in EVENT_TAXONOMY[event_type].actors}
    draft = fam.draft(
        EventType.APPROVAL_GRANTED,
        fam.agent,
        ApprovalGranted.model_validate(
            fam.grant_payload(ladder["experiment"], ladder["approval_id"]).model_dump()
        ),
        source=fam.source(SourceKind.TELEGRAM),
    )
    with pytest.raises(AdmissionRejected, match="ACTOR_NOT_PERMITTED:AGENT"):
        fam.ledger.append_event(draft)


def test_rejection_leaves_the_stream_unchanged(ladder: dict[str, Any]) -> None:
    fam: SyntheticFamily = ladder["family"]
    before = fam.ledger.get_events_for_child(fam.child_id)
    with pytest.raises(AdmissionRejected):
        fam.start(ladder["experiment"], ladder["approval_id"])  # approval already used
    assert fam.ledger.get_events_for_child(fam.child_id) == before


def test_stale_writer_gets_a_concurrency_conflict(family: SyntheticFamily) -> None:
    family.report("first")
    event = family.ledger.get_events_for_child(family.child_id)[0]
    with pytest.raises(ConcurrencyConflict):
        family.store.append(event, expected_prev_hash=GENESIS_HASH)


def test_unverified_report_from_unauthenticated_channel_cannot_claim_verified(
    family: SyntheticFamily,
) -> None:
    evidence = family.report("seed")
    forged = evidence.model_copy(update={"evidence_id": new_id("evd")})
    draft = family.draft(
        EventType.OBSERVATION_REPORTED,
        family.parent,
        ObservationReported(evidence=forged),
        status=VerificationStatus.VERIFIED,
        source=forged.source,
    )
    draft = draft.model_copy(update={"source": family.source(SourceKind.KERNEL)})
    with pytest.raises(AdmissionRejected) as info:
        family.ledger.append_event(draft)
    assert "UNAUTHENTICATED_CHANNEL" in info.value.reason_codes
    assert "SOURCE_MISMATCH" in info.value.reason_codes
