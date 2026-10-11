"""Runtime -> kernel boundary (issue #2).

The only path by which anything a model produced reaches the ledger:

    AgentRuntime.run(task) -> AgentRunResult (proposals; no authority)
      -> KernelBoundary.admit: re-validate, scope-check, stamp the AGENT actor
      -> EventDraft (allow-listed proposal kinds only)
      -> EventLedger.append_event (stateful admission decides)

The boundary never appends POLICY, VERIFIER or MEMORY_COMMITTER events, never
sets a verification status other than UNVERIFIED, and never trusts the actor,
child or model a proposal claims: the kernel stamps its own AGENT actor and a
proposal claiming any other actor kind is refused as a spoof.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Final

from pydantic import ValidationError

from serene.domain.base import new_id
from serene.domain.events import (
    EventDraft,
    EventPayload,
    EventType,
    ExperimentProposed,
    HypothesisProposed,
    HypothesisSuperseded,
    MemoryPatchProposed,
    ObservationStructured,
    PatternProposed,
)
from serene.domain.values import ActorKind, ActorRef, SourceKind, SourceRef, VerificationStatus
from serene.ledger.service import AdmissionRejected, EventLedger
from serene.observability.telemetry import SafeTelemetry
from serene.ports.agent_runtime import (
    Abstain,
    AgentRunResult,
    AgentTask,
    NeedEvidence,
    ProposeExperiment,
    ProposeHypothesis,
    ProposeMemoryPatch,
    ProposeObservation,
    ProposePattern,
)
from serene.ports.clock import Clock

# Proposal kind -> the one event type it may become. Nothing else is reachable.
EVENT_FOR_KIND: Final[dict[str, EventType]] = {
    "observation": EventType.OBSERVATION_STRUCTURED,
    "pattern": EventType.PATTERN_PROPOSED,
    "hypothesis": EventType.HYPOTHESIS_PROPOSED,
    "experiment": EventType.EXPERIMENT_PROPOSED,
    "memory_patch": EventType.MEMORY_PATCH_PROPOSED,
}
INVESTIGATION_KINDS: Final = frozenset(
    {"observation", "pattern", "hypothesis", "experiment", "need_evidence", "abstain"}
)
_ENTITY_FIELD: Final = {
    "observation": "observation",
    "pattern": "pattern",
    "hypothesis": "hypothesis",
    "experiment": "experiment",
    "memory_patch": "patch",
}


@dataclass(frozen=True, slots=True)
class ProposalOutcome:
    kind: str
    admitted: bool
    entity_id: str | None
    event_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BoundaryReport:
    task_id: str
    run_status: str
    outcomes: tuple[ProposalOutcome, ...]
    evidence_hints: tuple[NeedEvidence, ...]
    abstentions: tuple[Abstain, ...]
    reason_codes: tuple[str, ...] = ()

    def admitted(self, kind: str | None = None) -> list[ProposalOutcome]:
        return [o for o in self.outcomes if o.admitted and (kind is None or o.kind == kind)]

    def refused(self) -> list[ProposalOutcome]:
        return [o for o in self.outcomes if not o.admitted]


class KernelBoundary:
    def __init__(
        self,
        ledger: EventLedger,
        clock: Clock,
        *,
        agent_actor: ActorRef,
        telemetry: SafeTelemetry | None = None,
        new_source_id: Callable[[], str] = lambda: new_id("src"),
    ) -> None:
        if agent_actor.kind is not ActorKind.AGENT:
            raise ValueError("the boundary stamps an AGENT actor only")
        self._ledger = ledger
        self._clock = clock
        self._agent = agent_actor
        self._telemetry = telemetry or SafeTelemetry()
        self._new_source_id = new_source_id

    @property
    def agent_actor(self) -> ActorRef:
        return self._agent

    def admit(
        self,
        task: AgentTask,
        result: AgentRunResult,
        *,
        allowed_kinds: Iterable[str] = INVESTIGATION_KINDS,
    ) -> BoundaryReport:
        allowed = frozenset(allowed_kinds)
        try:
            # Re-validate from serialized form: a runtime cannot hand the kernel an
            # object built with `model_construct` or mutated after validation.
            task = AgentTask.model_validate_json(task.model_dump_json(warnings=False))
            result = AgentRunResult.model_validate_json(result.model_dump_json(warnings=False))
        except (ValidationError, ValueError, TypeError):
            return self._report(task.task_id, "FAILED", (), ("MALFORMED_RUN_RESULT",))
        if result.task_id != task.task_id:
            return self._report(task.task_id, result.status, (), ("TASK_MISMATCH",))
        if result.status != "COMPLETED":
            # Proposals from a failed, cancelled or over-budget run are never admitted.
            return self._report(task.task_id, result.status, (), (f"RUN_{result.status}",))

        outcomes: list[ProposalOutcome] = []
        hints: list[NeedEvidence] = []
        abstentions: list[Abstain] = []
        for proposal in result.proposals:
            if proposal.kind not in allowed:
                outcomes.append(_refused(proposal.kind, None, "KIND_NOT_ALLOWED"))
                continue
            match proposal:
                case NeedEvidence():
                    hints.append(proposal)
                case Abstain():
                    abstentions.append(proposal)
                case (
                    ProposeObservation()
                    | ProposePattern()
                    | ProposeHypothesis()
                    | ProposeExperiment()
                    | ProposeMemoryPatch()
                ):
                    outcomes.append(self._admit_entity(task, proposal))
        return self._report(task.task_id, result.status, tuple(outcomes), (), hints, abstentions)

    # ------------------------------------------------------------------ internals
    def _admit_entity(self, task: AgentTask, proposal: Any) -> ProposalOutcome:
        kind: str = proposal.kind
        entity = getattr(proposal, _ENTITY_FIELD[kind])
        entity_id: str = entity.entity_id
        if entity.child_id != task.child_id:
            return _refused(kind, entity_id, "CHILD_MISMATCH")
        claimed = entity.provenance.created_by
        if claimed.kind is not ActorKind.AGENT:
            return _refused(kind, entity_id, f"ACTOR_SPOOF:{claimed.kind.value}")
        if entity.provenance.model != proposal.model:
            return _refused(kind, entity_id, "MODEL_MISMATCH")
        if task.investigation_id is not None and getattr(
            entity, "investigation_id", task.investigation_id
        ) != (task.investigation_id):
            return _refused(kind, entity_id, "INVESTIGATION_MISMATCH")
        try:
            stamped = _restamp(entity, self._agent)
        except ValidationError:
            return _refused(kind, entity_id, "INVALID_ENTITY")

        state = self._ledger.replay_events(task.child_id)
        parents = tuple(
            dict.fromkeys(
                state.entities[p].introduced_by
                for p in stamped.provenance.derived_from
                if p in state.entities
            )
        )
        payload: EventPayload
        match kind:
            case "observation":
                payload = ObservationStructured(observation=stamped)
            case "pattern":
                payload = PatternProposed(pattern=stamped)
            case "hypothesis":
                payload = HypothesisProposed(hypothesis=stamped)
            case "experiment":
                payload = ExperimentProposed(experiment=stamped)
            case _:
                payload = MemoryPatchProposed(patch=stamped)
        try:
            event = self._ledger.append_event(
                self._draft(EVENT_FOR_KIND[kind], task, payload, parents)
            )
        except AdmissionRejected as exc:
            return self._emit(_refused(kind, entity_id, *exc.reason_codes), task)

        event_ids = [event.event_id]
        supersedes = stamped.provenance.supersedes
        if kind == "hypothesis" and supersedes is not None:
            try:
                superseded = self._ledger.append_event(
                    self._draft(
                        EventType.HYPOTHESIS_SUPERSEDED,
                        task,
                        HypothesisSuperseded(
                            hypothesis_id=supersedes,
                            superseded_by=entity_id,
                            reason="revised by agent proposal against newer evidence",
                        ),
                        (event.event_id,),
                        status=VerificationStatus.NOT_APPLICABLE,
                    )
                )
                event_ids.append(superseded.event_id)
            except AdmissionRejected as exc:
                return self._emit(
                    ProposalOutcome(kind, True, entity_id, tuple(event_ids), exc.reason_codes),
                    task,
                )
        return self._emit(ProposalOutcome(kind, True, entity_id, tuple(event_ids), ()), task)

    def _draft(
        self,
        event_type: EventType,
        task: AgentTask,
        payload: EventPayload,
        parents: tuple[str, ...],
        *,
        status: VerificationStatus = VerificationStatus.UNVERIFIED,
    ) -> EventDraft:
        return EventDraft(
            event_type=event_type,
            child_id=task.child_id,
            source=SourceRef(kind=SourceKind.KERNEL, source_id=self._new_source_id()),
            actor=self._agent,
            occurred_at=self._clock.now(),
            derived_from=parents,
            verification_status=status,
            payload=payload,
        )

    def _emit(self, outcome: ProposalOutcome, task: AgentTask) -> ProposalOutcome:
        self._telemetry.emit(
            "boundary.proposal",
            {
                "child_id": task.child_id,
                "task_id": task.task_id,
                "investigation_id": task.investigation_id or "",
                "proposal_kind": outcome.kind,
                "decision": "ADMITTED" if outcome.admitted else "REFUSED",
                "reason_codes": tuple(r.split(":", 1)[0] for r in outcome.reason_codes),
            },
        )
        return outcome

    def _report(
        self,
        task_id: str,
        status: str,
        outcomes: tuple[ProposalOutcome, ...],
        reasons: tuple[str, ...],
        hints: Iterable[NeedEvidence] = (),
        abstentions: Iterable[Abstain] = (),
    ) -> BoundaryReport:
        report = BoundaryReport(
            task_id=task_id,
            run_status=status,
            outcomes=outcomes,
            evidence_hints=tuple(hints),
            abstentions=tuple(abstentions),
            reason_codes=reasons,
        )
        self._telemetry.emit(
            "boundary.run",
            {
                "task_id": task_id,
                "status": status,
                "admitted": len(report.admitted()),
                "refused": len(report.refused()),
                "reason_codes": reasons,
            },
        )
        return report


def _refused(kind: str, entity_id: str | None, *reasons: str) -> ProposalOutcome:
    return ProposalOutcome(kind, False, entity_id, (), tuple(reasons))


def _restamp(entity: Any, agent: ActorRef) -> Any:
    """Rebuild the entity with the kernel's AGENT actor, re-running every validator."""
    data = entity.model_dump(mode="json")
    data["provenance"]["created_by"] = agent.model_dump(mode="json")
    return type(entity).model_validate_json(json.dumps(data, sort_keys=True))
