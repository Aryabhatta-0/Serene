"""Structural requirements for N-of-1 experiments (issues #25, #26).

An experiment is admissible for approval only if it is explicit (a real
intervention, outcome measure and comparison), reversible, minimal and
context-limited. These checks are lexical/structural and deterministic; they
complement - never replace - the GREEN/AMBER/RED classifier, and like it they
are recomputed at every gate (approval request, grant, start).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Final

from serene.domain.entities import Experiment
from serene.projections.state import ExperimentRecord, KernelState

POLICY_VERSION: Final = "experiment-requirements/1"

MAX_EXPERIMENT_CONTEXTS: Final = 4
MIN_SPEC_CHARS: Final = 8
# WAITING_FOR_OUTCOME lasts the declared duration plus this grace period, then times out.
OUTCOME_GRACE: Final = timedelta(days=3)

_PLACEHOLDERS: Final = frozenset(
    {"", "na", "n a", "none", "tbd", "todo", "unknown", "same", "nothing", "x", "tba", "null"}
)
_NON_WORD = re.compile(r"[^a-z0-9]+")


def _normalized(text: str) -> str:
    return _NON_WORD.sub(" ", text.lower()).strip()


def _explicit(text: str) -> bool:
    norm = _normalized(text)
    return norm not in _PLACEHOLDERS and len(norm) >= MIN_SPEC_CHARS


def requirement_violations(experiment: Experiment, state: KernelState) -> list[str]:
    """Reasons an experiment is not explicit, minimal and context-limited. Empty == ok."""
    reasons: list[str] = []
    intervention = experiment.intervention
    if not _explicit(intervention.description):
        reasons.append("MISSING_INTERVENTION")
    if not _explicit(experiment.outcome_measure):
        reasons.append("MISSING_OUTCOME_MEASURE")
    if not _explicit(experiment.comparison):
        reasons.append("MISSING_COMPARISON")
    specs = {
        _normalized(intervention.description),
        _normalized(experiment.outcome_measure),
        _normalized(experiment.comparison),
    }
    if len(specs) < 3:
        reasons.append("INDISTINCT_SPECIFICATION")
    if not intervention.reversible:
        reasons.append("NOT_REVERSIBLE")
    if len(experiment.scope.contexts) > MAX_EXPERIMENT_CONTEXTS:
        reasons.append("SCOPE_TOO_BROAD")
    if len(set(experiment.scope.contexts)) != len(experiment.scope.contexts):
        reasons.append("DUPLICATE_CONTEXTS")

    hypothesis = state.entities.get(experiment.hypothesis_id)
    if hypothesis is None:
        reasons.append("UNKNOWN_HYPOTHESIS")
    else:
        broadened = set(experiment.scope.contexts) - set(hypothesis.entity.scope.contexts)
        if broadened:
            reasons.append("SCOPE_EXCEEDS_HYPOTHESIS")
        if hypothesis.entity.investigation_id != experiment.investigation_id:
            reasons.append("INVESTIGATION_MISMATCH")
    return reasons


def outcome_due_at(record: ExperimentRecord) -> datetime | None:
    """End of WAITING_FOR_OUTCOME: declared duration plus grace, from the ledger start time."""
    if record.started_at is None:
        return None
    days = record.experiment.intervention.max_duration_days
    return record.started_at + timedelta(days=days) + OUTCOME_GRACE
