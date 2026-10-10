"""Which knowledge may live where in memory_repo, and at what epistemic level.

The directory decides the kind of subject a document may describe and the
minimum level that subject must have reached. The proposer declares a
`required_level` on its patch; the Critic checks it equals the level computed
here, so a patch cannot under-declare its way past the gate. Withdrawing a
document (DEPRECATE) is the fail-safe direction and needs no promotion authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from serene.domain.entities import MemoryOperation
from serene.domain.values import EpistemicLevel
from serene.memory.document import DIRECTORY_KIND, MemoryKind, directory_of

_L = EpistemicLevel


@dataclass(frozen=True, slots=True)
class PathRule:
    kind: MemoryKind
    subject_prefixes: frozenset[str]
    min_level: EpistemicLevel


PATH_RULES: Final[dict[str, PathRule]] = {
    "learnings": PathRule(MemoryKind.LEARNING, frozenset({"lrn"}), _L.CONTEXTUAL_LEARNING),
    "routines": PathRule(MemoryKind.ROUTINE, frozenset({"lrn"}), _L.CONTEXTUAL_LEARNING),
    "patterns": PathRule(MemoryKind.PATTERN, frozenset({"pat"}), _L.PATTERN),
    "child": PathRule(MemoryKind.CHILD_FACT, frozenset({"pat", "lrn"}), _L.PATTERN),
    "caregivers": PathRule(MemoryKind.CAREGIVER, frozenset({"pat", "lrn"}), _L.PATTERN),
    "investigations": PathRule(MemoryKind.INVESTIGATION, frozenset({"hyp"}), _L.HYPOTHESIS),
    "decisions": PathRule(MemoryKind.DECISION, frozenset({"exp"}), _L.HYPOTHESIS),
}
assert {r.kind for r in PATH_RULES.values()} == set(DIRECTORY_KIND.values())


def rule_for(path: str) -> PathRule:
    return PATH_RULES[directory_of(path)]


def required_level_for(path: str, operation: MemoryOperation) -> EpistemicLevel:
    if operation is MemoryOperation.DEPRECATE:
        return _L.RAW_EVIDENCE
    return rule_for(path).min_level
