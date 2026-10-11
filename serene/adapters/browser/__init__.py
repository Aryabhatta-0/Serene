"""Bounded web-evidence acquisition (issue #15) and the verifier's independent fetcher.

The browser acquires unverified evidence; it never verifies and never calls the
verifier. Verification lives in serene.evidence.verifier.
"""

from serene.adapters.browser.fetch import SafeHttpsFetcher, visible_text
from serene.adapters.browser.hermes_browser import READ_ONLY_TOOLS, HermesBrowser

__all__ = ["READ_ONLY_TOOLS", "HermesBrowser", "SafeHttpsFetcher", "visible_text"]
