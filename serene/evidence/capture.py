"""Canonical text of a browser capture (issues #15, #16).

The browser stores what it saw as raw L0 evidence whose `content` is this exact
rendering (and whose digest covers it). The verifier parses the same text back,
so every check runs over digest-protected ledger content rather than over
whatever the model said in its reply. Parsing is strict and fails closed: any
deviation from the format makes the capture unverifiable.

    serene-capture/1
    url: https://example.org/policies/pickup
    subject: daycare_pickup
    effective_date: 2026-09-01
    field.pickup_window: 15:00-17:30
    excerpt:
    <verbatim page excerpt, may span lines>
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Final

CAPTURE_FORMAT: Final = "serene-capture/1"
_TAG: Final = re.compile(r"^[a-z0-9_\-]{1,64}$")
_URL: Final = re.compile(r"^https://[^\s]{1,2000}$")
_MAX_VALUE: Final = 500
_MAX_EXCERPT: Final = 2000


@dataclass(frozen=True, slots=True)
class Capture:
    url: str
    subject: str
    effective_date: date
    fields: tuple[tuple[str, str], ...]
    excerpt: str

    def field(self, name: str) -> str | None:
        return dict(self.fields).get(name)


class CaptureError(ValueError):
    """Machine-readable reason; never echoes page text."""


def _single_line(value: str) -> bool:
    return bool(value.strip()) and "\n" not in value and "\r" not in value


def render_capture(capture: Capture) -> str:
    """Render a capture; raises CaptureError when it cannot be represented faithfully."""
    if not _URL.match(capture.url):
        raise CaptureError("CAPTURE_URL_INVALID")
    if not _TAG.match(capture.subject):
        raise CaptureError("CAPTURE_SUBJECT_INVALID")
    if not capture.excerpt.strip() or len(capture.excerpt) > _MAX_EXCERPT:
        raise CaptureError("CAPTURE_EXCERPT_INVALID")
    names = [name for name, _ in capture.fields]
    if len(names) != len(set(names)):
        raise CaptureError("CAPTURE_FIELD_DUPLICATE")
    lines = [
        CAPTURE_FORMAT,
        f"url: {capture.url}",
        f"subject: {capture.subject}",
        f"effective_date: {capture.effective_date.isoformat()}",
    ]
    for name, value in sorted(capture.fields):
        if not _TAG.match(name):
            raise CaptureError("CAPTURE_FIELD_NAME_INVALID")
        if not _single_line(value) or len(value) > _MAX_VALUE:
            raise CaptureError("CAPTURE_FIELD_VALUE_INVALID")
        lines.append(f"field.{name}: {value}")
    lines.append("excerpt:")
    lines.append(capture.excerpt)
    return "\n".join(lines)


def parse_capture(content: str) -> Capture:
    """Inverse of `render_capture`; the round trip must reproduce `content` exactly."""
    head, sep, excerpt = content.partition("\nexcerpt:\n")
    if not sep:
        raise CaptureError("CAPTURE_NO_EXCERPT")
    lines = head.split("\n")
    if len(lines) < 4 or lines[0] != CAPTURE_FORMAT:
        raise CaptureError("CAPTURE_FORMAT_UNKNOWN")
    try:
        url = _value(lines[1], "url")
        subject = _value(lines[2], "subject")
        effective = date.fromisoformat(_value(lines[3], "effective_date"))
    except ValueError as exc:
        raise CaptureError("CAPTURE_HEADER_INVALID") from exc
    fields: list[tuple[str, str]] = []
    for line in lines[4:]:
        name, sep_, value = line.partition(": ")
        if not sep_ or not name.startswith("field."):
            raise CaptureError("CAPTURE_FIELD_INVALID")
        fields.append((name.removeprefix("field."), value))
    capture = Capture(url, subject, effective, tuple(fields), excerpt)
    if render_capture(capture) != content:
        raise CaptureError("CAPTURE_NOT_CANONICAL")
    return capture


def _value(line: str, key: str) -> str:
    prefix = f"{key}: "
    if not line.startswith(prefix):
        raise ValueError(key)
    return line.removeprefix(prefix)


def normalize_text(text: str) -> str:
    """Whitespace-collapsed, case-folded text for containment checks (no other rewriting)."""
    return " ".join(text.split()).casefold()


def contains(haystack: str, needle: str) -> bool:
    n = normalize_text(needle)
    return bool(n) and n in normalize_text(haystack)
