"""The Markdown memory document format (memory_repo/SCHEMA.md).

A memory file is human-readable Markdown with a closed, fixed-order front
matter. Every authority-bearing field (subject, level, status, scope, validity,
sources, counterevidence) is filled in by deterministic code from the ledger -
never by the Dreamer or any model - and is re-checked by the Critic against the
ledger before a commit. Parsing is strict: unknown keys, reordering, duplicates
or malformed values are rejected.

This is also where the full-context unified diff grammar of a memory patch
lives. Both grammars are part of the authority contract: the ledger's admission
re-runs the memory review (`serene.policies.memory_review`) over a patch's raw
diff, so they sit in the policy layer and import nothing from `serene.memory`.
`serene.memory.document` and `serene.memory.diff` re-export them.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import Field, StringConstraints, ValidationError

from serene.domain.base import EntityId, KernelModel, ShortText, Tag, UtcDatetime
from serene.domain.canonical import format_timestamp
from serene.domain.entities import LearningStatus
from serene.domain.values import EpistemicLevel

MEMORY_FORMAT: Final = 1
FENCE: Final = "---"


class MemoryKind(StrEnum):
    LEARNING = "learning"
    ROUTINE = "routine"
    PATTERN = "pattern"
    CHILD_FACT = "child_fact"
    CAREGIVER = "caregiver"
    INVESTIGATION = "investigation"
    DECISION = "decision"


DIRECTORY_KIND: Final[dict[str, MemoryKind]] = {
    "learnings": MemoryKind.LEARNING,
    "routines": MemoryKind.ROUTINE,
    "patterns": MemoryKind.PATTERN,
    "child": MemoryKind.CHILD_FACT,
    "caregivers": MemoryKind.CAREGIVER,
    "investigations": MemoryKind.INVESTIGATION,
    "decisions": MemoryKind.DECISION,
}

BodyText = Annotated[str, StringConstraints(min_length=1, max_length=4000)]


class MemoryFormatError(ValueError):
    pass


class MemoryFrontMatter(KernelModel):
    serene_memory: Literal[1] = MEMORY_FORMAT
    kind: MemoryKind
    subject: EntityId
    level: EpistemicLevel | None
    # Withdrawn documents stay in the repo, marked with the ledger status that withdrew them.
    status: LearningStatus
    scope: tuple[Tag, ...] = Field(default=(), max_length=16)
    valid_from: UtcDatetime | None = None
    review_after: UtcDatetime | None = None
    sources: tuple[EntityId, ...] = Field(min_length=1, max_length=256)
    counterevidence: tuple[EntityId, ...] = Field(default=(), max_length=256)


class MemoryDoc(KernelModel):
    front: MemoryFrontMatter
    title: ShortText
    body: BodyText


_KEYS: Final = (
    "serene_memory",
    "kind",
    "subject",
    "level",
    "status",
    "scope",
    "valid_from",
    "review_after",
    "sources",
    "counterevidence",
)


def _list(values: tuple[str, ...]) -> str:
    return ", ".join(values)


def _time(value: datetime | None) -> str:
    return "" if value is None else format_timestamp(value)


def render(doc: MemoryDoc) -> str:
    """Canonical text of a document. Identical inputs render byte-identically."""
    f = doc.front
    values = {
        "serene_memory": str(f.serene_memory),
        "kind": f.kind.value,
        "subject": f.subject,
        "level": "" if f.level is None else f.level.name,
        "status": f.status.value,
        "scope": _list(f.scope),
        "valid_from": _time(f.valid_from),
        "review_after": _time(f.review_after),
        "sources": _list(f.sources),
        "counterevidence": _list(f.counterevidence),
    }
    lines = [FENCE, *(f"{k}: {values[k]}".rstrip() for k in _KEYS), FENCE, "", f"# {doc.title}", ""]
    body = [line.rstrip() for line in doc.body.strip().splitlines()]
    return "\n".join([*lines, *body]) + "\n"


def _split(value: str) -> tuple[str, ...]:
    return tuple(v.strip() for v in value.split(",")) if value.strip() else ()


def parse(text: str) -> MemoryDoc:
    lines = text.split("\n")
    if not text.endswith("\n") or "\r" in text:
        raise MemoryFormatError("documents use LF line endings and end with a newline")
    if len(lines) < len(_KEYS) + 6 or lines[0] != FENCE or lines[len(_KEYS) + 1] != FENCE:
        raise MemoryFormatError("missing or malformed front matter")
    raw: dict[str, str] = {}
    for key, line in zip(_KEYS, lines[1 : len(_KEYS) + 1], strict=True):
        name, sep, value = line.partition(":")
        if sep != ":" or name != key:
            raise MemoryFormatError(f"expected front-matter key {key!r}")
        raw[key] = value.strip()
    rest = lines[len(_KEYS) + 2 : -1]
    if len(rest) < 4 or rest[0] != "" or not rest[1].startswith("# ") or rest[2] != "":
        raise MemoryFormatError("expected a blank line, '# Title' and a blank line")
    try:
        front = MemoryFrontMatter.model_validate(
            {
                "serene_memory": int(raw["serene_memory"])
                if raw["serene_memory"].isdigit()
                else -1,
                "kind": MemoryKind(raw["kind"]),
                "subject": raw["subject"],
                "level": EpistemicLevel[raw["level"]] if raw["level"] else None,
                "status": LearningStatus(raw["status"]),
                "scope": _split(raw["scope"]),
                "valid_from": datetime.fromisoformat(raw["valid_from"])
                if raw["valid_from"]
                else None,
                "review_after": (
                    datetime.fromisoformat(raw["review_after"]) if raw["review_after"] else None
                ),
                "sources": _split(raw["sources"]),
                "counterevidence": _split(raw["counterevidence"]),
            },
            strict=False,
        )
        doc = MemoryDoc(front=front, title=rest[1][2:], body="\n".join(rest[3:]))
    except (ValidationError, ValueError, KeyError) as exc:
        raise MemoryFormatError(str(exc).splitlines()[0]) from exc
    if render(doc) != text:
        raise MemoryFormatError("document is not in canonical form")
    return doc


def directory_of(path: str) -> str:
    return path.split("/", 1)[0]


# ------------------------------------------------------------------ full-context diffs
# Full-context unified diffs for memory patches.
#
# A memory patch diff is a single hunk that covers the whole file (every
# unchanged line is context). That keeps it a standard, reviewable unified diff
# while making both the pre-image and the post-image reconstructible from the
# diff alone, so the kernel can review exactly what would be written without
# reading the repository, and the committer can refuse a patch whose pre-image
# no longer matches the file.

DEV_NULL: Final = "/dev/null"
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@$")


class DiffFormatError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ParsedDiff:
    path: str
    pre: str | None  # None: the file does not exist yet
    post: str


def _lines(text: str | None) -> list[str]:
    return [] if text is None else text.splitlines(keepends=True)


def full_diff(path: str, old: str | None, new: str) -> str:
    """Single-hunk unified diff from `old` (None = absent) to `new`. Empty if unchanged."""
    for text in (old, new):
        if text is not None and (not text.endswith("\n") or "\r" in text):
            raise DiffFormatError("memory files use LF and end with a newline")
    old_lines, new_lines = _lines(old), _lines(new)
    context = max(len(old_lines), len(new_lines))
    return "".join(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=DEV_NULL if old is None else f"a/{path}",
            tofile=f"b/{path}",
            n=context,
        )
    )


def _count(start: str, length: str | None) -> tuple[int, int]:
    return int(start), 1 if length is None else int(length)


def parse_full_diff(diff: str) -> ParsedDiff:
    lines = diff.split("\n")
    if not diff.endswith("\n") or len(lines) < 4:
        raise DiffFormatError("truncated diff")
    lines = lines[:-1]
    old_header, new_header, hunk = lines[0], lines[1], lines[2]
    if not new_header.startswith("+++ b/"):
        raise DiffFormatError("expected '+++ b/<path>'")
    path = new_header[len("+++ b/") :]
    if old_header not in (f"--- {DEV_NULL}", f"--- a/{path}"):
        raise DiffFormatError("expected '--- a/<path>' or '--- /dev/null' for the same path")
    match = _HUNK.match(hunk)
    if match is None:
        raise DiffFormatError("expected exactly one '@@ -a,b +c,d @@' hunk header")
    old_start, old_len = _count(match.group(1), match.group(2))
    new_start, new_len = _count(match.group(3), match.group(4))
    creating = old_header == f"--- {DEV_NULL}"
    if creating and (old_start, old_len) != (0, 0):
        raise DiffFormatError("a creation diff has an empty pre-image")
    if not creating and old_start != 1:
        raise DiffFormatError("the hunk must start at the first line")
    if new_start != 1 or new_len == 0:
        raise DiffFormatError("the post-image must be a non-empty file from line 1")

    pre: list[str] = []
    post: list[str] = []
    for line in lines[3:]:
        tag, content = line[:1], line[1:] + "\n"
        if tag == " ":
            pre.append(content)
            post.append(content)
        elif tag == "-":
            pre.append(content)
        elif tag == "+":
            post.append(content)
        else:
            raise DiffFormatError("only one hunk is allowed; no extra headers or markers")
    if len(pre) != old_len or len(post) != new_len:
        raise DiffFormatError("hunk line counts do not match the header")
    if pre == post:
        raise DiffFormatError("a patch must change the file")
    return ParsedDiff(path=path, pre=None if creating else "".join(pre), post="".join(post))
