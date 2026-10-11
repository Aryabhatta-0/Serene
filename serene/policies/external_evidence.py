"""Ledger-side recheck of external-evidence verification (issue #16, branch A).

The `EvidenceVerifier` (serene.evidence) does the full content checks. Admission
independently recomputes the decidable parts from ledger facts alone, so even a
VERIFIER-attributed EVIDENCE_VERIFIED cannot mark external evidence valid when
its digest is wrong, its source is off the request's allowlist, or a required
check was skipped.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Final
from urllib.parse import urlsplit

from serene.domain.canonical import sha256_hex
from serene.domain.entities import Evidence, EvidenceKind
from serene.domain.events import VerificationCheck
from serene.domain.values import SourceKind
from serene.projections.state import KernelState

_C = VerificationCheck
REQUIRED_EXTERNAL_CHECKS: Final = frozenset(
    {
        _C.SOURCE_ALLOWED,
        _C.SUBJECT_MATCHES,
        _C.EFFECTIVE_DATE_VALID,
        _C.REQUESTED_FIELDS_PRESENT,
        _C.DIGEST_MATCHES,
        _C.PROVENANCE_VALID,
    }
)
EXTERNAL_KINDS: Final = frozenset({EvidenceKind.DOCUMENT, EvidenceKind.BROWSER_CAPTURE})
EXTERNAL_SOURCES: Final = frozenset({SourceKind.BROWSER, SourceKind.EXTERNAL_DOCUMENT})


# One DNS label: 1-63 of [a-z0-9-], no leading/trailing hyphen.
_LABEL: Final = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


def _dns_name(host: str) -> str | None:
    """`host` as a lower-cased DNS name, or None for IP literals and malformed names."""
    name = host.lower().removesuffix(".")
    if not name or len(name) > 253 or not all(_LABEL.match(label) for label in name.split(".")):
        return None
    try:
        ipaddress.ip_address(name)
    except ValueError:
        return name
    return None  # allowlists name domains; an IP literal never matches one


def host_of(uri: str | None) -> str | None:
    """Lower-cased host of an https URI; None for anything else (fails closed).

    Never raises: a malformed port, host or authority is a deterministic refusal.
    """
    if uri is None:
        return None
    try:
        parts = urlsplit(uri)
        port = parts.port  # raises ValueError on a textual or out-of-range port
        host = parts.hostname
    except ValueError:
        return None
    if parts.scheme != "https" or not host or parts.username is not None:
        return None
    if parts.password is not None or "@" in parts.netloc or port not in (None, 443):
        return None
    return _dns_name(host)


def domain_allowed(host: str | None, allowed: tuple[str, ...]) -> bool:
    """Exact host or a subdomain of an allowed domain. Empty allowlist allows nothing."""
    if host is None:
        return False
    return any(host == d or host.endswith("." + d) for d in allowed)


def digest_consistent(evidence: Evidence) -> bool:
    computed = sha256_hex(evidence.content.encode("utf-8"))
    return computed == evidence.content_digest == evidence.source.content_digest


def external_verification_violations(
    evidence: Evidence, checks_passed: tuple[VerificationCheck, ...], state: KernelState
) -> list[str]:
    reasons = [
        f"MISSING_CHECK:{c.value}" for c in sorted(REQUIRED_EXTERNAL_CHECKS - set(checks_passed))
    ]
    if evidence.source.kind not in EXTERNAL_SOURCES:
        reasons.append("SOURCE_NOT_EXTERNAL")
    if not digest_consistent(evidence):
        reasons.append("CONTENT_DIGEST_MISMATCH")
    request_id = state.evidence_request_of.get(evidence.evidence_id)
    if request_id is None:
        reasons.append("NO_EVIDENCE_REQUEST")
    else:
        request = state.evidence_requests[request_id].request
        if not domain_allowed(host_of(evidence.source.uri), request.allowed_domains):
            reasons.append("SOURCE_DOMAIN_NOT_ALLOWED")
    return reasons
