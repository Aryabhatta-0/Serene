"""Learning validity, review and staleness (issue #20).

A Level-5 learning is scoped and expiring. Its *ledger* status moves through a
closed state machine; its *effective* status additionally accounts for time and
for signals the ledger already holds, so a learning that should be re-examined
is never presented as ACTIVE, even before the scheduled job records the change.

    ACTIVE -> NEEDS_REVIEW   review_after reached, or the hypothesis was superseded
    ACTIVE -> NEEDS_RETEST   contradicting outcome, or meaningful context drift
    *      -> STALE          still unreviewed STALE_AFTER past review_after
    *      -> DEPRECATED     hypothesis refuted, or learning superseded (terminal)

Signals only ever *lower* trust. Re-activation (-> ACTIVE) is admitted only when
the deterministic policy finds nothing outstanding: inside the validity window,
no unresolved signal since the learning was last active, and - after a retest -
a newer approved, completed experiment whose outcomes all support.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from serene.domain.entities import LearningStatus, OutcomeResult
from serene.domain.events import LearningStatusChanged
from serene.policies.decision import PolicyDecision
from serene.policies.promotion import tested_experiments
from serene.projections.state import KernelState, LearningRecord, LifecycleStatus

POLICY_VERSION: Final = "learning-validity/1"
STALE_AFTER: Final = timedelta(days=30)

# Closed vocabulary of observation context tags that mean "the world this learning
# was tested in has changed". Matching only escalates (to NEEDS_RETEST), never trusts.
DRIFT_MARKERS: Final = frozenset(
    {
        "new_caregiver",
        "caregiver_change",
        "schedule_change",
        "routine_change",
        "school_change",
        "daycare_change",
        "moved_home",
        "new_sibling",
        "illness",
        "travel",
        "developmental_change",
    }
)

_LS = LearningStatus
LEARNING_TRANSITIONS: Final[dict[LearningStatus, frozenset[LearningStatus]]] = {
    _LS.ACTIVE: frozenset({_LS.NEEDS_REVIEW, _LS.NEEDS_RETEST, _LS.STALE, _LS.DEPRECATED}),
    _LS.NEEDS_REVIEW: frozenset({_LS.ACTIVE, _LS.NEEDS_RETEST, _LS.STALE, _LS.DEPRECATED}),
    _LS.NEEDS_RETEST: frozenset({_LS.ACTIVE, _LS.STALE, _LS.DEPRECATED}),
    _LS.STALE: frozenset({_LS.NEEDS_RETEST, _LS.DEPRECATED}),
    _LS.DEPRECATED: frozenset(),
}

# Most to least trusted; the effective status is the least trusted applicable one.
_TRUST_ORDER: Final = (_LS.ACTIVE, _LS.NEEDS_REVIEW, _LS.NEEDS_RETEST, _LS.STALE, _LS.DEPRECATED)


@dataclass(frozen=True, slots=True)
class ValiditySignal:
    target: LearningStatus
    reason_code: str


def _since(record: LearningRecord) -> datetime:
    return record.active_since or record.valid_from


def validity_signals(
    record: LearningRecord, state: KernelState, now: datetime, *, since: datetime | None = None
) -> list[ValiditySignal]:
    """Every reason, from the ledger and the clock, that this learning is no longer ACTIVE.

    Event-driven signals count only if recorded at or after `since` (default: when
    the learning last became ACTIVE).
    """
    signals: list[ValiditySignal] = []
    since = since or _since(record)
    hypothesis = state.entities.get(record.hypothesis_id)
    if hypothesis is not None:
        if hypothesis.status is LifecycleStatus.REFUTED:
            signals.append(ValiditySignal(_LS.DEPRECATED, "HYPOTHESIS_REFUTED"))
        elif hypothesis.status is LifecycleStatus.SUPERSEDED:
            signals.append(ValiditySignal(_LS.NEEDS_REVIEW, "HYPOTHESIS_SUPERSEDED"))
    if record.superseded_by is not None:
        signals.append(ValiditySignal(_LS.DEPRECATED, "LEARNING_SUPERSEDED"))

    for exp in state.experiments.values():
        if exp.experiment.hypothesis_id != record.hypothesis_id:
            continue
        for outcome_id in exp.outcome_ids:
            outcome = state.entities[outcome_id]
            if outcome.entity.result is not OutcomeResult.CONTRADICTS:
                continue
            if outcome.introduced_at is not None and outcome.introduced_at >= since:
                signals.append(ValiditySignal(_LS.NEEDS_RETEST, "CONTRADICTING_OUTCOME"))

    scope = set(record.contexts)
    for entity in state.entities.values():
        if entity.kind != "obs" or entity.introduced_at is None or entity.introduced_at < since:
            continue
        contexts = set(entity.entity.contexts)
        markers = sorted(contexts & DRIFT_MARKERS)
        if markers and contexts & scope:
            signals.append(ValiditySignal(_LS.NEEDS_RETEST, f"CONTEXT_DRIFT:{markers[0]}"))

    if now >= record.review_after:
        signals.append(ValiditySignal(_LS.NEEDS_REVIEW, "REVIEW_DUE"))
    if now >= record.review_after + STALE_AFTER:
        signals.append(ValiditySignal(_LS.STALE, "REVIEW_OVERDUE"))
    return sorted(set(signals), key=lambda s: (_TRUST_ORDER.index(s.target), s.reason_code))


def _least_trusted(statuses: list[LearningStatus]) -> LearningStatus:
    return max(statuses, key=_TRUST_ORDER.index)


def effective_status(record: LearningRecord, state: KernelState, now: datetime) -> LearningStatus:
    """The status a reader must use. Never more trusted than the ledger status."""
    return _least_trusted(
        [record.status, *(s.target for s in validity_signals(record, state, now))]
    )


def surfaceable_learnings(state: KernelState, now: datetime) -> list[LearningRecord]:
    """Learnings that may be presented as ACTIVE right now. Stale ones never are."""
    return [
        record
        for _, record in sorted(state.learnings.items())
        if record.status is _LS.ACTIVE and effective_status(record, state, now) is _LS.ACTIVE
    ]


def due_transition(
    record: LearningRecord, state: KernelState, now: datetime
) -> tuple[LearningStatus, tuple[str, ...]] | None:
    """The next legal step towards the effective status, with its reasons, if one is due."""
    signals = validity_signals(record, state, now)
    target = _least_trusted([record.status, *(s.target for s in signals)])
    if target is record.status:
        return None
    allowed = LEARNING_TRANSITIONS[record.status]
    # Walk towards the target through legal states only (e.g. STALE -> DEPRECATED is legal).
    candidates = [
        s
        for s in _TRUST_ORDER
        if s in allowed and _TRUST_ORDER.index(s) <= _TRUST_ORDER.index(target)
    ]
    if not candidates:
        return None
    step = max(candidates, key=_TRUST_ORDER.index)
    reasons = tuple(
        s.reason_code for s in signals if _TRUST_ORDER.index(s.target) <= _TRUST_ORDER.index(step)
    )
    return step, reasons or (signals[-1].reason_code,)


def _retest_succeeded(record: LearningRecord, state: KernelState) -> bool:
    since = record.status_changed_at
    for exp_id in tested_experiments(record.hypothesis_id, state):
        exp = state.experiments[exp_id]
        if exp.started_at is None or since is None or exp.started_at < since:
            continue
        results = {state.entities[o].entity.result for o in exp.outcome_ids}
        if results == {OutcomeResult.SUPPORTS}:
            return True
    return False


def check_status_change(
    payload: LearningStatusChanged, state: KernelState, now: datetime
) -> PolicyDecision:
    record = state.learnings.get(payload.learning_id)
    if record is None:
        return PolicyDecision.from_reasons(["UNKNOWN_LEARNING"], POLICY_VERSION)
    if record.status != payload.from_status:
        return PolicyDecision.from_reasons([f"STALE_STATUS:{record.status.value}"], POLICY_VERSION)
    if payload.to_status not in LEARNING_TRANSITIONS[payload.from_status]:
        return PolicyDecision.from_reasons(
            [f"ILLEGAL_TRANSITION:{payload.from_status.value}_TO_{payload.to_status.value}"],
            POLICY_VERSION,
        )
    reasons: list[str] = []
    if payload.to_status is _LS.ACTIVE:
        # Lowering trust is always admissible; raising it must be justified by policy.
        if now >= record.review_after:
            reasons.append("REACTIVATION_NOT_JUSTIFIED:REVIEW_DUE")
        if record.status is _LS.NEEDS_RETEST and not _retest_succeeded(record, state):
            reasons.append("REACTIVATION_NOT_JUSTIFIED:NO_SUCCESSFUL_RETEST")
        # A successful retest answers the signals that triggered it; only newer ones remain.
        since = record.status_changed_at if record.status is _LS.NEEDS_RETEST else None
        outstanding = [
            s.reason_code.split(":", 1)[0]
            for s in validity_signals(record, state, now, since=since)
            if s.reason_code != "REVIEW_DUE"
        ]
        reasons += [f"REACTIVATION_NOT_JUSTIFIED:{code}" for code in outstanding]
    return PolicyDecision.from_reasons(reasons, POLICY_VERSION)
