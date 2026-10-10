"""Deterministic causal / epistemic engine (no external causal libraries, issue #27).

Candidate / supported / refuted relationship state with support (observational
vs experimental), counterevidence, confounders, experiments, scope, epistemic
level, validity and provenance - derived from the ledger, never self-declared,
and never scored numerically.
"""

from serene.causal.model import (
    CausalEdge,
    CausalTwin,
    RelationshipStatus,
    SupportItem,
    SupportKind,
    build_causal_twin,
    build_edge,
)

__all__ = [
    "CausalEdge",
    "CausalTwin",
    "RelationshipStatus",
    "SupportItem",
    "SupportKind",
    "build_causal_twin",
    "build_edge",
]
