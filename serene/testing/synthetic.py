"""Deterministic synthetic-family builder for tests, evaluation and self-checks.

Synthetic data only: no real child, family or caregiver information may ever be
used in tests, eval fixtures or demos (docs/privacy.md). Identifiers are
derived from a seed and the clock is fixed, so a scenario produces a
byte-identical ledger on every run and platform.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from serene.adapters.clock import FixedClock
from serene.adapters.in_memory_event_store import InMemoryEventStore
from serene.domain.canonical import sha256_hex
from serene.domain.entities import (
    Burden,
    Evidence,
    EvidenceKind,
    Experiment,
    Hypothesis,
    Intervention,
    InterventionCategory,
    Investigation,
    Learning,
    Observation,
    Outcome,
    OutcomeResult,
    Pattern,
    ReviewMetadata,
    ValidityWindow,
)
from serene.domain.events import (
    ApprovalGranted,
    ApprovalRequested,
    ChannelReceipt,
    DomainEvent,
    EventDraft,
    EventPayload,
    EventType,
    ExperimentClassified,
    ExperimentCompleted,
    ExperimentProposed,
    ExperimentStarted,
    HypothesisProposed,
    InvestigationOpened,
    LearningRecorded,
    ObservationReported,
    ObservationStructured,
    OutcomeReported,
    PatternProposed,
    PromotionDecisionRecord,
)
from serene.domain.values import (
    ActorKind,
    ActorRef,
    DerivationMethod,
    EpistemicLevel,
    ModelRef,
    Provenance,
    Scope,
    SourceKind,
    SourceRef,
    VerificationStatus,
)
from serene.ledger.service import EventLedger
from serene.policies import promotion, safety
from serene.ports.event_store import EventStore
from serene.projections.state import KernelState

T0 = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
SYNTHETIC_MODEL = ModelRef(
    provider="synthetic", model_id="scripted-proposer", prompt_version="test/1", runtime="scripted"
)
DEFAULT_CONTEXTS = ("daycare_pickup", "weekday_evening")


@dataclass
class SyntheticFamily:
    seed: str = "family-0"
    store: EventStore = field(default_factory=InMemoryEventStore)
    clock: FixedClock = field(default_factory=lambda: FixedClock(T0))
    _counter: int = 0
    introduced_by: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.ledger = EventLedger(self.store, self.clock, new_event_id=lambda: self.new_id("evt"))
        self.child_id = self.new_id("chd")
        self.parent = ActorRef(kind=ActorKind.PARENT, actor_id=self.new_id("act"))
        self.caregiver = ActorRef(kind=ActorKind.CAREGIVER, actor_id=self.new_id("act"))
        self.agent = ActorRef(kind=ActorKind.AGENT, actor_id=self.new_id("act"))
        self.policy = ActorRef(kind=ActorKind.POLICY, actor_id=self.new_id("act"))
        self.verifier = ActorRef(kind=ActorKind.VERIFIER, actor_id=self.new_id("act"))
        self.system = ActorRef(kind=ActorKind.SYSTEM, actor_id=self.new_id("act"))

    # ------------------------------------------------------------- primitives
    def new_id(self, prefix: str) -> str:
        self._counter += 1
        digest = hashlib.sha256(f"{self.seed}:{prefix}:{self._counter}".encode()).hexdigest()
        return f"{prefix}_{digest[:32]}"

    def source(self, kind: SourceKind = SourceKind.TELEGRAM) -> SourceRef:
        return SourceRef(kind=kind, source_id=self.new_id("src"))

    def state(self) -> KernelState:
        return self.ledger.replay_events(self.child_id)

    def draft(
        self,
        event_type: EventType,
        actor: ActorRef,
        payload: EventPayload,
        *,
        status: VerificationStatus = VerificationStatus.NOT_APPLICABLE,
        source: SourceRef | None = None,
        derived_from: tuple[str, ...] = (),
    ) -> EventDraft:
        return EventDraft(
            event_type=event_type,
            child_id=self.child_id,
            source=source or self.source(SourceKind.KERNEL),
            actor=actor,
            occurred_at=self.clock.now(),
            derived_from=derived_from,
            verification_status=status,
            payload=payload,
        )

    def append(self, draft: EventDraft) -> DomainEvent:
        self.clock.advance(timedelta(minutes=1))
        return self.ledger.append_event(draft)

    def _events_for(self, entity_ids: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self.introduced_by[e] for e in entity_ids))

    def _sources_for(self, entity_ids: tuple[str, ...]) -> tuple[str, ...]:
        state = self.state()
        out: list[str] = []
        for entity_id in entity_ids:
            record = state.entities[entity_id]
            if entity_id.startswith("evd_"):
                out.append(entity_id)
            else:
                out.extend(record.entity.provenance.source_ids)
        return tuple(dict.fromkeys(out))

    def _agent_provenance(
        self, parents: tuple[str, ...], method: DerivationMethod = DerivationMethod.MODEL_INFERENCE
    ) -> Provenance:
        return Provenance(
            created_by=self.agent,
            created_at=self.clock.now(),
            method=method,
            model=SYNTHETIC_MODEL,
            derived_from=parents,
            source_ids=self._sources_for(parents),
        )

    # ------------------------------------------------------------- ladder steps
    def report(
        self, content: str, *, observer: ActorRef | None = None, verified: bool = True
    ) -> Evidence:
        observer = observer or self.parent
        status = VerificationStatus.VERIFIED if verified else VerificationStatus.UNVERIFIED
        source = self.source(SourceKind.TELEGRAM)
        kind = (
            EvidenceKind.PARENT_REPORT
            if observer.kind is ActorKind.PARENT
            else EvidenceKind.CAREGIVER_REPORT
        )
        method = (
            DerivationMethod.PARENT_REPORT
            if observer.kind is ActorKind.PARENT
            else DerivationMethod.CAREGIVER_REPORT
        )
        evidence = Evidence(
            child_id=self.child_id,
            provenance=Provenance(
                created_by=observer,
                created_at=self.clock.now(),
                method=method,
                verification_status=status,
            ),
            evidence_id=self.new_id("evd"),
            kind=kind,
            source=source,
            observer=observer,
            captured_at=self.clock.now(),
            content=content,
            content_digest=sha256_hex(content.encode("utf-8")),
        )
        event = self.append(
            self.draft(
                EventType.OBSERVATION_REPORTED,
                observer,
                ObservationReported(evidence=evidence),
                status=status,
                source=source,
            )
        )
        self.introduced_by[evidence.evidence_id] = event.event_id
        return evidence

    def structure(
        self, evidence: tuple[Evidence, ...], statement: str, *, observed_at: datetime
    ) -> Observation:
        parents = tuple(e.evidence_id for e in evidence)
        observation = Observation(
            child_id=self.child_id,
            provenance=self._agent_provenance(parents, DerivationMethod.MODEL_EXTRACTION),
            observation_id=self.new_id("obs"),
            evidence_ids=parents,
            observer=evidence[0].observer,
            observed_at=observed_at,
            statement=statement,
            contexts=DEFAULT_CONTEXTS,
        )
        event = self.append(
            self.draft(
                EventType.OBSERVATION_STRUCTURED,
                self.agent,
                ObservationStructured(observation=observation),
                status=VerificationStatus.UNVERIFIED,
                derived_from=self._events_for(parents),
            )
        )
        self.introduced_by[observation.observation_id] = event.event_id
        return observation

    def observe(self, content: str, *, day: int) -> Observation:
        evidence = self.report(content)
        return self.structure((evidence,), content[:200], observed_at=T0 + timedelta(days=day))

    def pattern(self, observations: tuple[Observation, ...], description: str) -> Pattern:
        parents = tuple(o.observation_id for o in observations)
        pattern = Pattern(
            child_id=self.child_id,
            provenance=self._agent_provenance(parents),
            pattern_id=self.new_id("pat"),
            observation_ids=parents,
            description=description,
            contexts=DEFAULT_CONTEXTS,
        )
        event = self.append(
            self.draft(
                EventType.PATTERN_PROPOSED,
                self.agent,
                PatternProposed(pattern=pattern),
                status=VerificationStatus.UNVERIFIED,
                derived_from=self._events_for(parents),
            )
        )
        self.introduced_by[pattern.pattern_id] = event.event_id
        return pattern

    def open_investigation(self, question: str) -> Investigation:
        investigation = Investigation(
            child_id=self.child_id,
            provenance=Provenance(
                created_by=self.parent,
                created_at=self.clock.now(),
                method=DerivationMethod.PARENT_REPORT,
            ),
            investigation_id=self.new_id("inv"),
            question=question,
            opened_by=self.parent,
            opened_at=self.clock.now(),
        )
        event = self.append(
            self.draft(
                EventType.INVESTIGATION_OPENED,
                self.parent,
                InvestigationOpened(investigation=investigation),
                source=self.source(SourceKind.TELEGRAM),
            )
        )
        self.introduced_by[investigation.investigation_id] = event.event_id
        return investigation

    def hypothesis(
        self,
        investigation: Investigation,
        patterns: tuple[Pattern, ...],
        statement: str,
        *,
        contexts: tuple[str, ...] = DEFAULT_CONTEXTS,
    ) -> Hypothesis:
        parents = tuple(p.pattern_id for p in patterns)
        hypothesis = Hypothesis(
            child_id=self.child_id,
            provenance=self._agent_provenance(parents),
            hypothesis_id=self.new_id("hyp"),
            investigation_id=investigation.investigation_id,
            statement=statement,
            pattern_ids=parents,
            alternative_explanations=("hunger after daycare", "end-of-day tiredness"),
            known_confounders=("variable nap length",),
            falsification_criteria=("calm pickups continue without the intervention",),
            scope=Scope(child_id=self.child_id, contexts=contexts),
        )
        event = self.append(
            self.draft(
                EventType.HYPOTHESIS_PROPOSED,
                self.agent,
                HypothesisProposed(hypothesis=hypothesis),
                status=VerificationStatus.UNVERIFIED,
                derived_from=self._events_for(parents),
            )
        )
        self.introduced_by[hypothesis.hypothesis_id] = event.event_id
        return hypothesis

    def propose_experiment(
        self,
        hypothesis: Hypothesis,
        intervention: Intervention | None = None,
    ) -> Experiment:
        intervention = intervention or Intervention(
            category=InterventionCategory.TRANSITION_SUPPORT,
            description="Give a five-minute heads-up before leaving daycare",
            reversible=True,
            max_duration_days=7,
            burden=Burden.LOW,
        )
        parents = (hypothesis.hypothesis_id,)
        experiment = Experiment(
            child_id=self.child_id,
            provenance=self._agent_provenance(parents),
            experiment_id=self.new_id("exp"),
            hypothesis_id=hypothesis.hypothesis_id,
            investigation_id=hypothesis.investigation_id,
            intervention=intervention,
            comparison="pickups in the week before the heads-up",
            outcome_measure="parent-reported calm pickup (yes/no)",
            scope=hypothesis.scope,
        )
        event = self.append(
            self.draft(
                EventType.EXPERIMENT_PROPOSED,
                self.agent,
                ExperimentProposed(experiment=experiment),
                status=VerificationStatus.UNVERIFIED,
                derived_from=self._events_for(parents),
            )
        )
        self.introduced_by[experiment.experiment_id] = event.event_id
        return experiment

    def classify(self, experiment: Experiment) -> DomainEvent:
        decision = safety.classify_intervention(experiment.intervention)
        return self.append(
            self.draft(
                EventType.EXPERIMENT_CLASSIFIED,
                self.policy,
                ExperimentClassified(
                    experiment_id=experiment.experiment_id,
                    safety_class=decision.safety_class,
                    intervention_digest=safety.intervention_digest(experiment.intervention),
                    reason_codes=decision.reason_codes,
                    policy_version=decision.policy_version,
                ),
            )
        )

    def request_approval(self, experiment: Experiment, *, ttl_hours: int = 24) -> str:
        decision = safety.classify_intervention(experiment.intervention)
        approval_id = self.new_id("apr")
        self.append(
            self.draft(
                EventType.APPROVAL_REQUESTED,
                self.policy,
                ApprovalRequested(
                    approval_request_id=approval_id,
                    experiment_id=experiment.experiment_id,
                    intervention_digest=safety.intervention_digest(experiment.intervention),
                    safety_class=decision.safety_class,
                    requested_of=self.parent.actor_id,
                    expires_at=self.clock.now() + timedelta(hours=ttl_hours),
                ),
            )
        )
        return approval_id

    def grant_payload(self, experiment: Experiment, approval_id: str) -> ApprovalGranted:
        return ApprovalGranted(
            approval_request_id=approval_id,
            intervention_digest=safety.intervention_digest(experiment.intervention),
            acknowledged_safety_class=safety.classify_intervention(
                experiment.intervention
            ).safety_class,
            receipt=ChannelReceipt(
                channel=SourceKind.TELEGRAM,
                message_ref="tg-callback-0001",
                received_at=self.clock.now(),
            ),
        )

    def grant(self, experiment: Experiment, approval_id: str) -> DomainEvent:
        return self.append(
            self.draft(
                EventType.APPROVAL_GRANTED,
                self.parent,
                self.grant_payload(experiment, approval_id),
                source=self.source(SourceKind.TELEGRAM),
            )
        )

    def start_payload(self, experiment: Experiment, approval_id: str) -> ExperimentStarted:
        return ExperimentStarted(
            experiment_id=experiment.experiment_id,
            approval_request_id=approval_id,
            intervention_digest=safety.intervention_digest(experiment.intervention),
            policy_version="approval/1",
        )

    def start(self, experiment: Experiment, approval_id: str) -> DomainEvent:
        return self.append(
            self.draft(
                EventType.EXPERIMENT_STARTED,
                self.policy,
                self.start_payload(experiment, approval_id),
            )
        )

    def outcome(
        self,
        experiment: Experiment,
        observations: tuple[Observation, ...],
        result: OutcomeResult = OutcomeResult.SUPPORTS,
    ) -> Outcome:
        parents = tuple(o.observation_id for o in observations)
        outcome = Outcome(
            child_id=self.child_id,
            provenance=Provenance(
                created_by=self.parent,
                created_at=self.clock.now(),
                method=DerivationMethod.EXPERIMENT_OUTCOME,
                derived_from=parents,
                source_ids=self._sources_for(parents),
                verification_status=VerificationStatus.VERIFIED,
            ),
            outcome_id=self.new_id("out"),
            experiment_id=experiment.experiment_id,
            result=result,
            observation_ids=parents,
            reported_by=self.parent,
            reported_at=self.clock.now(),
            summary="pickups were calm on most heads-up days",
        )
        event = self.append(
            self.draft(
                EventType.OUTCOME_REPORTED,
                self.parent,
                OutcomeReported(outcome=outcome),
                status=VerificationStatus.VERIFIED,
                source=self.source(SourceKind.TELEGRAM),
                derived_from=self._events_for(parents),
            )
        )
        self.introduced_by[outcome.outcome_id] = event.event_id
        return outcome

    def complete(self, experiment: Experiment, outcomes: tuple[Outcome, ...]) -> DomainEvent:
        return self.append(
            self.draft(
                EventType.EXPERIMENT_COMPLETED,
                self.policy,
                ExperimentCompleted(
                    experiment_id=experiment.experiment_id,
                    outcome_ids=tuple(o.outcome_id for o in outcomes),
                ),
            )
        )

    def promotion_payload(
        self, subject_id: str, frm: EpistemicLevel, to: EpistemicLevel
    ) -> PromotionDecisionRecord:
        state = self.state()
        request = promotion.PromotionRequest(
            subject_id=subject_id,
            from_level=frm,
            to_level=to,
            requested_by=self.agent,
            rationale="scripted promotion request",
        )
        decision = promotion.evaluate_promotion(request, state)
        return PromotionDecisionRecord(
            subject_id=subject_id,
            from_level=frm,
            to_level=to,
            reason_codes=decision.reason_codes,
            policy_version=decision.policy_version,
            facts_digest=promotion.facts_digest(subject_id, decision, state),
        )

    def promote(self, subject_id: str, frm: EpistemicLevel, to: EpistemicLevel) -> DomainEvent:
        return self.append(
            self.draft(
                EventType.PROMOTION_GRANTED,
                self.policy,
                self.promotion_payload(subject_id, frm, to),
            )
        )

    def learning_candidate(
        self,
        hypothesis: Hypothesis,
        experiments: tuple[Experiment, ...],
        outcomes: tuple[Outcome, ...],
        *,
        contexts: tuple[str, ...] = DEFAULT_CONTEXTS,
        review_days: int = 60,
    ) -> Learning:
        parents = (
            hypothesis.hypothesis_id,
            *(e.experiment_id for e in experiments),
            *(o.outcome_id for o in outcomes),
        )
        now = self.clock.now()
        return Learning(
            child_id=self.child_id,
            provenance=Provenance(
                created_by=self.policy,
                created_at=now,
                method=DerivationMethod.DETERMINISTIC_RULE,
                derived_from=parents,
                source_ids=self._sources_for(parents),
                verification_status=VerificationStatus.VERIFIED,
            ),
            learning_id=self.new_id("lrn"),
            hypothesis_id=hypothesis.hypothesis_id,
            experiment_ids=tuple(e.experiment_id for e in experiments),
            outcome_ids=tuple(o.outcome_id for o in outcomes),
            statement="A five-minute heads-up helps weekday daycare pickups go calmly",
            scope=Scope(child_id=self.child_id, contexts=contexts),
            validity=ValidityWindow(valid_from=now, review_after=now + timedelta(days=review_days)),
            review=ReviewMetadata(
                reviewer=self.parent,
                retest_triggers=("daycare schedule changes", "new caregiver at pickup"),
            ),
        )

    def record_learning(self, learning: Learning, promotion_event: DomainEvent) -> DomainEvent:
        event = self.append(
            self.draft(
                EventType.LEARNING_RECORDED,
                self.policy,
                LearningRecorded(learning=learning, promotion_event_id=promotion_event.event_id),
                status=VerificationStatus.VERIFIED,
                derived_from=(*self._events_for(learning.provenance.derived_from),),
            )
        )
        self.introduced_by[learning.learning_id] = event.event_id
        return event


def build_full_ladder(seed: str = "family-0", store: EventStore | None = None) -> dict[str, Any]:
    """Walk one synthetic investigation from raw evidence to a contextual learning."""
    fam = SyntheticFamily(seed=seed, store=store or InMemoryEventStore())
    o1 = fam.observe("Pickup was hard today, lots of crying at the door", day=0)
    o2 = fam.observe("Another tearful pickup, calmer once in the car", day=1)
    o3 = fam.observe("Pickup meltdown again when I arrived without warning", day=2)
    pattern = fam.pattern((o1, o2, o3), "Weekday pickups are frequently tearful")
    investigation = fam.open_investigation("Why are daycare pickups so hard?")
    hypothesis = fam.hypothesis(
        investigation, (pattern,), "Abrupt transitions at pickup drive the distress"
    )
    experiment = fam.propose_experiment(hypothesis)
    fam.classify(experiment)
    approval_id = fam.request_approval(experiment)
    fam.grant(experiment, approval_id)
    fam.start(experiment, approval_id)
    r1 = fam.observe("Gave the heads-up, pickup was calm", day=8)
    r2 = fam.observe("Heads-up again, smooth pickup", day=9)
    outcome = fam.outcome(experiment, (r1, r2))
    fam.complete(experiment, (outcome,))
    tested = fam.promote(
        hypothesis.hypothesis_id, EpistemicLevel.HYPOTHESIS, EpistemicLevel.TESTED_HYPOTHESIS
    )
    grant5 = fam.promote(
        hypothesis.hypothesis_id,
        EpistemicLevel.TESTED_HYPOTHESIS,
        EpistemicLevel.CONTEXTUAL_LEARNING,
    )
    learning = fam.learning_candidate(hypothesis, (experiment,), (outcome,))
    fam.record_learning(learning, grant5)
    return {
        "family": fam,
        "observations": (o1, o2, o3),
        "pattern": pattern,
        "investigation": investigation,
        "hypothesis": hypothesis,
        "experiment": experiment,
        "approval_id": approval_id,
        "outcome": outcome,
        "tested_event": tested,
        "grant5_event": grant5,
        "learning": learning,
    }
