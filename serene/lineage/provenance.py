"""Provenance validation and lineage reconstruction (issue #7).

Known IDs are necessary but not sufficient: an entity may only cite raw
evidence that is actually reachable through its own parents, so a proposal
cannot launder support by citing unrelated, verified evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from serene.domain.base import id_prefix
from serene.domain.values import EpistemicLevel, VerificationStatus


class _Record(Protocol):
    entity: Any
    level: EpistemicLevel | None
    verification_status: VerificationStatus


class EntityIndex(Protocol):
    entities: Any  # Mapping[str, _Record]


# Typed reference fields that must also appear in provenance.derived_from.
_TYPED_PARENT_FIELDS = (
    "evidence_ids",
    "observation_ids",
    "pattern_ids",
    "experiment_ids",
    "outcome_ids",
)


def raw_sources_of(entity_id: str, index: EntityIndex) -> frozenset[str]:
    """Raw evidence ids an existing entity rests on."""
    record = index.entities.get(entity_id)
    if record is None:
        return frozenset()
    if id_prefix(entity_id) == "evd":
        return frozenset({entity_id})
    return frozenset(record.entity.provenance.source_ids)


def provenance_violations(entity: Any, index: EntityIndex) -> list[str]:
    """Deterministic lineage checks for a candidate entity. Empty list == valid."""
    reasons: list[str] = []
    prov = entity.provenance
    derived_from: tuple[str, ...] = prov.derived_from
    level = type(entity).level

    if level is not None and level > EpistemicLevel.RAW_EVIDENCE:
        if not derived_from:
            reasons.append("PROVENANCE_MISSING_DERIVED_FROM")
        if not prov.source_ids:
            reasons.append("PROVENANCE_MISSING_SOURCES")

    for parent in derived_from:
        if parent not in index.entities:
            reasons.append(f"UNKNOWN_PARENT:{parent}")

    reachable: set[str] = set()
    for parent in derived_from:
        reachable |= raw_sources_of(parent, index)

    for source_id in prov.source_ids:
        if id_prefix(source_id) != "evd":
            reasons.append(f"SOURCE_NOT_EVIDENCE:{source_id}")
            continue
        status = (
            index.entities[source_id].verification_status if source_id in index.entities else None
        )
        if status is None:
            reasons.append(f"UNKNOWN_SOURCE:{source_id}")
        elif status is VerificationStatus.REJECTED:
            reasons.append(f"REJECTED_SOURCE:{source_id}")
        elif status is not VerificationStatus.VERIFIED:
            reasons.append(f"UNVERIFIED_SOURCE:{source_id}")
        if derived_from and source_id not in reachable:
            reasons.append(f"SOURCE_NOT_IN_LINEAGE:{source_id}")

    declared = set(derived_from)
    for field_name in _TYPED_PARENT_FIELDS:
        for ref in getattr(entity, field_name, ()) or ():
            if ref not in declared:
                reasons.append(f"TYPED_REF_NOT_IN_LINEAGE:{ref}")

    if prov.supersedes is not None and prov.supersedes not in index.entities:
        reasons.append(f"UNKNOWN_SUPERSEDED:{prov.supersedes}")
    return reasons


@dataclass(frozen=True, slots=True)
class LineageNode:
    entity_id: str
    level: EpistemicLevel | None
    verification_status: VerificationStatus
    parents: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LineageTrace:
    root: str
    nodes: tuple[LineageNode, ...]
    raw_evidence: tuple[str, ...]
    missing: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.missing and bool(self.raw_evidence)


def trace_lineage(entity_id: str, index: EntityIndex) -> LineageTrace:
    """Reconstruct the full chain from any entity down to raw evidence."""
    nodes: dict[str, LineageNode] = {}
    missing: set[str] = set()
    stack = [entity_id]
    while stack:
        current = stack.pop()
        if current in nodes or current in missing:
            continue
        record = index.entities.get(current)
        if record is None:
            missing.add(current)
            continue
        parents = tuple(record.entity.provenance.derived_from)
        nodes[current] = LineageNode(
            entity_id=current,
            level=record.level,
            verification_status=record.verification_status,
            parents=parents,
        )
        stack.extend(parents)
    raw = sorted(n for n in nodes if id_prefix(n) == "evd")
    return LineageTrace(
        root=entity_id,
        nodes=tuple(nodes[k] for k in sorted(nodes)),
        raw_evidence=tuple(raw),
        missing=tuple(sorted(missing)),
    )
