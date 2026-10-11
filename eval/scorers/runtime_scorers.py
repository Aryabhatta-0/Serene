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
    high_value     at least one oracle-discriminating field was obtained
    resolution     terminal outcome matches the oracle (resolve vs honest park)
    burden         1 - unnecessary questions / questions asked (redundant or off-oracle)

Recovery & State (#50)
    injected       every injected failure is visibly recorded, never silently swallowed
    preserved      no evidence/request lost and nothing re-dispatched across restart
    termination    the run ends within its step budget in a terminal or waiting state
    honesty        unresolvable runs PARK; claiming completion there is CRITICAL
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Final

SCORER_VERSION: Final = "runtime-scorers/1"

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
        "Oracle.discriminating_fields",
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
class Trajectory:
    system: str
    scenario_id: str
    questions: tuple[tuple[str, ...], ...] = ()  # requested fields per question asked
    evidence: tuple[EvidenceUse, ...] = ()
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


@dataclass(frozen=True)
class Oracle:
    true_cause_terms: tuple[str, ...]
    discriminating_fields: tuple[str, ...]
    expected_terminal: str  # COMPLETE | PARKED_UNRESOLVED
    allowed_domains: tuple[str, ...] = ()
    injected_failures: tuple[str, ...] = ()
    grader_note: str = ""


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
def score_investigation(t: Trajectory, oracle: Oracle) -> Score:
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
