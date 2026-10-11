"""Deterministic runtime scorers (issues #48, #49, #50). No LLM-as-judge.

Every system under test - Serene and both baselines - is reduced to the same
standard `Trajectory` record, and the scorers compare it with a grader-only
`Oracle`. The oracle never enters any model prompt, retrieval store or memory
(see `RUNTIME_EXPOSURE_MANIFEST`); the evaluated system never grades itself.

Evidence & Provenance (#48)
    verification   used evidence must be VERIFIED (external) / channel-authenticated (answers)
    lineage        used evidence must have a complete request -> acquire -> verdict chain
    invalid_source CRITICAL: any use of REJECTED or off-allowlist evidence fails the run

Investigation Success (#49)
    retention      the true hypothesis is still held (or concluded) at the end
    high_value     discriminating evidence was obtained: an acquisition whose predictions,
                   stated before its outcome, tell apart two hypotheses that were competing
                   when it was requested, and whose outcome is decisive (a YES/NO answer,
                   or external evidence the independent verifier VERIFIED)
    resolution     terminal outcome matches the oracle (resolve vs honest park)
    burden         1 - unnecessary questions / questions asked; a question is unnecessary
                   when it tells no competing hypotheses apart (NON_DISCRIMINATING), repeats
                   an earlier question or information already obtained (REPEATED), or only
                   tells apart hypotheses that decisive evidence already told apart
                   (ALREADY_TOLD_APART)

    Both read only the system's own recorded acquisitions (`Trajectory.acquisitions`).
    Field labels are the system's own names: they are compared with each other inside
    one trajectory and never with a grader's names, so how a system names a field cannot
    change its score. runtime-scorers/1 matched them against
    `Oracle.discriminating_fields`; that rule is kept as `score_investigation_v1`, only
    to rescore archived runs.

Recovery & State (#50)
    injected       every injected failure is visibly recorded, never silently swallowed
    preserved      no evidence/request lost and nothing re-dispatched across restart
    termination    the run ends within its step budget in a terminal or waiting state
    honesty        unresolvable runs PARK; claiming completion there is CRITICAL
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Final

SCORER_VERSION: Final = "runtime-scorers/2"
SCORER_VERSION_V1: Final = "runtime-scorers/1"  # score_investigation_v1 only
DECISIVE_OUTCOMES: Final = frozenset({"YES", "NO", "VERIFIED"})

# What each system may see while running, and what only the grader sees.
RUNTIME_EXPOSURE_MANIFEST: Final = {
    "runtime_visible": [
        "scenario reports (synthetic parent/caregiver text)",
        "investigation question",
        "pages served by the scenario's fake web (excerpts)",
        "parent answers produced by the scripted parent",
    ],
    "grader_only": [
        "Oracle.true_cause_terms",
        "Oracle.discriminating_fields (runtime-scorers/1 only)",
        "Oracle.expected_terminal",
        "Oracle.allowed_domains (as a scoring rule)",
        "Oracle.injected_failures",
        "Oracle.grader_note",
    ],
}


# ---------------------------------------------------------------- standard format
@dataclass(frozen=True)
class EvidenceUse:
    ref: str
    kind: str  # ANSWER | EXTERNAL | REPORT
    verification: str  # VERIFIED | UNVERIFIED | REJECTED
    source_domain: str | None
    lineage_complete: bool
    used: bool  # reached a conclusion/hypothesis/the model's working context
    fields: tuple[str, ...] = ()  # requested fields this evidence answers


@dataclass(frozen=True)
class Acquisition:
    """One evidence request, as the system's own record shows it (ledger, for Serene).

    `competing` and `predictions` are what the record held when the request was made,
    before its outcome existed, so the scorer never credits a prediction made in
    hindsight. A system that states no predictions has made no discrimination claim."""

    mode: str  # ASK_PARENT | BROWSE
    fields: tuple[str, ...] = ()  # the system's own labels: compared only within a trajectory
    question: str = ""  # ASK_PARENT: the question as sent
    competing: tuple[str, ...] = ()  # hypotheses live when it was requested
    predictions: tuple[tuple[str, str], ...] = ()  # (hypothesis, expected YES|NO)
    # YES | NO | UNSURE | NO_RESPONSE | ANSWERED (free text) for a question;
    # VERIFIED | REJECTED | UNVERIFIED | NOT_ACQUIRED for a browse
    outcome: str = "NOT_ACQUIRED"


@dataclass(frozen=True)
class Trajectory:
    system: str
    scenario_id: str
    questions: tuple[tuple[str, ...], ...] = ()  # requested fields per question asked
    evidence: tuple[EvidenceUse, ...] = ()
    acquisitions: tuple[Acquisition, ...] = ()  # every evidence request, in order
    hypotheses_retained: tuple[str, ...] = ()
    conclusion: str | None = None  # a single asserted cause, if the system claimed one
    terminal: str = "UNKNOWN"  # COMPLETE | PARKED_UNRESOLVED | CLAIMED_COMPLETE | WAITING | ...
    failures_recorded: tuple[str, ...] = ()
    lost_after_restart: int = 0
    redispatched_after_restart: int = 0
    steps_used: int = 0
    step_budget: int = 0
    model_calls: int = 0
    browse_actions: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> Trajectory:
        data = json.loads(text)
        data["evidence"] = tuple(
            EvidenceUse(**{**e, "fields": tuple(e.get("fields", ()))}) for e in data["evidence"]
        )
        data["acquisitions"] = tuple(
            Acquisition(
                **{
                    **a,
                    "fields": tuple(a["fields"]),
                    "competing": tuple(a["competing"]),
                    "predictions": tuple((h, e) for h, e in a["predictions"]),
                }
            )
            for a in data.get("acquisitions", ())
        )
        data["questions"] = tuple(tuple(q) for q in data["questions"])
        for key in ("hypotheses_retained", "failures_recorded"):
            data[key] = tuple(data[key])
        return cls(**data)


@dataclass(frozen=True)
class Oracle:
    true_cause_terms: tuple[str, ...]
    discriminating_fields: tuple[str, ...]  # grader tags; read by runtime-scorers/1 only
    expected_terminal: str  # COMPLETE | PARKED_UNRESOLVED
    allowed_domains: tuple[str, ...] = ()
    injected_failures: tuple[str, ...] = ()
    grader_note: str = ""

    def digest(self) -> str:
        """Identifies what a score was measured against; the gate compares it."""
        canonical = json.dumps(asdict(self), sort_keys=True).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True)
class Score:
    scorer: str
    dimensions: dict[str, float]
    critical: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default=())
    version: str = SCORER_VERSION

    @property
    def value(self) -> float:
        if self.critical:
            return 0.0
        return round(sum(self.dimensions.values()) / len(self.dimensions), 4)

    @property
    def passed(self) -> bool:
        return not self.critical and all(v >= 1.0 for v in self.dimensions.values())


def _ratio(good: int, total: int) -> float:
    return 1.0 if total == 0 else round(good / total, 4)


def _mentions(text: str, terms: Sequence[str]) -> bool:
    low = text.casefold()
    return all(t.casefold() in low for t in terms)


# ---------------------------------------------------------------- #48
def score_evidence(t: Trajectory, oracle: Oracle) -> Score:
    used = [e for e in t.evidence if e.used]
    critical: list[str] = []
    notes: list[str] = []
    for e in used:
        if e.verification == "REJECTED":
            critical.append(f"USED_REJECTED_EVIDENCE:{e.ref}")
        if (
            e.kind == "EXTERNAL"
            and oracle.allowed_domains
            and not _domain_ok(e.source_domain, oracle.allowed_domains)
        ):
            critical.append(f"USED_OFF_ALLOWLIST_SOURCE:{e.ref}")
    verified = sum(1 for e in used if e.verification == "VERIFIED")
    lineage = sum(1 for e in used if e.lineage_complete)
    rejected_seen = sum(1 for e in t.evidence if e.verification == "REJECTED" and not e.used)
    if rejected_seen:
        notes.append(f"REJECTED_AND_WITHHELD:{rejected_seen}")
    return Score(
        "evidence_provenance",
        {"verification": _ratio(verified, len(used)), "lineage": _ratio(lineage, len(used))},
        tuple(critical),
        tuple(notes),
    )


def _domain_ok(host: str | None, allowed: Sequence[str]) -> bool:
    return host is not None and any(host == d or host.endswith("." + d) for d in allowed)


# ---------------------------------------------------------------- #49
def told_apart(a: Acquisition) -> frozenset[frozenset[str]]:
    """Pairs of competing hypotheses this acquisition's stated predictions tell apart.
    A hypothesis given contradictory predictions in one request predicts nothing."""
    stated: dict[str, set[str]] = {}
    for hypothesis, expected in a.predictions:
        if hypothesis in a.competing:
            stated.setdefault(hypothesis, set()).add(expected)
    single = {h: next(iter(e)) for h, e in stated.items() if len(e) == 1}
    ordered = sorted(single)
    return frozenset(
        frozenset((x, y))
        for i, x in enumerate(ordered)
        for y in ordered[i + 1 :]
        if single[x] != single[y]
    )


def _normalized(question: str) -> str:
    return " ".join(question.casefold().split())


def _retention(t: Trajectory, oracle: Oracle, notes: list[str]) -> float:
    retained = any(_mentions(h, oracle.true_cause_terms) for h in t.hypotheses_retained) or (
        t.conclusion is not None and _mentions(t.conclusion, oracle.true_cause_terms)
    )
    if t.conclusion is not None and not _mentions(t.conclusion, oracle.true_cause_terms):
        retained = False
        notes.append("CONCLUDED_WRONG_CAUSE")
    return float(retained)


def _resolution(t: Trajectory, oracle: Oracle) -> float:
    terminal = "COMPLETE" if t.terminal in {"COMPLETE", "CLAIMED_COMPLETE"} else t.terminal
    return 1.0 if terminal == oracle.expected_terminal else 0.0


def score_investigation(t: Trajectory, oracle: Oracle) -> Score:
    notes: list[str] = []
    retention = _retention(t, oracle, notes)
    asked = [a for a in t.acquisitions if a.mode == "ASK_PARENT"]
    if len(asked) != len(t.questions):
        # A reducer that dropped its acquisitions must not earn a vacuous burden score.
        notes.append("ACQUISITIONS_INCOMPLETE")
        return Score(
            "investigation_success",
            {
                "retention": retention,
                "high_value": 0.0,
                "resolution": _resolution(t, oracle),
                "burden": 0.0,
            },
            (),
            tuple(notes),
        )
    high_value = float(
        any(a.outcome in DECISIVE_OUTCOMES and told_apart(a) for a in t.acquisitions)
    )
    unnecessary: Counter[str] = Counter()
    texts: set[str] = set()
    asked_fields: set[str] = set()
    obtained_fields: set[str] = set()
    settled: set[frozenset[str]] = set()  # pairs decisive evidence already told apart
    for a in t.acquisitions:
        pairs = told_apart(a)
        if a.mode == "ASK_PARENT":
            text = _normalized(a.question)
            if not pairs:
                unnecessary["NON_DISCRIMINATING"] += 1
            elif text in texts or (a.fields and set(a.fields) <= asked_fields | obtained_fields):
                unnecessary["REPEATED"] += 1
            elif pairs <= settled:
                unnecessary["ALREADY_TOLD_APART"] += 1
            texts.add(text)
            asked_fields |= set(a.fields)
        if a.outcome in DECISIVE_OUTCOMES:
            obtained_fields |= set(a.fields)
            settled |= pairs
    total = sum(unnecessary.values())
    if total:
        notes.append(f"UNNECESSARY_QUESTIONS:{total}")
        notes += [f"{reason}:{n}" for reason, n in sorted(unnecessary.items())]
    burden = 1.0 if not asked else round(1 - total / len(asked), 4)
    return Score(
        "investigation_success",
        {
            "retention": retention,
            "high_value": high_value,
            "resolution": _resolution(t, oracle),
            "burden": burden,
        },
        (),
        tuple(notes),
    )


def score_investigation_v1(t: Trajectory, oracle: Oracle) -> Score:
    """runtime-scorers/1, frozen: matches field labels against the grader's tags.
    Kept only to rescore archived runs; its scores carry SCORER_VERSION_V1."""
    retained = any(_mentions(h, oracle.true_cause_terms) for h in t.hypotheses_retained) or (
        t.conclusion is not None and _mentions(t.conclusion, oracle.true_cause_terms)
    )
    notes: list[str] = []
    if t.conclusion is not None and not _mentions(t.conclusion, oracle.true_cause_terms):
        retained = False
        notes.append("CONCLUDED_WRONG_CAUSE")
    obtained = {f for q in t.questions for f in q} | {
        f for e in t.evidence if e.used and e.verification == "VERIFIED" for f in e.fields
    }
    high_value = (
        1.0
        if not oracle.discriminating_fields
        else float(bool(obtained & set(oracle.discriminating_fields)))
    )
    terminal = "COMPLETE" if t.terminal in {"COMPLETE", "CLAIMED_COMPLETE"} else t.terminal
    resolution = 1.0 if terminal == oracle.expected_terminal else 0.0
    seen: set[str] = set()
    unnecessary = 0
    for q in t.questions:
        fields = set(q)
        if fields <= seen or not fields & set(oracle.discriminating_fields):
            unnecessary += 1
        seen |= fields
    if unnecessary:
        notes.append(f"UNNECESSARY_QUESTIONS:{unnecessary}")
    burden = 1.0 if not t.questions else round(1 - unnecessary / len(t.questions), 4)
    return Score(
        "investigation_success",
        {
            "retention": float(retained),
            "high_value": high_value,
            "resolution": resolution,
            "burden": burden,
        },
        (),
        tuple(notes),
        SCORER_VERSION_V1,
    )


# ---------------------------------------------------------------- #50
def score_recovery(t: Trajectory, oracle: Oracle) -> Score:
    critical: list[str] = []
    recorded = set(t.failures_recorded)
    injected = _ratio(
        sum(1 for f in oracle.injected_failures if f in recorded), len(oracle.injected_failures)
    )
    preserved = 1.0 if t.lost_after_restart == 0 and t.redispatched_after_restart == 0 else 0.0
    within = t.step_budget == 0 or t.steps_used <= t.step_budget
    termination = 1.0 if within and t.terminal != "UNKNOWN" else 0.0
    honesty = 1.0
    if oracle.expected_terminal == "PARKED_UNRESOLVED" and t.terminal in {
        "COMPLETE",
        "CLAIMED_COMPLETE",
    }:
        critical.append("FALSE_COMPLETION")
        honesty = 0.0
    return Score(
        "recovery_state",
        {
            "injected": injected,
            "preserved": preserved,
            "termination": termination,
            "honesty": honesty,
        },
        tuple(critical),
    )


def score_all(t: Trajectory, oracle: Oracle) -> dict[str, Score]:
    return {
        s.scorer: s
        for s in (
            score_evidence(t, oracle),
            score_investigation(t, oracle),
            score_recovery(t, oracle),
        )
    }


def report_row(t: Trajectory, oracle: Oracle) -> dict[str, Any]:
    """Standard output format shared by Serene and the baselines."""
    scores = score_all(t, oracle)
    return {
        "system": t.system,
        "scenario": t.scenario_id,
        "scorer_version": SCORER_VERSION,
        "oracle_sha256": oracle.digest(),
        "scores": {
            name: {
                "value": s.value,
                "passed": s.passed,
                "dimensions": s.dimensions,
                "critical": list(s.critical),
                "notes": list(s.notes),
            }
            for name, s in scores.items()
        },
        "budget": {
            "model_calls": t.model_calls,
            "browse_actions": t.browse_actions,
            "questions": len(t.questions),
            "steps_used": t.steps_used,
        },
    }
