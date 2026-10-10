"""Orchestrates the pure lifecycle steps against the ledger.

The service decides nothing: each step is a pure function's draft, and the
ledger's admission recomputes every authority decision before sealing. A step
the ledger refuses is reported with its reason codes; the stream is unchanged.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from serene.domain.base import new_id
from serene.domain.events import DomainEvent, EventDraft, EventType, LearningRecorded
from serene.domain.values import ActorRef, EpistemicLevel, VerificationStatus
from serene.experiments import lifecycle
from serene.ledger.service import AdmissionRejected, EventLedger
from serene.policies import promotion
from serene.ports.clock import Clock


@dataclass(slots=True)
class StepReport:
    appended: list[DomainEvent] = field(default_factory=list)
    refused: list[tuple[EventType, tuple[str, ...]]] = field(default_factory=list)

    def extend(self, other: StepReport) -> None:
        self.appended += other.appended
        self.refused += other.refused


class ExperimentLifecycleService:
    def __init__(
        self,
        ledger: EventLedger,
        clock: Clock,
        ctx: lifecycle.LifecycleContext,
        *,
        new_entity_id: Callable[[str], str] = new_id,
    ) -> None:
        self._ledger = ledger
        self._clock = clock
        self._ctx = ctx
        self._new_id = new_entity_id

    def _append_all(self, drafts: Sequence[EventDraft]) -> StepReport:
        report = StepReport()
        for draft in drafts:
            try:
                report.appended.append(self._ledger.append_event(draft))
            except AdmissionRejected as exc:
                report.refused.append((draft.event_type, exc.reason_codes))
                break  # later drafts may depend on this one
        return report

    def classify(self, child_id: str, experiment_id: str) -> StepReport:
        state = self._ledger.replay_events(child_id)
        return self._append_all(
            lifecycle.classify(experiment_id, state, self._clock.now(), self._ctx)
        )

    def request_approval(self, child_id: str, experiment_id: str, *, parent_id: str) -> StepReport:
        state = self._ledger.replay_events(child_id)
        draft = lifecycle.request_approval(
            experiment_id,
            state,
            self._clock.now(),
            self._ctx,
            requested_of=parent_id,
            approval_request_id=self._new_id("apr"),
        )
        return self._append_all([] if draft is None else [draft])

    def run_timers(self, child_id: str) -> StepReport:
        """Scheduler entry point: nudges, timeouts, due starts and learning validity."""
        report = StepReport()
        for step in (lifecycle.nudge_due, lifecycle.timeout_due, lifecycle.start_due):
            state = self._ledger.replay_events(child_id)
            for draft in step(state, self._clock.now(), self._ctx):
                report.extend(self._append_all([draft]))
        state = self._ledger.replay_events(child_id)
        for draft in lifecycle.learning_validity_due(state, self._clock.now(), self._ctx):
            report.extend(self._append_all([draft]))
        return report

    def complete(self, child_id: str, experiment_id: str) -> StepReport:
        """Close a running experiment with its reported outcomes and hand it to the gate."""
        state = self._ledger.replay_events(child_id)
        report = self._append_all(
            [lifecycle.complete(experiment_id, state, self._clock.now(), self._ctx)]
        )
        if report.refused:
            return report
        state = self._ledger.replay_events(child_id)
        draft = lifecycle.promotion_after_completion(
            experiment_id, state, self._clock.now(), self._ctx
        )
        report.extend(self._append_all([] if draft is None else [draft]))
        return report

    def promote_to_learning(
        self, child_id: str, hypothesis_id: str, *, reviewer: ActorRef
    ) -> StepReport:
        """Gate 4 -> 5, then record the policy-built, scoped, expiring learning."""
        state = self._ledger.replay_events(child_id)
        now = self._clock.now()
        event_type, decision = promotion.decide_promotion(
            hypothesis_id,
            EpistemicLevel.TESTED_HYPOTHESIS,
            EpistemicLevel.CONTEXTUAL_LEARNING,
            state,
        )
        report = self._append_all(
            [self._ctx.draft(event_type, self._ctx.policy, decision, state, now)]
        )
        if report.refused or event_type is not EventType.PROMOTION_GRANTED:
            return report
        grant = report.appended[-1]
        state = self._ledger.replay_events(child_id)
        candidate = promotion.build_learning_candidate(
            hypothesis_id,
            state,
            learning_id=self._new_id("lrn"),
            created_by=self._ctx.policy,
            reviewer=reviewer,
            now=self._clock.now(),
        )
        parents = tuple(
            dict.fromkeys(
                state.entities[p].introduced_by for p in candidate.provenance.derived_from
            )
        )
        draft = self._ctx.draft(
            EventType.LEARNING_RECORDED,
            self._ctx.policy,
            LearningRecorded(learning=candidate, promotion_event_id=grant.event_id),
            state,
            self._clock.now(),
            (*parents, grant.event_id),
        ).model_copy(update={"verification_status": VerificationStatus.VERIFIED})
        report.extend(self._append_all([draft]))
        return report
