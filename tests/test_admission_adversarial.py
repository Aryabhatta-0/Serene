"""Branch-B owner review of PR #65: adversarial writes that bypass InvestigationService.

Every case appends straight to the ledger (or calls admission on a ledger-derived
state), so nothing here relies on the controller behaving. The ledger itself must
refuse, and a refusal must leave the chain head untouched.
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from serene.adapters.browser import SafeHttpsFetcher
from serene.domain.entities import Hypothesis, Scope
from serene.domain.entities import InvestigationPhase as P
from serene.domain.events import (
    AcquisitionMode,
    EventDraft,
    EventType,
    EvidenceAcquired,
    EvidenceRequested,
    HypothesisPrediction,
    HypothesisProposed,
    InformationValue,
    InvestigationPhaseChanged,
    PredictedAnswer,
)
from serene.domain.values import VerificationStatus
from serene.ledger.service import AdmissionRejected
from serene.policies.admission import admission_violations
from serene.policies.external_evidence import _LABEL, domain_allowed, host_of
from serene.policies.investigation import HYPOTHESIS_PHASES
from serene.testing import SyntheticFamily
from serene.testing.synthetic import DEFAULT_CONTEXTS
from tests.evidence_support import browse_reply
from tests.test_evidence_path import _acquired

# ---------------------------------------------------------------- helpers


def _phase(fam: SyntheticFamily, inv: str, frm: P, to: P) -> None:
    fam.append(
        fam.draft(
            EventType.INVESTIGATION_PHASE_CHANGED,
            fam.system,
            InvestigationPhaseChanged(
                investigation_id=inv, from_phase=frm, to_phase=to, reason_codes=("TEST",)
            ),
        )
    )


def _hypothesis_draft(fam: SyntheticFamily, inv: str, pattern: Any, statement: str) -> EventDraft:
    """A HYPOTHESIS_PROPOSED draft built by hand: no phase walk, no service."""
    parents = (pattern.pattern_id,)
    hypothesis = Hypothesis(
        child_id=fam.child_id,
        provenance=fam._agent_provenance(parents),
        hypothesis_id=fam.new_id("hyp"),
        investigation_id=inv,
        statement=statement,
        pattern_ids=parents,
        alternative_explanations=("end-of-day tiredness",),
        known_confounders=("variable nap length",),
        falsification_criteria=("calm pickups continue without the intervention",),
        scope=Scope(child_id=fam.child_id, contexts=DEFAULT_CONTEXTS),
    )
    return fam.draft(
        EventType.HYPOTHESIS_PROPOSED,
        fam.agent,
        HypothesisProposed(hypothesis=hypothesis),
        status=VerificationStatus.UNVERIFIED,
        derived_from=fam._events_for(parents),
    )


def _rejected(fam: SyntheticFamily, draft: EventDraft) -> tuple[str, ...]:
    head = fam.state().last_event_hash
    with pytest.raises(AdmissionRejected) as exc:
        fam.append(draft)
    assert fam.state().last_event_hash == head  # a refusal never moves the chain
    return exc.value.reason_codes


@pytest.fixture
def setup() -> tuple[SyntheticFamily, str, Any, list[str]]:
    """An investigation in NEEDS_EVIDENCE with two competing hypotheses."""
    fam = SyntheticFamily(seed="adversarial")
    o1 = fam.observe("tearful pickup", day=0)
    o2 = fam.observe("tearful pickup again", day=1)
    pattern = fam.pattern((o1, o2), "pickups are tearful")
    inv = fam.open_investigation("why are pickups hard?")
    hyps = [
        fam.hypothesis(inv, (pattern,), "abrupt transitions").hypothesis_id,
        fam.hypothesis(inv, (pattern,), "hunger after daycare").hypothesis_id,
    ]
    _phase(fam, inv.investigation_id, P.FORMING_HYPOTHESES, P.NEEDS_EVIDENCE)
    return fam, inv.investigation_id, pattern, hyps


# ---------------------------------------------------------------- HYPOTHESIS_PROPOSED phases


def test_a_hypothesis_cannot_enter_while_understanding_the_question() -> None:
    fam = SyntheticFamily(seed="adv-understanding")
    o1 = fam.observe("tearful pickup", day=0)
    o2 = fam.observe("tearful pickup again", day=1)
    pattern = fam.pattern((o1, o2), "pickups are tearful")
    inv = fam.open_investigation("why?").investigation_id
    draft = _hypothesis_draft(fam, inv, pattern, "abrupt transitions")
    assert _rejected(fam, draft) == ("WRONG_PHASE:UNDERSTANDING",)
    _phase(fam, inv, P.UNDERSTANDING, P.RETRIEVING_CONTEXT)
    assert _rejected(fam, draft) == ("WRONG_PHASE:RETRIEVING_CONTEXT",)
    _phase(fam, inv, P.RETRIEVING_CONTEXT, P.FORMING_HYPOTHESES)
    fam.append(draft)  # the one legal entry point while forming


def test_a_hypothesis_cannot_enter_while_evidence_is_being_gathered(setup: Any) -> None:
    fam, inv, pattern, _ = setup
    draft = _hypothesis_draft(fam, inv, pattern, "a late third explanation")
    assert _rejected(fam, draft) == ("WRONG_PHASE:NEEDS_EVIDENCE",)


@pytest.mark.parametrize("phase", list(P))
def test_hypothesis_admission_is_decided_by_phase_alone(setup: Any, phase: P) -> None:
    """Admission on a ledger-derived state with the phase forced: every phase is decided."""
    fam, inv, pattern, _ = setup
    draft = _hypothesis_draft(fam, inv, pattern, "a forced-phase explanation")
    state = fam.state()
    state.investigation_phases[inv] = phase
    reasons = admission_violations(draft, state, fam.clock.now())
    if phase in HYPOTHESIS_PHASES:
        assert reasons == []
    elif phase in (P.COMPLETE, P.PARKED_UNRESOLVED):
        assert reasons == [f"INVESTIGATION_PHASE_TERMINAL:{phase.value}"]
    else:
        assert reasons == [f"WRONG_PHASE:{phase.value}"]


def test_a_hypothesis_for_an_unknown_investigation_is_refused(setup: Any) -> None:
    fam, _, pattern, _ = setup
    draft = _hypothesis_draft(fam, fam.new_id("inv"), pattern, "orphan")
    assert "UNKNOWN_INVESTIGATION" in _rejected(fam, draft)


# ---------------------------------------------------------------- EVIDENCE_REQUESTED authority


def _request(
    fam: SyntheticFamily, inv: str, hyps: list[str], **overrides: Any
) -> EvidenceRequested:
    base: dict[str, Any] = {
        "request_id": fam.new_id("erq"),
        "investigation_id": inv,
        "requested_fields": ("snack_before_pickup",),
        "information_value": InformationValue.HIGH,
        "rationale": "discriminates hunger from transitions",
        "acquisition_mode": AcquisitionMode.ASK_PARENT,
        "question": "Did he eat a snack before pickup today?",
        "predictions": (
            HypothesisPrediction(hypothesis_id=hyps[0], expected=PredictedAnswer.YES),
            HypothesisPrediction(hypothesis_id=hyps[1], expected=PredictedAnswer.NO),
        ),
    }
    base.update(overrides)
    return EvidenceRequested(**base)


def _requested(fam: SyntheticFamily, payload: EvidenceRequested, actor: Any = None) -> EventDraft:
    return fam.draft(EventType.EVIDENCE_REQUESTED, actor or fam.system, payload)


def test_the_model_cannot_record_an_evidence_request(setup: Any) -> None:
    fam, inv, _, hyps = setup
    draft = _requested(fam, _request(fam, inv, hyps), actor=fam.agent)
    assert _rejected(fam, draft) == ("ACTOR_NOT_PERMITTED:AGENT",)
    fam.append(_requested(fam, _request(fam, inv, hyps)))  # the kernel's own record is fine


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"predictions": ()}, "LOW_VALUE_REQUEST"),
        ({"predictions": "one"}, "INFORMATION_VALUE_INFLATED:MEDIUM"),
        ({"predictions": "twice"}, "DUPLICATE_PREDICTION"),
        ({"predictions": "stranger"}, "PREDICTION_FOR_INACTIVE_HYPOTHESIS"),
        ({"question": "Should we withhold food until pickup goes calmly?"}, "UNSAFE_QUESTION"),
        ({"question": None}, "QUESTION_REQUIRED"),
        ({"allowed_domains": ("example.org",)}, "QUESTION_WITH_BROWSE_BOUNDS"),
        ({"acquisition_mode": AcquisitionMode.BROWSE}, "BROWSE_BOUNDS_REQUIRED"),
        (
            {
                "acquisition_mode": AcquisitionMode.BROWSE,
                "subject": "daycare_pickup",
                "allowed_domains": ("example.org",),
            },
            "BROWSE_WITH_QUESTION",
        ),
        ({"acquisition_mode": None}, "ACQUISITION_MODE_REQUIRED"),
    ],
)
def test_a_recorded_request_must_be_one_code_could_have_selected(
    setup: Any, overrides: dict[str, Any], reason: str
) -> None:
    fam, inv, _, hyps = setup
    predictions = {
        "one": (HypothesisPrediction(hypothesis_id=hyps[0], expected=PredictedAnswer.YES),),
        "twice": (
            HypothesisPrediction(hypothesis_id=hyps[0], expected=PredictedAnswer.YES),
            HypothesisPrediction(hypothesis_id=hyps[0], expected=PredictedAnswer.NO),
        ),
        "stranger": (
            HypothesisPrediction(hypothesis_id=hyps[0], expected=PredictedAnswer.YES),
            HypothesisPrediction(hypothesis_id=fam.new_id("hyp"), expected=PredictedAnswer.NO),
        ),
    }
    if isinstance(overrides.get("predictions"), str):
        overrides = {**overrides, "predictions": predictions[overrides["predictions"]]}
    codes = _rejected(fam, _requested(fam, _request(fam, inv, hyps, **overrides)))
    assert any(c.split(":", 1)[0] == reason.split(":", 1)[0] for c in codes), codes
    if ":" in reason and reason.split(":", 1)[0] != "PREDICTION_FOR_INACTIVE_HYPOTHESIS":
        assert reason in codes


def test_a_second_request_waits_for_the_first_and_never_repeats_it(setup: Any) -> None:
    fam, inv, _, hyps = setup
    fam.append(_requested(fam, _request(fam, inv, hyps)))
    again = _request(fam, inv, hyps, requested_fields=("nap_length",))
    assert "OPEN_REQUEST_OUTSTANDING" in _rejected(fam, _requested(fam, again))
    same = _request(fam, inv, hyps)
    assert "REDUNDANT_FIELDS" in _rejected(fam, _requested(fam, same))


def test_a_request_outside_needs_evidence_is_refused() -> None:
    fam = SyntheticFamily(seed="adv-phase")
    o1 = fam.observe("tearful pickup", day=0)
    o2 = fam.observe("tearful pickup again", day=1)
    pattern = fam.pattern((o1, o2), "pickups are tearful")
    inv = fam.open_investigation("why?")
    hyps = [
        fam.hypothesis(inv, (pattern,), "abrupt transitions").hypothesis_id,
        fam.hypothesis(inv, (pattern,), "hunger after daycare").hypothesis_id,
    ]
    draft = _requested(fam, _request(fam, inv.investigation_id, hyps))
    assert _rejected(fam, draft) == ("WRONG_PHASE:FORMING_HYPOTHESES",)


# ---------------------------------------------------------------- fail-closed URLs

MALFORMED = [
    "https://example.org:abc/p",  # textual port (urlsplit .port raises)
    "https://example.org:99999/p",  # out-of-range port (raises)
    "https://example.org:8443/p",  # non-default port
    "https://[::1/p",  # unbalanced IPv6 bracket (urlsplit raises)
    "https://[::1]/p",  # IP literal
    "https://127.0.0.1/p",  # IP literal, private
    "https://169.254.169.254/latest/meta-data",  # metadata IP literal
    "https://exa mple.org/p",  # whitespace in host
    "https://%65xample.org/p",  # percent-encoded host
    "https://example..org/p",  # empty label
    "https://-example.org/p",  # leading hyphen
    "https://user@example.org/p",  # userinfo
    "https://user:pw@example.org/p",  # credentials
    "https://:@example.org/p",  # empty credentials
    "https://example.org\\@evil.org/p",  # backslash authority confusion
    "http://example.org/p",  # not https
    "ftp://example.org/p",
    "javascript:alert(1)",
    "//example.org/p",
    "",
    "https://",
]


@pytest.mark.parametrize("url", MALFORMED)
def test_malformed_urls_are_refused_deterministically(url: str) -> None:
    assert host_of(url) is None
    assert not domain_allowed(host_of(url), ("example.org", "evil.org"))


@given(st.text(max_size=80))
def test_host_of_never_raises_and_only_returns_dns_names(text: str) -> None:
    for candidate in (text, f"https://{text}", f"https://example.org:{text}/x"):
        host = host_of(candidate)
        assert host is None or all(_LABEL.match(label) for label in host.split("."))


def test_well_formed_urls_still_pass() -> None:
    assert host_of("https://Example.ORG./p?q=1") == "example.org"
    assert host_of("https://example.org:443/p") == "example.org"
    assert host_of("https://raw.githubusercontent.com/a/b") == "raw.githubusercontent.com"


class _Conn:
    def __init__(self, log: list[str], status: int, location: str = "") -> None:
        self._log, self.status, self._location = log, status, location

    def request(self, method: str, path: str, headers: dict[str, str]) -> None:
        self._log.append(path)

    def getresponse(self) -> Any:
        conn = self

        class _R:
            status = conn.status
            headers = type("H", (), {"get_content_charset": lambda self: "utf-8"})()

            def read(self, n: int) -> bytes:
                return b"<p>moved</p>"

            def getheader(self, name: str) -> str:
                return conn._location

        return _R()

    def close(self) -> None:
        return None


@pytest.mark.parametrize("url", MALFORMED)
def test_the_verifier_fetcher_never_connects_for_a_malformed_url(url: str) -> None:
    connects: list[str] = []
    fetcher = SafeHttpsFetcher(
        resolver=lambda host: ["93.184.216.34"],
        connection_factory=lambda host, addr: _Conn(connects, 200),  # type: ignore[arg-type,return-value]
    )
    assert fetcher.fetch(url, ("example.org", "evil.org")) is None
    assert connects == []


@pytest.mark.parametrize(
    "location", ["https://10.0.0.5/x", "https://127.0.0.1/", "http://example.org/"]
)
def test_a_redirect_to_a_private_target_is_never_followed(location: str) -> None:
    connects: list[str] = []
    fetcher = SafeHttpsFetcher(
        resolver=lambda host: ["93.184.216.34"],
        connection_factory=lambda host, addr: _Conn(connects, 302, location),  # type: ignore[arg-type,return-value]
    )
    assert fetcher.fetch("https://example.org/p", ("example.org",)) is None
    assert connects == ["/p"]  # one request, to the vetted address; the 3xx is not followed


def test_a_host_resolving_to_a_private_address_is_never_contacted() -> None:
    connects: list[str] = []
    fetcher = SafeHttpsFetcher(
        resolver=lambda host: ["10.1.2.3"],
        connection_factory=lambda host, addr: _Conn(connects, 200),  # type: ignore[arg-type,return-value]
    )
    assert fetcher.fetch("https://example.org/p", ("example.org",)) is None
    assert connects == []


@pytest.mark.parametrize(
    "uri", ["https://example.org:abc/p", "https://u:p@example.org/p", "https://[::1]/p"]
)
def test_admission_refuses_acquired_evidence_with_a_malformed_source_url(
    setup: Any, uri: str
) -> None:
    """EVIDENCE_ACQUIRED and EVIDENCE_VERIFIED with a hostile URI: reason codes, no exception."""
    fam, inv, _, hyps = setup
    browse = _request(
        fam,
        inv,
        hyps,
        requested_fields=("pickup_window",),
        acquisition_mode=AcquisitionMode.BROWSE,
        question=None,
        subject="daycare_pickup",
        allowed_domains=("example.org",),
    )
    fam.append(_requested(fam, browse))
    result, _ = _acquired(fam, browse_reply())
    (ev,) = result.evidence
    hostile = ev.model_validate(
        {**ev.model_dump(), "source": {**ev.source.model_dump(), "uri": uri}}
    )
    draft = fam.draft(
        EventType.EVIDENCE_ACQUIRED,
        fam.system,
        EvidenceAcquired(request_id=browse.request_id, evidence=hostile),
        status=VerificationStatus.UNVERIFIED,
    )
    assert "SOURCE_DOMAIN_NOT_ALLOWED" in _rejected(fam, draft)
