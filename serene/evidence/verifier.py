"""Independent, deterministic external-evidence verifier (issue #16).

Separate from the browser and from the model: it sees only the ledger's raw
evidence and the ledger's EVIDENCE_REQUESTED bounds, and optionally re-fetches
the source page itself. It never trusts what the browser *said*; every check
runs over digest-protected capture text (serene.evidence.capture).

    SOURCE_ALLOWED            external kind/source; https host on the request allowlist
    DIGEST_MATCHES            sha256(content) == evidence digest == source digest
    SUBJECT_MATCHES           capture subject == requested subject, and the subject
                              is named in the excerpt
    EFFECTIVE_DATE_VALID      not in the future; within the request's max age
    REQUESTED_FIELDS_PRESENT  every requested field has a value found in the excerpt
    PROVENANCE_VALID          browser-acquired raw evidence, capture url == source uri,
                              retrieved no later than now, and (by default) the
                              excerpt is present in an independent re-fetch of the url

All six pass -> VERIFIED with the six checks. Anything else -> REJECTED with
reason codes. Admission then re-checks the decidable parts again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

from serene.domain.entities import Evidence
from serene.domain.events import VerificationCheck
from serene.domain.values import DerivationMethod
from serene.evidence.capture import Capture, CaptureError, contains, parse_capture
from serene.policies.external_evidence import (
    EXTERNAL_KINDS,
    EXTERNAL_SOURCES,
    REQUIRED_EXTERNAL_CHECKS,
    digest_consistent,
    domain_allowed,
    host_of,
)
from serene.ports.clock import Clock
from serene.ports.evidence import EvidenceBrowseRequest, VerificationVerdict

VERIFIER_VERSION: Final = "serene-evidence-verifier/1"
_C = VerificationCheck
_SUBJECT_TOKEN: Final = re.compile(r"[a-z0-9]{3,}")


@dataclass(frozen=True, slots=True)
class FetchedPage:
    url: str
    text: str


@runtime_checkable
class PageFetcher(Protocol):
    """Independent read of a public page (serene.adapters.browser.fetch). None == unreachable."""

    def fetch(self, url: str, allowed_domains: tuple[str, ...]) -> FetchedPage | None: ...


class IndependentEvidenceVerifier:
    def __init__(
        self,
        clock: Clock,
        *,
        fetcher: PageFetcher | None = None,
        require_refetch: bool = True,
    ) -> None:
        self._clock = clock
        self._fetcher = fetcher
        self._require_refetch = require_refetch

    def verify(self, evidence: Evidence, request: EvidenceBrowseRequest) -> VerificationVerdict:
        passed: set[VerificationCheck] = set()
        reasons: list[str] = []

        source_ok = (
            evidence.kind in EXTERNAL_KINDS
            and evidence.source.kind in EXTERNAL_SOURCES
            and domain_allowed(host_of(evidence.source.uri), request.allowed_domains)
        )
        _record(source_ok, _C.SOURCE_ALLOWED, "SOURCE_NOT_ALLOWED", passed, reasons)
        digest_ok = digest_consistent(evidence)
        _record(digest_ok, _C.DIGEST_MATCHES, "CONTENT_DIGEST_MISMATCH", passed, reasons)

        try:
            capture: Capture | None = parse_capture(evidence.content)
        except CaptureError as exc:
            capture = None
            reasons.append(str(exc))

        if capture is not None:
            self._content_checks(capture, request, passed, reasons)
            if source_ok and digest_ok:
                self._provenance(evidence, capture, request, passed, reasons)
            else:
                reasons.append("PROVENANCE_NOT_CHECKED")

        if passed == REQUIRED_EXTERNAL_CHECKS and not reasons:
            return VerificationVerdict(
                evidence_id=evidence.evidence_id,
                verdict="VERIFIED",
                checks_passed=tuple(sorted(passed)),
                verifier_version=VERIFIER_VERSION,
            )
        return VerificationVerdict(
            evidence_id=evidence.evidence_id,
            verdict="REJECTED",
            checks_passed=tuple(sorted(passed)),
            reason_codes=tuple(dict.fromkeys(reasons)) or ("VERIFICATION_INCOMPLETE",),
            verifier_version=VERIFIER_VERSION,
        )

    # ------------------------------------------------------------------ checks
    def _content_checks(
        self,
        capture: Capture,
        request: EvidenceBrowseRequest,
        passed: set[VerificationCheck],
        reasons: list[str],
    ) -> None:
        subject_ok = (
            request.subject is not None
            and capture.subject == request.subject
            and any(
                contains(capture.excerpt, token)
                for token in _SUBJECT_TOKEN.findall(request.subject)
            )
        )
        _record(subject_ok, _C.SUBJECT_MATCHES, "SUBJECT_MISMATCH", passed, reasons)

        today = self._clock.now().date()
        age = (today - capture.effective_date).days
        if age < 0:
            reasons.append("EFFECTIVE_DATE_IN_FUTURE")
        elif request.max_age_days is not None and age > request.max_age_days:
            reasons.append("EVIDENCE_STALE")
        else:
            passed.add(_C.EFFECTIVE_DATE_VALID)

        missing = [
            name
            for name in request.requested_fields
            if not (value := capture.field(name)) or not contains(capture.excerpt, value)
        ]
        for name in missing:
            reasons.append(f"REQUESTED_FIELD_UNSUPPORTED:{name}")
        if not missing:
            passed.add(_C.REQUESTED_FIELDS_PRESENT)

    def _provenance(
        self,
        evidence: Evidence,
        capture: Capture,
        request: EvidenceBrowseRequest,
        passed: set[VerificationCheck],
        reasons: list[str],
    ) -> None:
        local: list[str] = []
        if evidence.provenance.method is not DerivationMethod.BROWSER_ACQUISITION:
            local.append("NOT_BROWSER_ACQUIRED")
        if capture.url != evidence.source.uri:
            local.append("CAPTURE_URI_MISMATCH")
        retrieved = evidence.source.retrieved_at
        if retrieved is None or retrieved > self._clock.now():
            local.append("RETRIEVAL_TIME_INVALID")
        if not local:
            local += self._refetch(capture, request)
        reasons += local
        if not local:
            passed.add(_C.PROVENANCE_VALID)

    def _refetch(self, capture: Capture, request: EvidenceBrowseRequest) -> list[str]:
        if self._fetcher is None:
            return ["REFETCH_UNAVAILABLE"] if self._require_refetch else []
        try:
            page = self._fetcher.fetch(capture.url, request.allowed_domains)
        except Exception:  # an unreachable source can never verify
            page = None
        if page is None:
            return ["REFETCH_FAILED"]
        if page.url != capture.url:
            return ["REFETCH_REDIRECTED"]
        if not contains(page.text, capture.excerpt):
            return ["EXCERPT_NOT_ON_SOURCE"]
        return []


def _record(
    ok: bool,
    check: VerificationCheck,
    reason: str,
    passed: set[VerificationCheck],
    reasons: list[str],
) -> None:
    if ok:
        passed.add(check)
    else:
        reasons.append(reason)
