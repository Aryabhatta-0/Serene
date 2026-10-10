"""Strict schema behaviour of the Domain Kernel (issue #1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from serene.domain import (
    ActorKind,
    ActorRef,
    DerivationMethod,
    EventDraft,
    Evidence,
    Learning,
    Provenance,
    ReviewMetadata,
    Scope,
    SourceKind,
    SourceRef,
    ValidityWindow,
)
from serene.domain.base import new_id


def _roundtrip(model: BaseModel) -> None:
    again = type(model).model_validate_json(model.model_dump_json())
    assert again == model


def test_every_ladder_entity_round_trips(ladder: dict[str, Any]) -> None:
    fam = ladder["family"]
    state = fam.state()
    kinds = set()
    for record in state.entities.values():
        _roundtrip(record.entity)
        kinds.add(type(record.entity).__name__)
    assert {
        "Evidence",
        "Observation",
        "Pattern",
        "Hypothesis",
        "Investigation",
        "Experiment",
        "Outcome",
        "Learning",
    } <= kinds


def test_schema_version_is_present_and_stable(ladder: dict[str, Any]) -> None:
    for record in ladder["family"].state().entities.values():
        assert record.entity.schema_version == 1
        assert record.entity.provenance.schema_version == 1


def test_unknown_fields_are_rejected(ladder: dict[str, Any]) -> None:
    observation = ladder["observations"][0]
    data = observation.model_dump(mode="json")
    data["confidence"] = 0.99  # a model-invented authority field
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        type(observation).model_validate(data)


def test_missing_required_field_is_rejected(ladder: dict[str, Any]) -> None:
    data = ladder["hypothesis"].model_dump(mode="json")
    del data["falsification_criteria"]
    with pytest.raises(ValidationError):
        type(ladder["hypothesis"]).model_validate_json(_json(data))


def test_invalid_enum_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ActorRef.model_validate_json('{{"kind": "ADMIN", "actor_id": "{}"}}'.format(new_id("act")))


def test_ids_are_prefix_typed() -> None:
    with pytest.raises(ValidationError):
        ActorRef(kind=ActorKind.PARENT, actor_id=new_id("chd"))
    with pytest.raises(ValueError, match="unknown id prefix"):
        new_id("zzz")


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        Provenance(
            created_by=ActorRef(kind=ActorKind.PARENT, actor_id=new_id("act")),
            created_at=datetime(2026, 1, 1),
            method=DerivationMethod.PARENT_REPORT,
        )


def test_model_derived_objects_must_name_their_model() -> None:
    agent = ActorRef(kind=ActorKind.AGENT, actor_id=new_id("act"))
    with pytest.raises(ValidationError, match="record the model"):
        Provenance(
            created_by=agent, created_at=datetime.now(UTC), method=DerivationMethod.MODEL_INFERENCE
        )
    parent = ActorRef(kind=ActorKind.PARENT, actor_id=new_id("act"))
    with pytest.raises(ValidationError, match="AGENT actor"):
        Provenance(
            created_by=parent, created_at=datetime.now(UTC), method=DerivationMethod.MODEL_INFERENCE
        )


def test_derived_entities_require_lineage(ladder: dict[str, Any]) -> None:
    observation = ladder["observations"][0]
    stripped = observation.provenance.model_copy(update={"derived_from": (), "source_ids": ()})
    data = observation.model_dump()
    data["provenance"] = stripped
    with pytest.raises(ValidationError, match="derived_from"):
        type(observation)(**data)


def test_raw_evidence_cannot_claim_parents(family: Any) -> None:
    evidence: Evidence = family.report("Sleepy at breakfast")
    data = evidence.model_dump()
    data["provenance"] = evidence.provenance.model_copy(update={"derived_from": (new_id("obs"),)})
    with pytest.raises(ValidationError, match="raw evidence"):
        Evidence(**data)


def test_external_sources_need_uri_and_digest() -> None:
    with pytest.raises(ValidationError, match="external sources"):
        SourceRef(kind=SourceKind.BROWSER, source_id=new_id("src"))
    with pytest.raises(ValidationError, match="only external"):
        SourceRef(kind=SourceKind.TELEGRAM, source_id=new_id("src"), uri="https://example.org")


def test_level5_learning_requires_scope_validity_and_parent_review(ladder: dict[str, Any]) -> None:
    learning: Learning = ladder["learning"]
    now = learning.validity.valid_from
    with pytest.raises(ValidationError):
        ValidityWindow(valid_from=now, review_after=now - timedelta(days=1))
    with pytest.raises(ValidationError):
        Scope(child_id=learning.child_id, contexts=())
    with pytest.raises(ValidationError, match="reviewed by the parent"):
        ReviewMetadata(reviewer=ladder["family"].agent, retest_triggers=("x",))
    data = learning.model_dump()
    del data["validity"]
    with pytest.raises(ValidationError):
        Learning(**data)


def test_event_type_vocabulary_is_closed(family: Any) -> None:
    evidence = family.report("ok")
    draft = family.draft(
        family.ledger.get_events_for_child(family.child_id)[0].event_type,
        family.parent,
        family.ledger.get_events_for_child(family.child_id)[0].typed_payload(),
    )
    data = draft.model_dump()
    data["event_type"] = "BELIEF_OVERWRITTEN"
    with pytest.raises(ValidationError):
        EventDraft(**data)
    assert evidence.evidence_id


def _json(data: dict[str, Any]) -> str:
    import json

    return json.dumps(data)
