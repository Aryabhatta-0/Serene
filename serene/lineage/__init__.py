"""Evidence / provenance lineage and the tamper-evident hash chain.

Every derived object answers "why do you believe this?" via derived_from,
source_ids, creator/time/method/model, verification status and supersession.
"""

from serene.lineage.chain import ChainVerification, LedgerIntegrityError, verify_hash_chain
from serene.lineage.hashing import compute_event_hash, compute_payload_hash, seal_event
from serene.lineage.provenance import (
    LineageTrace,
    provenance_violations,
    raw_sources_of,
    trace_lineage,
)

__all__ = [
    "ChainVerification",
    "LedgerIntegrityError",
    "LineageTrace",
    "compute_event_hash",
    "compute_payload_hash",
    "provenance_violations",
    "raw_sources_of",
    "seal_event",
    "trace_lineage",
    "verify_hash_chain",
]
