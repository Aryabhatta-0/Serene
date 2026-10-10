"""Dream Critic, provenance verifier and memory Promotion Gate (issues #29, #31, #32).

`review_patch` is a pure, deterministic function of (patch, ledger state, now).
The ledger's admission recomputes it for MEMORY_PATCH_REVIEWED and again for
MEMORY_PATCH_COMMITTED, so neither a model nor a buggy caller can record a
passing verdict the Critic would not produce. Four independent checks must all
pass:

    DOCUMENT_FORMAT       full-context diff, canonical document, kind/path, level
    LINEAGE               provenance verifier: complete verified lineage, sources
    CONTRADICTION_SEARCH  counterevidence complete; nothing contradicts an ACTIVE claim
    PROMOTION_GATE        the subject reached the level its directory requires

The expected front matter is computed from the ledger (`expected_front`); a
document whose authority-bearing fields differ from it is rejected. No model
judges evidence validity or promotion here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from serene.domain.base import id_prefix
from serene.domain.canonical import canonical_digest
from serene.domain.entities import LearningStatus, MemoryOperation, MemoryPatch
from serene.domain.events import MemoryCheck, MemoryPatchReviewed
from serene.domain.values import EpistemicLevel
from serene.lineage.provenance import provenance_violations, raw_sources_of
from serene.memory.diff import DiffFormatError, ParsedDiff, parse_full_diff
from serene.memory.document import (
    DIRECTORY_KIND,
    MemoryDoc,
    MemoryFormatError,
    MemoryFrontMatter,
    directory_of,
    parse,
)
from serene.memory.rules import required_level_for, rule_for
from serene.policies.learning import effective_status
from serene.policies.promotion import counterevidence_for, lineage_reasons
from serene.projections.state import ApprovalState, KernelState, LifecycleStatus

CRITIC_VERSION: Final = "memory-critic/1"
_MAX_CODES: Final = 64
_ACTIVE = LearningStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class MemoryReview:
    passed: bool
    checks_passed: tuple[MemoryCheck, ...]
    reason_codes: tuple[str, ...]
    critic_version: str = CRITIC_VERSION


# ------------------------------------------------------------------ ledger facts about a subject
def subject_hypothesis(subject: str, state: KernelState) -> str | None:
    record = state.entities.get(subject)
    if record is None:
        return None
    match id_prefix(subject):
        case "hyp":
            return subject
        case "lrn" | "exp":
            return str(record.entity.hypothesis_id)
        case _:
            return None


def subject_level(subject: str, state: KernelState) -> EpistemicLevel | None:
    if id_prefix(subject) == "exp":
        hyp = subject_hypothesis(subject, state)
        return None if hyp is None else state.hypothesis_levels.get(hyp)
    return state.level_of(subject)


def _subject_status(subject: str, state: KernelState, now: datetime) -> LearningStatus:
    learning = state.learnings.get(subject)
    if learning is not None:
        return effective_status(learning, state, now)
    record = state.entities[subject]
    return _ACTIVE if record.status is LifecycleStatus.ACTIVE else LearningStatus.DEPRECATED


def _subject_scope(entity: Any) -> tuple[str, ...]:
    scope = getattr(entity, "scope", None)
    return tuple(scope.contexts) if scope is not None else tuple(getattr(entity, "contexts", ()))


def subject_counterevidence(subject: str, state: KernelState) -> tuple[str, ...]:
    hypothesis = subject_hypothesis(subject, state)
    if hypothesis is not None:
        return counterevidence_for(hypothesis, state).all_ids
    record = state.entities.get(subject)
    counter = getattr(record.entity, "counter_observation_ids", ()) if record else ()
    return tuple(sorted(counter))


def expected_front(subject: str, path: str, state: KernelState, now: datetime) -> MemoryFrontMatter:
    """The front matter the ledger supports for `subject` at `path`, right now."""
    record = state.entities[subject]
    learning = state.learnings.get(subject)
    return MemoryFrontMatter(
        kind=DIRECTORY_KIND[directory_of(path)],
        subject=subject,
        level=subject_level(subject, state),
        status=_subject_status(subject, state, now),
        scope=_subject_scope(record.entity),
        valid_from=None if learning is None else learning.valid_from,
        review_after=None if learning is None else learning.review_after,
        sources=tuple(sorted(raw_sources_of(subject, state))),
        counterevidence=subject_counterevidence(subject, state),
    )


# ------------------------------------------------------------------ the four checks
def check_document(patch: MemoryPatch) -> tuple[MemoryDoc | None, ParsedDiff | None, list[str]]:
    reasons: list[str] = []
    try:
        parsed = parse_full_diff(patch.diff)
    except DiffFormatError:
        return None, None, ["MALFORMED_DIFF"]
    if parsed.path != patch.target_path:
        reasons.append("DIFF_PATH_MISMATCH")
    creating = patch.operation is MemoryOperation.CREATE
    if creating != (parsed.pre is None):
        reasons.append("OPERATION_DIFF_MISMATCH")
    if creating != (patch.base_revision is None):
        reasons.append("BASE_REVISION_MISMATCH")
    if patch.required_level != required_level_for(patch.target_path, patch.operation):
        reasons.append("REQUIRED_LEVEL_MISMATCH")
    try:
        doc = parse(parsed.post)
    except MemoryFormatError:
        return None, parsed, [*reasons, "MALFORMED_DOCUMENT"]
    if doc.front.kind is not rule_for(patch.target_path).kind:
        reasons.append("KIND_PATH_MISMATCH")
    withdrawing = doc.front.status is not _ACTIVE
    if (patch.operation is MemoryOperation.DEPRECATE) != withdrawing:
        reasons.append("DEPRECATE_MUST_WITHDRAW" if withdrawing else "WITHDRAWAL_MUST_DEPRECATE")
    if creating and withdrawing:
        reasons.append("CANNOT_CREATE_WITHDRAWN")
    return doc, parsed, reasons


def verify_patch_lineage(
    patch: MemoryPatch, doc: MemoryDoc | None, state: KernelState
) -> list[str]:
    """Provenance verifier: the patch and its document rest on complete, verified lineage."""
    reasons = provenance_violations(patch, state)
    if doc is None:
        return reasons
    subject = doc.front.subject
    if subject not in patch.provenance.derived_from:
        reasons.append("SUBJECT_NOT_IN_LINEAGE")
    if subject not in state.entities:
        return [*reasons, "UNKNOWN_SUBJECT"]
    reasons += lineage_reasons(subject, state)
    expected = tuple(sorted(raw_sources_of(subject, state)))
    if doc.front.sources != expected:
        reasons.append("SOURCES_MISMATCH")
    if set(doc.front.sources) - set(patch.provenance.source_ids):
        reasons.append("SOURCES_NOT_IN_PATCH_PROVENANCE")
    return reasons


def search_contradictions(
    patch: MemoryPatch, doc: MemoryDoc | None, state: KernelState, now: datetime
) -> list[str]:
    """Everything in the ledger that speaks against the document must be present and answered."""
    if doc is None or doc.front.subject not in state.entities:
        return ["NO_SUBJECT_TO_CHECK"]
    subject = doc.front.subject
    reasons: list[str] = []
    asserted = doc.front.status is _ACTIVE
    known = set(subject_counterevidence(subject, state))
    listed = set(doc.front.counterevidence)
    reasons += [f"COUNTEREVIDENCE_OMITTED:{c}" for c in sorted(known - listed)]
    reasons += [f"UNKNOWN_COUNTEREVIDENCE:{c}" for c in sorted(listed - known)]

    status = _subject_status(subject, state, now)
    if doc.front.status is not status:
        reasons.append(f"STATUS_MISMATCH:{status.value}")
    hypothesis = subject_hypothesis(subject, state)
    if asserted and hypothesis is not None:
        counter = counterevidence_for(hypothesis, state)
        if counter.contradicting_outcomes:
            reasons.append("CONTRADICTED_BY_OUTCOME")
        hyp_record = state.entities[hypothesis]
        if hyp_record.status is not LifecycleStatus.ACTIVE:
            reasons.append(f"SUBJECT_{hyp_record.status.value}")
        rivals = set(state.investigation_hypotheses.get(hyp_record.entity.investigation_id, []))
        rivals.discard(hypothesis)
        for lrn_id, learning in sorted(state.learnings.items()):
            if learning.hypothesis_id not in rivals:
                continue
            overlap = set(learning.contexts) & set(doc.front.scope)
            if overlap and effective_status(learning, state, now) is _ACTIVE:
                reasons.append(f"CONFLICTING_LEARNING:{lrn_id}")
    return reasons


def check_memory_authority(
    patch: MemoryPatch, doc: MemoryDoc | None, state: KernelState, now: datetime
) -> list[str]:
    """Promotion Gate for memory: the subject must have earned the directory's level."""
    if doc is None:
        return ["NO_SUBJECT_TO_CHECK"]
    subject = doc.front.subject
    if subject not in state.entities:
        return ["UNKNOWN_SUBJECT"]
    rule = rule_for(patch.target_path)
    reasons: list[str] = []
    level = subject_level(subject, state)
    if patch.operation is not MemoryOperation.DEPRECATE:
        have = "NONE" if level is None else level.name
        if level is None or level < rule.min_level:
            reasons.append(f"INSUFFICIENT_EVIDENCE:{have}_BELOW_{rule.min_level.name}")
        elif id_prefix(subject) not in rule.subject_prefixes:
            reasons.append(f"SUBJECT_KIND_NOT_ALLOWED:{id_prefix(subject)}")
    if id_prefix(subject) == "exp" and patch.operation is not MemoryOperation.DEPRECATE:
        exp = state.experiments.get(subject)
        approval = None if exp is None else state.approvals.get(exp.approval_request_id or "")
        if approval is None or approval.state is not ApprovalState.GRANTED:
            reasons.append("NO_PARENT_DECISION")
    expected = expected_front(subject, patch.target_path, state, now)
    for field_name in ("level", "scope", "valid_from", "review_after"):
        if getattr(doc.front, field_name) != getattr(expected, field_name):
            reasons.append(f"{field_name.upper()}_MISMATCH")
    return reasons


