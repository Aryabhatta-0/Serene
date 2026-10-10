"""Structured policy decisions shared by every deterministic policy."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """allow/deny with machine-readable reason codes. Deny is the default."""

    allowed: bool
    reason_codes: tuple[str, ...]
    policy_version: str

    @classmethod
    def from_reasons(cls, reasons: list[str], policy_version: str) -> PolicyDecision:
        unique = tuple(dict.fromkeys(reasons))
        if unique:
            return cls(allowed=False, reason_codes=unique, policy_version=policy_version)
        return cls(allowed=True, reason_codes=("ALLOWED",), policy_version=policy_version)
