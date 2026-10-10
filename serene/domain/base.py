"""Strict base model, identifiers and time handling for the Domain Kernel.

Every authority-bearing structure in Serene is a frozen, strict Pydantic v2
model that rejects unknown fields. Identifiers are opaque, prefixed and minted
by trusted code (`new_id`), never by model text.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Final

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

SCHEMA_VERSION: Final = 1

# prefix -> entity kind. A prefix encodes the kind so lineage references can be
# type-checked without a lookup.
ID_PREFIXES: Final[dict[str, str]] = {
    "chd": "child",
    "act": "actor",
    "src": "source",
    "evt": "event",
    "evd": "evidence",
    "obs": "observation",
    "pat": "pattern",
    "hyp": "hypothesis",
    "inv": "investigation",
    "exp": "experiment",
    "trl": "trial",
    "out": "outcome",
    "lrn": "learning",
    "mpt": "memory_patch",
    "apr": "approval_request",
    "erq": "evidence_request",
}

_ID_RE = re.compile(r"^(?P<prefix>[a-z]{3})_[0-9a-f]{32}$")


def new_id(prefix: str) -> str:
    """Mint a fresh opaque identifier. Only trusted kernel/adapter code calls this."""
    if prefix not in ID_PREFIXES:
        raise ValueError(f"unknown id prefix: {prefix!r}")
    return f"{prefix}_{uuid.uuid4().hex}"


def id_prefix(value: str) -> str:
    match = _ID_RE.match(value)
    if match is None:
        raise ValueError(f"malformed id: {value!r}")
    return match.group("prefix")


def _id_validator(prefix: str) -> AfterValidator:
    def check(value: str) -> str:
        if id_prefix(value) != prefix:
            raise ValueError(f"expected a {prefix}_ id, got {value!r}")
        return value

    return AfterValidator(check)


def _any_entity_id(value: str) -> str:
    if id_prefix(value) not in ID_PREFIXES:
        raise ValueError(f"unknown id prefix in {value!r}")
    return value


_IdStr = Annotated[str, StringConstraints(min_length=36, max_length=36)]

ChildId = Annotated[_IdStr, _id_validator("chd")]
ActorId = Annotated[_IdStr, _id_validator("act")]
SourceId = Annotated[_IdStr, _id_validator("src")]
EventId = Annotated[_IdStr, _id_validator("evt")]
EvidenceId = Annotated[_IdStr, _id_validator("evd")]
ObservationId = Annotated[_IdStr, _id_validator("obs")]
PatternId = Annotated[_IdStr, _id_validator("pat")]
HypothesisId = Annotated[_IdStr, _id_validator("hyp")]
InvestigationId = Annotated[_IdStr, _id_validator("inv")]
ExperimentId = Annotated[_IdStr, _id_validator("exp")]
TrialId = Annotated[_IdStr, _id_validator("trl")]
OutcomeId = Annotated[_IdStr, _id_validator("out")]
LearningId = Annotated[_IdStr, _id_validator("lrn")]
MemoryPatchId = Annotated[_IdStr, _id_validator("mpt")]
ApprovalRequestId = Annotated[_IdStr, _id_validator("apr")]
EvidenceRequestId = Annotated[_IdStr, _id_validator("erq")]
EntityId = Annotated[_IdStr, AfterValidator(_any_entity_id)]

Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=500)]
LongText = Annotated[str, StringConstraints(min_length=1, max_length=8000)]
Tag = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
ReasonCode = Annotated[
    str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{0,63}(:[A-Za-z0-9_]{1,64})?$")
]


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_require_utc)]


class KernelModel(BaseModel):
    """Frozen, strict, closed-world base for every kernel structure."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        validate_default=True,
        ser_json_timedelta="iso8601",
    )
