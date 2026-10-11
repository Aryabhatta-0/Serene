"""Micro-question answers as raw evidence (issue #40).

A parent's tap on YES / NO / UNSURE is recorded verbatim as a channel-
authenticated PARENT_REPORT whose content is this canonical JSON document. It
answers exactly one kernel-issued EVIDENCE_REQUESTED and is never an approval.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import ValidationError

from serene.domain.base import EvidenceRequestId, KernelModel, ShortText
from serene.domain.canonical import canonical_json


class MicroAnswerValue(StrEnum):
    YES = "YES"
    NO = "NO"
    UNSURE = "UNSURE"


class MicroAnswer(KernelModel):
    kind: Literal["micro_answer"] = "micro_answer"
    request_id: EvidenceRequestId
    question: ShortText
    answer: MicroAnswerValue


def encode_micro_answer(answer: MicroAnswer) -> str:
    return canonical_json(answer).decode("utf-8")


def decode_micro_answer(content: str) -> MicroAnswer | None:
    """Parse evidence content as a micro-answer; None for anything else (never guesses)."""
    try:
        return MicroAnswer.model_validate_json(content)
    except ValidationError:
        return None
