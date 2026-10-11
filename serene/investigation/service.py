"""Deterministic investigation controller (issues #10, #11, #12, #13, #14).

One step = read the phase from the ledger, do that phase's bounded work,
append the resulting events, and request exactly one phase transition. Ledger
admission re-checks every transition against the legal table and its evidence
guards, so a refused transition leaves the investigation where it was.

    UNDERSTANDING      question + observations exist                 -> RETRIEVING_CONTEXT
    RETRIEVING_CONTEXT experience / memory / belief retrieved        -> FORMING_HYPOTHESES
                       (context digest recorded in the reason codes)
    FORMING_HYPOTHESES model proposes patterns + competing hypotheses;
                       >= 2 admitted                                  -> NEEDS_EVIDENCE
    NEEDS_EVIDENCE     planner suggests; MinimumDataPolicy picks at most
                       one missing observation, or none (sufficient) -> ASKING_HUMAN |
                                                                        RESEARCHING | EVALUATING
    ASKING_HUMAN       one YES/NO/UNSURE question; answered           -> VERIFYING
    RESEARCHING        bounded browser, retries counted in the ledger -> VERIFYING |
                                                                        NEEDS_EVIDENCE (exhausted)
    VERIFYING          independent verifier decides every acquisition -> EVALUATING
    EVALUATING         model may revise (supersede) or propose an
                       experiment; deterministic sufficiency decides  -> NEEDS_APPROVAL |
                                                                        NEEDS_EVIDENCE | COMPLETE
    NEEDS_APPROVAL     the experiment lifecycle classifies each proposal (RED is
                       blocked); the opening parent decides the rest on an
                       authenticated prompt; expiry parks              -> EVALUATING

Any phase parks honestly (PARKED_UNRESOLVED) on an exhausted budget, an
unavailable runtime/planner, a missing parent response or no live hypothesis.
COMPLETE and PARKED_UNRESOLVED are terminal; `step` on them is a no-op.
Budgets (model runs, evidence rounds, acquisition attempts) are counted from
ledger events, so a restart never replenishes them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Protocol

from serene.domain.base import new_id
from serene.domain.entities import (
    TERMINAL_INVESTIGATION_PHASES,
    Investigation,
    InvestigationPhase,
    Observation,
)
from serene.domain.events import (
    AcquisitionMode,
    EventDraft,
    EventPayload,
    EventType,
    EvidenceRequested,
    InvestigationOpened,
    InvestigationPhaseChanged,
)
from serene.domain.values import (
    ActorKind,
    ActorRef,
    DerivationMethod,
    Provenance,
    SourceKind,
    SourceRef,
    VerificationStatus,
)
from serene.investigation.boundary import BoundaryReport, KernelBoundary
from serene.investigation.context import ContextRetriever, InvestigationContext
from serene.investigation.minimum_data import EvidencePlanner, MinimumDataPolicy, Selection
from serene.ledger.service import AdmissionRejected, EventLedger
from serene.observability.telemetry import SafeTelemetry
from serene.policies.investigation import active_hypotheses, latest_request
from serene.ports.agent_runtime import AgentRuntime, AgentTask, ProposalKind
from serene.ports.clock import Clock
from serene.projections.state import (
    ApprovalState,
    ExperimentStatus,
    KernelState,
    LifecycleStatus,
)

_P = InvestigationPhase
_MODEL_PHASES: Final = frozenset({_P.FORMING_HYPOTHESES, _P.EVALUATING})
_DECIDED_EXPERIMENT: Final = frozenset(
    {
        ExperimentStatus.APPROVED,
        ExperimentStatus.STARTED,
        ExperimentStatus.COMPLETED,
        ExperimentStatus.ABANDONED,
        ExperimentStatus.BLOCKED,
    }
)


class EvidenceActions(Protocol):
    """What the controller needs from the evidence service (serene.evidence.service)."""

    def acquire(self, child_id: str, request_id: str) -> object: ...

    def verify_pending(self, child_id: str, request_id: str) -> object: ...


class QuestionAsker(Protocol):
    def ask(self, child_id: str, request_id: str) -> object: ...


class ExperimentSteps(Protocol):
    """Branch-B experiment lifecycle (serene.experiments.service). POLICY decides; no model."""

    def classify(self, child_id: str, experiment_id: str) -> object: ...

    def request_approval(self, child_id: str, experiment_id: str, *, parent_id: str) -> object: ...

    def run_timers(self, child_id: str) -> object: ...


class ApprovalPrompter(Protocol):
    """Shows open approval requests to the bound parent (idempotent per request)."""

    def prompt_pending_approvals(self, child_id: str) -> object: ...


@dataclass(frozen=True, slots=True)
class InvestigationBudget:
    max_model_runs: int = 6
    max_evidence_rounds: int = 3
    max_steps_per_drive: int = 32
    model_cost_micro_usd: int = 5_000_000
    model_steps: int = 3
    ask_timeout: timedelta = timedelta(hours=48)


@dataclass(frozen=True, slots=True)
class StepResult:
    investigation_id: str
    phase: InvestigationPhase
    to_phase: InvestigationPhase | None
    action: str
    reason_codes: tuple[str, ...] = ()
    waiting: bool = False

    @property
    def terminal(self) -> bool:
        phase = self.to_phase or self.phase
        return phase in TERMINAL_INVESTIGATION_PHASES


class InvestigationService:
    def __init__(
        self,
        ledger: EventLedger,
        clock: Clock,
        *,
        runtime: AgentRuntime,
        planner: EvidencePlanner,
        boundary: KernelBoundary,
        retriever: ContextRetriever,
        policy: MinimumDataPolicy,
        system_actor: ActorRef,
        evidence: EvidenceActions | None = None,
        asker: QuestionAsker | None = None,
        telemetry: SafeTelemetry | None = None,
        budget: InvestigationBudget | None = None,
        new_entity_id: Callable[[str], str] = new_id,
        experiments: ExperimentSteps | None = None,
        approvals: ApprovalPrompter | None = None,
    ) -> None:
        if system_actor.kind is not ActorKind.SYSTEM:
            raise ValueError("the controller acts as a SYSTEM actor")
        self._ledger = ledger
        self._clock = clock
        self._runtime = runtime
        self._planner = planner
        self._boundary = boundary
        self._retriever = retriever
        self._policy = policy
        self._system = system_actor
        self._evidence = evidence
        self._asker = asker
        self._experiments = experiments
        self._approvals = approvals
        self._telemetry = telemetry or SafeTelemetry()
        self._budget = budget or InvestigationBudget()
        self._new_id = new_entity_id

    # ------------------------------------------------------------------ public
    def open(self, child_id: str, question: str, *, opened_by: ActorRef, source: SourceRef) -> str:
        """Record a parent's question (INVESTIGATION_OPENED); the phase starts at UNDERSTANDING."""
        investigation = Investigation(
            child_id=child_id,
            provenance=Provenance(
                created_by=opened_by,
                created_at=self._clock.now(),
                method=(
                    DerivationMethod.PARENT_REPORT
                    if opened_by.kind is ActorKind.PARENT
                    else DerivationMethod.DETERMINISTIC_RULE
                ),
            ),
            investigation_id=self._new_id("inv"),
            question=question,
            opened_by=opened_by,
            opened_at=self._clock.now(),
        )
        self._append(
            EventType.INVESTIGATION_OPENED,
            child_id,
            InvestigationOpened(investigation=investigation),
            actor=opened_by,
            source=source,
        )
        self._telemetry.emit(
            "investigation.opened",
            {
                "child_id": child_id,
                "investigation_id": investigation.investigation_id,
                "phase": _P.UNDERSTANDING.value,
            },
        )
        return investigation.investigation_id

    def drive(self, child_id: str, investigation_id: str) -> list[StepResult]:
        """Step until waiting on the outside world, terminal, refused, or out of steps."""
        results: list[StepResult] = []
        for _ in range(self._budget.max_steps_per_drive):
            result = self.step(child_id, investigation_id)
            results.append(result)
            if result.waiting or result.terminal or result.action == "TRANSITION_REFUSED":
                break
        return results

    def step(self, child_id: str, investigation_id: str) -> StepResult:
        state = self._ledger.replay_events(child_id)
        phase = state.investigation_phases[investigation_id]
        if phase in TERMINAL_INVESTIGATION_PHASES:
            return StepResult(investigation_id, phase, None, "TERMINAL", waiting=True)
        handler = {
            _P.UNDERSTANDING: self._understanding,
            _P.RETRIEVING_CONTEXT: self._retrieving,
            _P.FORMING_HYPOTHESES: self._forming,
            _P.NEEDS_EVIDENCE: self._needs_evidence,
            _P.ASKING_HUMAN: self._asking,
            _P.RESEARCHING: self._researching,
            _P.VERIFYING: self._verifying,
            _P.EVALUATING: self._evaluating,
            _P.NEEDS_APPROVAL: self._needs_approval,
        }[phase]
        result = handler(child_id, investigation_id, state)
        self._telemetry.emit(
            "investigation.step",
            {
                "child_id": child_id,
                "investigation_id": investigation_id,
                "phase": phase.value,
                "to_phase": result.to_phase.value if result.to_phase else "",
                "status": result.action,
                "reason_codes": tuple(r.split(":", 1)[0] for r in result.reason_codes),
            },
        )
        return result

    # ------------------------------------------------------------------ phases
    def _understanding(self, child: str, inv: str, state: KernelState) -> StepResult:
        observations = [
            r
            for r in state.entities.values()
            if isinstance(r.entity, Observation) and r.status is LifecycleStatus.ACTIVE
        ]
        if not observations:
            return self._park(child, inv, _P.UNDERSTANDING, "NO_OBSERVATIONS")
        return self._move(
            child, inv, _P.UNDERSTANDING, _P.RETRIEVING_CONTEXT, "QUESTION_UNDERSTOOD"
        )

    def _retrieving(self, child: str, inv: str, state: KernelState) -> StepResult:
        ctx = self._context(state, child, inv)
        return self._move(
            child,
            inv,
            _P.RETRIEVING_CONTEXT,
            _P.FORMING_HYPOTHESES,
            "CONTEXT_RETRIEVED",
            f"CONTEXT_DIGEST:{ctx.digest}",
        )

    def _forming(self, child: str, inv: str, state: KernelState) -> StepResult:
        report = self._model_step(
            child,
            inv,
            state,
            phase=_P.FORMING_HYPOTHESES,
            goal=(
                "Propose patterns over the observations and at least two competing "
                "hypotheses with support, counter-evidence, scope and known confounders."
            ),
            kinds={"pattern", "hypothesis", "need_evidence", "abstain"},
        )
        if isinstance(report, StepResult):
            return report
        fresh = self._ledger.replay_events(child)
        if len(active_hypotheses(inv, fresh)) < 2:
            return self._park(
                child, inv, _P.FORMING_HYPOTHESES, "INSUFFICIENT_COMPETING_HYPOTHESES"
            )
        return self._move(child, inv, _P.FORMING_HYPOTHESES, _P.NEEDS_EVIDENCE, "HYPOTHESES_FORMED")

    def _needs_evidence(self, child: str, inv: str, state: KernelState) -> StepResult:
        rounds = len(state.investigation_requests.get(inv, []))
        if rounds >= self._budget.max_evidence_rounds:
            return self._park(child, inv, _P.NEEDS_EVIDENCE, "EVIDENCE_BUDGET_EXHAUSTED")
        selection = self._select(child, inv, state)
        if selection is None:
            return self._park(child, inv, _P.NEEDS_EVIDENCE, "PLANNER_UNAVAILABLE")
        if selection.chosen is None:
            return self._move(child, inv, _P.NEEDS_EVIDENCE, _P.EVALUATING, "EVIDENCE_SUFFICIENT")
        candidate = selection.chosen.candidate
        request_id = self._new_id("erq")
        try:
            self._append(
                EventType.EVIDENCE_REQUESTED,
                child,
                EvidenceRequested(
                    request_id=request_id,
                    investigation_id=inv,
                    requested_fields=candidate.requested_fields,
                    information_value=selection.chosen.information_value,
                    rationale=candidate.rationale,
                    acquisition_mode=candidate.acquisition_mode,
                    question=candidate.question,
                    subject=candidate.subject,
                    allowed_domains=candidate.allowed_domains,
                    predictions=candidate.predictions,
                ),
            )
        except AdmissionRejected as exc:
            return StepResult(inv, _P.NEEDS_EVIDENCE, None, "TRANSITION_REFUSED", exc.reason_codes)
        self._telemetry.emit(
            "evidence.requested",
            {
                "child_id": child,
                "investigation_id": inv,
                "request_id": request_id,
                "acquisition_mode": candidate.acquisition_mode.value,
                "information_value": selection.chosen.information_value.value,
            },
        )
        if candidate.acquisition_mode is AcquisitionMode.ASK_PARENT:
            moved = self._move(child, inv, _P.NEEDS_EVIDENCE, _P.ASKING_HUMAN, "QUESTION_SELECTED")
            if self._asker is not None:
                self._asker.ask(child, request_id)
            return moved
        return self._move(child, inv, _P.NEEDS_EVIDENCE, _P.RESEARCHING, "RESEARCH_SELECTED")

    def _asking(self, child: str, inv: str, state: KernelState) -> StepResult:
        record = latest_request(inv, state)
        if record is not None and record.answered:
            return self._move(child, inv, _P.ASKING_HUMAN, _P.VERIFYING, "ANSWER_RECEIVED")
        asked_at = self._recorded_at(child, record.event_id) if record is not None else None
        if asked_at is None or self._clock.now() - asked_at > self._budget.ask_timeout:
            return self._park(child, inv, _P.ASKING_HUMAN, "PARENT_NO_RESPONSE")
        if self._asker is not None and record is not None:
            self._asker.ask(child, record.request.request_id)  # idempotent re-delivery
        return StepResult(inv, _P.ASKING_HUMAN, None, "WAITING_FOR_PARENT", waiting=True)

    def _researching(self, child: str, inv: str, state: KernelState) -> StepResult:
        record = latest_request(inv, state)
        if self._evidence is None or record is None:
            return self._park(child, inv, _P.RESEARCHING, "NO_EVIDENCE_SERVICE")
        if not record.answered and not record.exhausted:
            self._evidence.acquire(child, record.request.request_id)
            record = latest_request(inv, self._ledger.replay_events(child))
            assert record is not None
        if record.answered:
            return self._move(child, inv, _P.RESEARCHING, _P.VERIFYING, "EVIDENCE_ACQUIRED")
        if record.exhausted:
            return self._move(
                child, inv, _P.RESEARCHING, _P.NEEDS_EVIDENCE, "ACQUISITION_EXHAUSTED"
            )
        # Yield to the scheduler: the next tick retries (backoff = tick interval), and
        # the ledger-counted attempt budget bounds how often that can happen.
        return StepResult(
            inv,
            _P.RESEARCHING,
            None,
            "RETRY_SCHEDULED",
            (f"ATTEMPTS_USED:{record.failed_attempts}",),
            waiting=True,
        )

    def _verifying(self, child: str, inv: str, state: KernelState) -> StepResult:
        record = latest_request(inv, state)
        if record is not None and record.request.acquisition_mode is AcquisitionMode.BROWSE:
            if self._evidence is None:
                return self._park(child, inv, _P.VERIFYING, "NO_EVIDENCE_SERVICE")
            self._evidence.verify_pending(child, record.request.request_id)
        return self._move(child, inv, _P.VERIFYING, _P.EVALUATING, "EVIDENCE_DECIDED")

    def _evaluating(self, child: str, inv: str, state: KernelState) -> StepResult:
        kinds: set[ProposalKind] = {"pattern", "hypothesis", "need_evidence", "abstain"}
        declined = self._parent_declined_an_experiment(inv, state)
        if not declined:
            kinds.add("experiment")
        report = self._model_step(
            child,
            inv,
            state,
            phase=_P.EVALUATING,
            goal=(
                "Re-evaluate the competing hypotheses against the verified evidence. Revise a "
                "hypothesis only by proposing a successor that supersedes it. "
                + (
                    "The parent declined an experiment: propose none."
                    if declined
                    else "Propose at most one reversible experiment, only if evidence alone "
                    "cannot discriminate."
                )
            ),
            kinds=kinds,
        )
        if isinstance(report, StepResult):
            return report
        proposed = [o.entity_id for o in report.admitted("experiment") if o.entity_id]
        if proposed and self._experiments is None:
            return self._move(child, inv, _P.EVALUATING, _P.NEEDS_APPROVAL, "EXPERIMENT_PROPOSED")
        if proposed and self._seek_approval(child, inv, proposed):
            moved = self._move(child, inv, _P.EVALUATING, _P.NEEDS_APPROVAL, "EXPERIMENT_PROPOSED")
            if self._approvals is not None:
                self._approvals.prompt_pending_approvals(child)
            return moved
        # No proposal, or every proposal was blocked (RED / unfit) and needs no decision.
        fresh = self._ledger.replay_events(child)
        ctx = self._context(fresh, child, inv)
        if not ctx.live_hypotheses():
            return self._park(child, inv, _P.EVALUATING, "NO_LIVE_HYPOTHESIS")
        selection = self._select(child, inv, fresh, ctx)
        if selection is None:
            return self._park(child, inv, _P.EVALUATING, "PLANNER_UNAVAILABLE")
        if selection.sufficient:
            return self._move(
                child,
                inv,
                _P.EVALUATING,
                _P.COMPLETE,
                "EVIDENCE_SUFFICIENT",
                "COMPETING_HYPOTHESES_RETAINED",
            )
        if len(fresh.investigation_requests.get(inv, [])) >= self._budget.max_evidence_rounds:
            return self._park(child, inv, _P.EVALUATING, "EVIDENCE_BUDGET_EXHAUSTED")
        return self._move(child, inv, _P.EVALUATING, _P.NEEDS_EVIDENCE, "MORE_EVIDENCE_USEFUL")

    @staticmethod
    def _parent_declined_an_experiment(inv: str, state: KernelState) -> bool:
        """A parent's REJECT stands for the rest of the investigation: code stops offering
        the model the experiment kind, so the parent is not asked again and again."""
        return any(
            approval.state is ApprovalState.REJECTED
            and state.experiments[approval.experiment_id].experiment.investigation_id == inv
            for approval in state.approvals.values()
        )

    def _seek_approval(self, child: str, inv: str, experiment_ids: list[str]) -> bool:
        """Classify each proposal (POLICY) and ask the opening parent to decide the eligible
        ones. True when at least one now awaits a parent's decision."""
        assert self._experiments is not None
        for experiment_id in experiment_ids:
            self._experiments.classify(child, experiment_id)
        state = self._ledger.replay_events(child)
        opener = state.entities[inv].entity.opened_by
        if opener.kind is ActorKind.PARENT:
            for experiment_id in experiment_ids:
                self._experiments.request_approval(child, experiment_id, parent_id=opener.actor_id)
            state = self._ledger.replay_events(child)
        statuses = [state.experiments[e].status for e in experiment_ids]
        self._telemetry.emit(
            "investigation.experiments",
            {
                "child_id": child,
                "investigation_id": inv,
                "count": len(experiment_ids),
                "status": ",".join(sorted({s.value for s in statuses})),
            },
        )
        return ExperimentStatus.AWAITING_APPROVAL in statuses

    def _needs_approval(self, child: str, inv: str, state: KernelState) -> StepResult:
        if self._experiments is not None:
            self._experiments.run_timers(child)  # approval expiry parks; never approves
            state = self._ledger.replay_events(child)
        if self._approvals is not None:
            self._approvals.prompt_pending_approvals(child)  # idempotent re-delivery
        records = [r for r in state.experiments.values() if r.experiment.investigation_id == inv]
        if any(r.status is ExperimentStatus.PARKED_UNRESOLVED for r in records):
            return self._park(child, inv, _P.NEEDS_APPROVAL, "APPROVAL_TIMED_OUT")
        if records and all(r.status in _DECIDED_EXPERIMENT for r in records):
            return self._move(child, inv, _P.NEEDS_APPROVAL, _P.EVALUATING, "APPROVAL_DECIDED")
        return StepResult(inv, _P.NEEDS_APPROVAL, None, "WAITING_FOR_APPROVAL", waiting=True)

    # ------------------------------------------------------------------ helpers
    def _context(self, state: KernelState, child: str, inv: str) -> InvestigationContext:
        ctx = self._retriever.retrieve(
            state, child_id=child, investigation_id=inv, now=self._clock.now()
        )
        self._telemetry.emit(
            "context.retrieve",
            {
                "child_id": child,
                "investigation_id": inv,
                "context_digest": ctx.digest,
                "experience_count": len(ctx.experience),
                "memory_count": len(ctx.memory),
                "belief_count": len(ctx.belief),
                "disagreement_count": sum(1 for d in ctx.disagreements if d.diverges),
                "hypothesis_ids": tuple(b.entity_id for b in ctx.live_hypotheses()),
            },
        )
        return ctx

    def _select(
        self,
        child: str,
        inv: str,
        state: KernelState,
        ctx: InvestigationContext | None = None,
    ) -> Selection | None:
        """Plan + select. None means the planner failed: never read as 'sufficient'."""
        ctx = ctx or self._context(state, child, inv)
        try:
            candidates = self._planner.plan_evidence(ctx)
        except Exception:  # untrusted planner (model); failure parks, it never completes
            return None
        selection = self._policy.select(candidates, ctx)
        chosen = selection.chosen
        self._telemetry.emit(
            "evidence.select",
            {
                "child_id": child,
                "investigation_id": inv,
                "candidate_count": len(candidates),
                "decision": "SUFFICIENT" if chosen is None else "SELECTED",
                "information_value": "" if chosen is None else chosen.information_value.value,
                "acquisition_mode": (
                    "" if chosen is None else chosen.candidate.acquisition_mode.value
                ),
                "reason_codes": tuple(reason for _, reason in selection.excluded),
                "policy_version": selection.policy_version,
            },
        )
        return selection

    def _model_runs_used(self, child: str, inv: str) -> int:
        used = 0
        for event in self._ledger.get_events_for_child(child):
            if event.event_type is EventType.INVESTIGATION_PHASE_CHANGED:
                payload = event.payload
                if payload["investigation_id"] == inv and payload["from_phase"] in {
                    p.value for p in _MODEL_PHASES
                }:
                    used += 1
        return used

    def _model_step(
        self,
        child: str,
        inv: str,
        state: KernelState,
        *,
        phase: InvestigationPhase,
        goal: str,
        kinds: set[ProposalKind],
    ) -> BoundaryReport | StepResult:
        used = self._model_runs_used(child, inv)
        if used >= self._budget.max_model_runs:
            return self._park(child, inv, phase, "MODEL_BUDGET_EXHAUSTED")
        task = AgentTask(
            task_id=f"{phase.value.lower()[:4]}-{inv[4:16]}-{used + 1}",
            child_id=child,
            investigation_id=inv,
            goal=goal,
            max_steps=self._budget.model_steps,
            max_cost_micro_usd=self._budget.model_cost_micro_usd,
            proposal_kinds=tuple(sorted(kinds)),
        )
        try:
            result = self._runtime.run(task)
        except Exception as exc:  # untrusted infrastructure; never crashes the controller
            return self._park(child, inv, phase, f"RUNTIME_{type(exc).__name__.upper()[:40]}")
        report = self._boundary.admit(task, result, allowed_kinds=kinds)
        if report.run_status != "COMPLETED":
            return self._park(child, inv, phase, f"RUNTIME_{report.run_status}")
        self._telemetry.emit(
            "investigation.hypotheses",
            {
                "child_id": child,
                "investigation_id": inv,
                "task_id": task.task_id,
                "hypothesis_ids": tuple(
                    o.entity_id for o in report.admitted("hypothesis") if o.entity_id
                ),
                "admitted": len(report.admitted()),
                "refused": len(report.refused()),
            },
        )
        return report

    def _recorded_at(self, child: str, event_id: str) -> datetime | None:
        for event in self._ledger.get_events_for_child(child):
            if event.event_id == event_id:
                return event.recorded_at
        return None

    def _move(
        self, child: str, inv: str, frm: InvestigationPhase, to: InvestigationPhase, *reasons: str
    ) -> StepResult:
        try:
            self._append(
                EventType.INVESTIGATION_PHASE_CHANGED,
                child,
                InvestigationPhaseChanged(
                    investigation_id=inv, from_phase=frm, to_phase=to, reason_codes=reasons
                ),
            )
        except AdmissionRejected as exc:
            self._telemetry.emit(
                "investigation.transition",
                {
                    "child_id": child,
                    "investigation_id": inv,
                    "from_phase": frm.value,
                    "to_phase": to.value,
                    "decision": "REJECTED",
                    "reason_codes": tuple(r.split(":", 1)[0] for r in exc.reason_codes),
                },
            )
            return StepResult(inv, frm, None, "TRANSITION_REFUSED", exc.reason_codes)
        self._telemetry.emit(
            "investigation.transition",
            {
                "child_id": child,
                "investigation_id": inv,
                "from_phase": frm.value,
                "to_phase": to.value,
                "decision": "ADMITTED",
                "reason_codes": tuple(r.split(":", 1)[0] for r in reasons),
            },
        )
        return StepResult(inv, frm, to, "TRANSITIONED", tuple(reasons))

    def _park(self, child: str, inv: str, frm: InvestigationPhase, reason: str) -> StepResult:
        return self._move(child, inv, frm, _P.PARKED_UNRESOLVED, reason)

    def _append(
        self,
        event_type: EventType,
        child_id: str,
        payload: EventPayload,
        *,
        actor: ActorRef | None = None,
        source: SourceRef | None = None,
    ) -> None:
        self._ledger.append_event(
            EventDraft(
                event_type=event_type,
                child_id=child_id,
                source=source or SourceRef(kind=SourceKind.KERNEL, source_id=self._new_id("src")),
                actor=actor or self._system,
                occurred_at=self._clock.now(),
                verification_status=VerificationStatus.NOT_APPLICABLE,
                payload=payload,
            )
        )


def selection_summary(selection: Selection) -> dict[str, object]:
    """Codes-only summary of a selection for traces and eval reports."""
    chosen = selection.chosen
    return {
        "chosen": None if chosen is None else chosen.candidate.candidate_id,
        "information_value": None if chosen is None else chosen.information_value.value,
        "ranked": [s.candidate.candidate_id for s in selection.ranked],
        "excluded": [list(e) for e in selection.excluded],
    }
