"""Shared builders for branch-B trust tests. Synthetic data only (serene.testing)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest

from serene.domain.entities import (
    Burden,
    Experiment,
    Hypothesis,
    Intervention,
    InterventionCategory,
    Investigation,
    Observation,
)
from serene.domain.events import ApprovalGranted, ChannelReceipt, DomainEvent, EventType
from serene.domain.values import ActorRef, SourceKind
from serene.experiments.lifecycle import LifecycleContext
from serene.experiments.service import ExperimentLifecycleService
from serene.ledger import AdmissionRejected
from serene.policies import safety
from serene.testing import SyntheticFamily
from serene.testing.synthetic import DEFAULT_CONTEXTS, T0

C = InterventionCategory


def reasons(info: pytest.ExceptionInfo[AdmissionRejected]) -> set[str]:
    return {r.split(":", 1)[0] for r in info.value.reason_codes}


def intervention(
    category: C = C.TRANSITION_SUPPORT,
    description: str = "Give a five-minute heads-up before leaving",
    *,
    reversible: bool = True,
    days: int = 7,
    burden: Burden = Burden.LOW,
) -> Intervention:
    return Intervention(
        category=category,
        description=description,
        reversible=reversible,
        max_duration_days=days,
        burden=burden,
    )


def ctx(fam: SyntheticFamily) -> LifecycleContext:
    return LifecycleContext(
        policy=fam.policy, system=fam.system, new_source_id=lambda: fam.new_id("src")
    )


def service(fam: SyntheticFamily) -> ExperimentLifecycleService:
    return ExperimentLifecycleService(fam.ledger, fam.clock, ctx(fam), new_entity_id=fam.new_id)


def hypothesis(
    fam: SyntheticFamily, *, contexts: tuple[str, ...] = DEFAULT_CONTEXTS
) -> tuple[Investigation, Hypothesis]:
    o1 = fam.observe("tearful pickup", day=0)
    o2 = fam.observe("tearful pickup again", day=1)
    pattern = fam.pattern((o1, o2), "pickups are tearful")
    inv = fam.open_investigation("why are pickups hard?")
    return inv, fam.hypothesis(
        inv, (pattern,), "abrupt transitions drive distress", contexts=contexts
    )


def awaiting_approval(
    fam: SyntheticFamily, iv: Intervention | None = None
) -> tuple[Experiment, str]:
    _inv, hyp = hypothesis(fam)
    exp = fam.propose_experiment(hyp, iv)
    fam.classify(exp)
    return exp, fam.request_approval(exp)


def grant_draft(
    fam: SyntheticFamily,
    exp: Experiment,
    apr: str,
    *,
    actor: ActorRef | None = None,
    source_kind: SourceKind = SourceKind.TELEGRAM,
    receipt_channel: SourceKind = SourceKind.TELEGRAM,
    received_at: datetime | None = None,
    message_ref: str | None = None,
) -> Any:
    payload = ApprovalGranted(
        approval_request_id=apr,
        intervention_digest=safety.intervention_digest(exp.intervention),
        acknowledged_safety_class=safety.classify_intervention(exp.intervention).safety_class,
        receipt=ChannelReceipt(
            channel=receipt_channel,  # type: ignore[arg-type]
            message_ref=message_ref or f"tg-callback-{apr[-12:]}",
            received_at=received_at or fam.clock.now(),
        ),
    )
    return fam.draft(
        EventType.APPROVAL_GRANTED, actor or fam.parent, payload, source=fam.source(source_kind)
    )


def observe_with_contexts(
    fam: SyntheticFamily, content: str, contexts: tuple[str, ...], *, day: int
) -> Observation:
    """A structured observation carrying specific context tags (e.g. a drift marker)."""
    from serene.domain.events import ObservationStructured
    from serene.domain.values import DerivationMethod, VerificationStatus

    evidence = fam.report(content)
    parents = (evidence.evidence_id,)
    observation = Observation(
        child_id=fam.child_id,
        provenance=fam._agent_provenance(parents, DerivationMethod.MODEL_EXTRACTION),
        observation_id=fam.new_id("obs"),
        evidence_ids=parents,
        observer=evidence.observer,
        observed_at=T0 + timedelta(days=day),
        statement=content,
        contexts=contexts,
    )
    event = fam.append(
        fam.draft(
            EventType.OBSERVATION_STRUCTURED,
            fam.agent,
            ObservationStructured(observation=observation),
            status=VerificationStatus.UNVERIFIED,
            derived_from=fam._events_for(parents),
        )
    )
    fam.introduced_by[observation.observation_id] = event.event_id
    return observation


def event_types(fam: SyntheticFamily) -> list[EventType]:
    return [e.event_type for e in fam.ledger.get_events_for_child(fam.child_id)]


def last(fam: SyntheticFamily) -> DomainEvent:
    return fam.ledger.get_events_for_child(fam.child_id)[-1]