# ------------------------------------------------------------------ verdict
def review_patch(patch: MemoryPatch, state: KernelState, now: datetime) -> MemoryReview:
    doc, _parsed, fmt = check_document(patch)
    results = {
        MemoryCheck.DOCUMENT_FORMAT: fmt,
        MemoryCheck.LINEAGE: verify_patch_lineage(patch, doc, state),
        MemoryCheck.CONTRADICTION_SEARCH: search_contradictions(patch, doc, state, now),
        MemoryCheck.PROMOTION_GATE: check_memory_authority(patch, doc, state, now),
    }
    passed_checks = tuple(check for check, reasons in results.items() if not reasons)
    reasons = list(dict.fromkeys(r for rs in results.values() for r in rs))
    if not reasons:
        return MemoryReview(True, passed_checks, ("ALL_CHECKS_PASSED",))
    return MemoryReview(False, passed_checks, tuple(reasons[:_MAX_CODES]))


def review_facts_digest(patch_id: str, review: MemoryReview, state: KernelState) -> str:
    return canonical_digest(
        {
            "patch_id": patch_id,
            "passed": review.passed,
            "checks_passed": [c.value for c in review.checks_passed],
            "reason_codes": list(review.reason_codes),
            "critic_version": review.critic_version,
            "ledger_head": state.last_event_hash,
        }
    )


def review_payload(patch: MemoryPatch, state: KernelState, now: datetime) -> MemoryPatchReviewed:
    review = review_patch(patch, state, now)
    return MemoryPatchReviewed(
        patch_id=patch.patch_id,
        passed=review.passed,
        checks_passed=review.checks_passed,
        reason_codes=review.reason_codes,
        critic_version=review.critic_version,
        facts_digest=review_facts_digest(patch.patch_id, review, state),
    )
