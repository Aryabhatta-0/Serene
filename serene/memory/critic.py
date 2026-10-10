"""Dream Critic, provenance verifier and memory Promotion Gate (issues #29, #31, #32).

The review is deterministic authority, so it lives in the policy layer
(`serene.policies.memory_review`), which the ledger's admission imports
directly. This module re-exports it for the memory feature layer (committer,
Dream); policy code must never import from `serene.memory`.
"""

from __future__ import annotations

from serene.policies.memory_review import (
    CRITIC_VERSION,
    MemoryReview,
    check_document,
    check_memory_authority,
    expected_front,
    review_facts_digest,
    review_patch,
    review_payload,
    search_contradictions,
    subject_counterevidence,
    subject_hypothesis,
    subject_level,
    verify_patch_lineage,
)

__all__ = [
    "CRITIC_VERSION",
    "MemoryReview",
    "check_document",
    "check_memory_authority",
    "expected_front",
    "review_facts_digest",
    "review_patch",
    "review_payload",
    "search_contradictions",
    "subject_counterevidence",
    "subject_hypothesis",
    "subject_level",
    "verify_patch_lineage",
]
