"""EvidenceBrowser and EvidenceVerifier ports (issues #15, #16).

The browser acquires; it never verifies. The verifier is deterministic and
independent of the browser and the model; only its verdict can mark evidence
VERIFIED or REJECTED in the ledger.
"""

from __future__ import annotations

from typing import Annotated, Literal, Protocol, runtime_checkable

from pydantic import Field, StringConstraints

from serene.domain.base import (
    ChildId,
    EvidenceId,
    EvidenceRequestId,
    KernelModel,
    ReasonCode,
    ShortText,
    Tag,
)
from serene.domain.entities import Evidence
from serene.domain.events import VerificationCheck

Domain = Annotated[str, StringConstraints(pattern=r"^[a-z0-9.\-]{1,253}$")]
ForbiddenBrowserAction = Literal[
    "submit_form", "login", "purchase", "download", "upload", "send_message"
]


class EvidenceBrowseRequest(KernelModel):
    request_id: EvidenceRequestId
    child_id: ChildId
    goal: ShortText
    allowed_domains: tuple[Domain, ...] = Field(min_length=1, max_length=16)
    requested_fields: tuple[Tag, ...] = Field(min_length=1, max_length=16)
    max_actions: int = Field(ge=1, le=50)
    forbidden_actions: tuple[ForbiddenBrowserAction, ...] = (
        "submit_form",
        "login",
        "purchase",
        "download",
        "upload",
        "send_message",
    )
    # Additive (branch A): what the evidence must be about and how fresh it must
    # be. The verifier checks both; the browser never decides validity.
    subject: Tag | None = None
    max_age_days: int | None = Field(default=None, ge=1, le=3650)


class EvidenceBrowseResult(KernelModel):
    request_id: EvidenceRequestId
    status: Literal["ACQUIRED", "NOT_FOUND", "BLOCKED", "BUDGET_EXHAUSTED", "FAILED"]
    evidence: tuple[Evidence, ...] = Field(default=(), max_length=16)
    actions_used: int = Field(ge=0)
    # Additive (branch A): machine-readable why (e.g. FORBIDDEN_TOOL:browser_type).
    reason_codes: tuple[ReasonCode, ...] = Field(default=(), max_length=32)


class VerificationVerdict(KernelModel):
    evidence_id: EvidenceId
    verdict: Literal["VERIFIED", "REJECTED"]
    checks_passed: tuple[VerificationCheck, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()
    verifier_version: ShortText


@runtime_checkable
class EvidenceBrowser(Protocol):
    def acquire(self, request: EvidenceBrowseRequest) -> EvidenceBrowseResult: ...


@runtime_checkable
class EvidenceVerifier(Protocol):
    def verify(self, evidence: Evidence, request: EvidenceBrowseRequest) -> VerificationVerdict: ...
