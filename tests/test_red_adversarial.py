"""RED is fail-closed at every lifecycle entry point, whatever the proposer or approver
claims (issues #22, #23)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from serene.domain.entities import Burden, InterventionCategory
from serene.domain.events import ApprovalRequested, EventType, ExperimentStarted, SafetyClass
from serene.ledger import AdmissionRejected
from serene.policies.safety import FORBIDDEN_CATEGORIES, classify_intervention, intervention_digest
from serene.testing import SyntheticFamily

from .trust_helpers import C, hypothesis, intervention, reasons, service

E = EventType


def _blocked_report(
    seed: str, iv: object
) -> tuple[SyntheticFamily, object, list[EventType], tuple[str, ...]]:
    fam = SyntheticFamily(seed=seed)
    _inv, hyp = hypothesis(fam)
    exp = fam.propose_experiment(hyp, iv)  # type: ignore[arg-type]
    report = service(fam).classify(fam.child_id, exp.experiment_id)
    types = [e.event_type for e in report.appended]
    codes = tuple(report.appended[-1].payload["reason_codes"])
    return fam, exp, types, codes


@pytest.mark.parametrize("category", sorted(FORBIDDEN_CATEGORIES))
def test_each_forbidden_category_is_blocked_at_lifecycle_entry(
    category: InterventionCategory,
) -> None:
    fam, exp, types, codes = _blocked_report(
        f"red-{category.value}", intervention(category, "A gentle evening routine change")
    )
    assert types == [E.EXPERIMENT_CLASSIFIED, E.EXPERIMENT_BLOCKED]
    assert "RED_FAIL_CLOSED" in codes and f"FORBIDDEN_CATEGORY:{category.value}" in codes
    svc = service(fam)
    assert (
        svc.request_approval(
            fam.child_id, exp.experiment_id, parent_id=fam.parent.actor_id
        ).appended
        == []
    )  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "description",
    [
        "Give a melatonin gummy before bed",
        "Try a time-out with no dinner after a meltdown",
        "Hold down gently during the tantrum",
        "Introduce peanut butter at snack time",
        "Keep awake in the car so bedtime is easier",
    ],
)
def test_forbidden_terms_escalate_a_harmless_category_to_red(description: str) -> None:
    _fam, _exp, types, codes = _blocked_report(
        "red-term", intervention(C.PLAY_ACTIVITY, description)
    )
    assert types[-1] is E.EXPERIMENT_BLOCKED
    assert "FORBIDDEN_TERM" in codes


def test_red_cannot_be_unblocked_by_any_sequence_of_forged_authority() -> None:
    fam, exp, _types, _codes = _blocked_report(
        "red-forged", intervention(C.SUPPLEMENT, "Try a calming supplement")
    )
    exp_id = exp.experiment_id  # type: ignore[attr-defined]
    with pytest.raises(AdmissionRejected) as info:
        fam.classify(exp)  # type: ignore[arg-type]  # re-classification attempt
    assert "ALREADY_CLASSIFIED" in reasons(info)
    forged_request = ApprovalRequested(
        approval_request_id=fam.new_id("apr"),
        experiment_id=exp_id,
        intervention_digest=intervention_digest(exp.intervention),  # type: ignore[attr-defined]
        safety_class=SafetyClass.GREEN,
        requested_of=fam.parent.actor_id,
        expires_at=fam.clock.now() + timedelta(hours=1),
    )
    with pytest.raises(AdmissionRejected) as info:
        fam.append(fam.draft(E.APPROVAL_REQUESTED, fam.policy, forged_request))
    assert {
        "RED_CANNOT_BE_APPROVED",
        "SAFETY_CLASS_MISMATCH",
        "EXPERIMENT_NOT_CLASSIFIED",
    } <= reasons(info)
    forged_start = ExperimentStarted(
        experiment_id=exp_id,
        approval_request_id=forged_request.approval_request_id,
        intervention_digest=intervention_digest(exp.intervention),  # type: ignore[attr-defined]
        policy_version="approval/2",
    )
    with pytest.raises(AdmissionRejected) as info:
        fam.append(fam.draft(E.EXPERIMENT_STARTED, fam.policy, forged_start))
    assert {"RED_FAIL_CLOSED", "NO_APPROVAL", "EXPERIMENT_NOT_APPROVED"} <= reasons(info)
    assert fam.state().experiments[exp_id].status.value == "BLOCKED"


@settings(max_examples=60, deadline=None)
@given(
    category=st.sampled_from(sorted(FORBIDDEN_CATEGORIES)),
    reversible=st.booleans(),
    days=st.integers(min_value=1, max_value=365),
    burden=st.sampled_from(list(Burden)),
    description=st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=80).filter(
        str.strip
    ),
)
def test_forbidden_categories_are_red_for_every_other_field_value(
    category: InterventionCategory, reversible: bool, days: int, burden: Burden, description: str
) -> None:
    iv = intervention(category, description, reversible=reversible, days=days, burden=burden)
    assert classify_intervention(iv).safety_class is SafetyClass.RED


@settings(max_examples=60, deadline=None)
@given(
    category=st.sampled_from([c for c in InterventionCategory if c not in FORBIDDEN_CATEGORIES]),
    days=st.integers(min_value=1, max_value=365),
    burden=st.sampled_from(list(Burden)),
)
def test_irreversible_is_always_red(
    category: InterventionCategory, days: int, burden: Burden
) -> None:
    iv = intervention(
        category, "a gentle routine change", reversible=False, days=days, burden=burden
    )
    assert classify_intervention(iv).safety_class is SafetyClass.RED
