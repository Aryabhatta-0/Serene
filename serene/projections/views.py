"""The five initial read projections (issue #6).

Each projection is a pure function of `KernelState` returning canonical,
JSON-compatible data. Ledger = truth; projections = disposable read state.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any, Final

from serene.domain.canonical import canonical_digest, format_timestamp, to_canonical_data
from serene.domain.entities import (
    TERMINAL_INVESTIGATION_STATUSES,
    LearningStatus,
)
from serene.domain.events import DomainEvent
from serene.domain.values import VerificationStatus
from serene.projections.state import (
    OPEN_APPROVAL_STATES,
    KernelState,
    LearningRecord,
    LifecycleStatus,
    replay,
)


def current_child_state(state: KernelState) -> dict[str, Any]:
    by_level: dict[str, int] = {}
    evidence: dict[str, int] = {status.value: 0 for status in VerificationStatus}
    for record in state.entities.values():
        if record.level is not None:
            by_level[record.level.name] = by_level.get(record.level.name, 0) + 1
        if record.kind == "evd":
            evidence[record.verification_status.value] += 1
    return {
        "child_id": state.child_id,
        "last_sequence": state.last_sequence,
        "last_event_hash": state.last_event_hash,
        "entities_by_level": dict(sorted(by_level.items())),
        "evidence_by_status": evidence,
    }


def active_investigations(state: KernelState) -> dict[str, Any]:
    return {
        inv_id: {
            "status": status.value,
            "hypothesis_ids": sorted(state.investigation_hypotheses.get(inv_id, [])),
        }
        for inv_id, status in sorted(state.investigations.items())
        if status not in TERMINAL_INVESTIGATION_STATUSES
    }


def active_hypotheses(state: KernelState) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for hyp_id, level in sorted(state.hypothesis_levels.items()):
        record = state.entities[hyp_id]
        if record.status is not LifecycleStatus.ACTIVE:
            continue
        out[hyp_id] = {
            "level": level.name,
            "investigation_id": record.entity.investigation_id,
        }
    return out


def pending_approvals(state: KernelState) -> dict[str, Any]:
    return {
        apr_id: {
            "experiment_id": record.experiment_id,
            "state": record.state.value,
            "nudges": record.nudges,
            "safety_class": record.safety_class.value,
            "expires_at": format_timestamp(record.expires_at),
        }
        for apr_id, record in sorted(state.approvals.items())
        if record.state in OPEN_APPROVAL_STATES
    }


def active_learnings(state: KernelState) -> dict[str, Any]:
    return {
        lrn_id: {
            "status": record.status.value,
            "hypothesis_id": record.hypothesis_id,
            "contexts": list(record.contexts),
            "valid_from": format_timestamp(record.valid_from),
            "review_after": format_timestamp(record.review_after),
        }
        for lrn_id, record in sorted(state.learnings.items())
        if record.status is not LearningStatus.DEPRECATED
    }


def effective_learning_status(record: LearningRecord, now: datetime) -> LearningStatus:
    """Time-aware status for presentation: a learning past review is never shown ACTIVE."""
    if record.status is LearningStatus.ACTIVE and now >= record.review_after:
        return LearningStatus.NEEDS_REVIEW
    return record.status


PROJECTIONS: Final[dict[str, Callable[[KernelState], dict[str, Any]]]] = {
    "current_child_state": current_child_state,
    "active_investigations": active_investigations,
    "active_hypotheses": active_hypotheses,
    "pending_approvals": pending_approvals,
    "active_learnings": active_learnings,
}


def project(state: KernelState) -> dict[str, dict[str, Any]]:
    return {name: to_canonical_data(fn(state)) for name, fn in PROJECTIONS.items()}


def rebuild_projections(events: Iterable[DomainEvent]) -> dict[str, dict[str, Any]]:
    """Delete-and-rebuild: projections derived solely by replaying the ledger."""
    return project(replay(events))


def projection_digest(projections: dict[str, dict[str, Any]]) -> str:
    return canonical_digest(projections)
