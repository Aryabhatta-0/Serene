"""Full-context unified diffs for memory patches.

A memory patch diff is a single hunk that covers the whole file (every
unchanged line is context). That keeps it a standard, reviewable unified diff
while making both the pre-image and the post-image reconstructible from the
diff alone, so the kernel can review exactly what would be written without
reading the repository, and the committer can refuse a patch whose pre-image
no longer matches the file.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Final

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
