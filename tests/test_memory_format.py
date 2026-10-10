"""Memory document format and full-context diffs (issue #28)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from serene.domain.entities import LearningStatus
from serene.domain.values import EpistemicLevel
from serene.memory.diff import DiffFormatError, full_diff, parse_full_diff
from serene.memory.document import (
    MemoryDoc,
    MemoryFormatError,
    MemoryFrontMatter,
    MemoryKind,
    parse,
    render,
)

EVD = "evd_" + "a" * 32
LRN = "lrn_" + "b" * 32


def _doc(
    status: LearningStatus = LearningStatus.ACTIVE, body: str = "Heads-up helps."
) -> MemoryDoc:
    return MemoryDoc(
        front=MemoryFrontMatter(
            kind=MemoryKind.LEARNING,
            subject=LRN,
            level=EpistemicLevel.CONTEXTUAL_LEARNING,
            status=status,
            scope=("daycare_pickup", "weekday_evening"),
            valid_from=datetime(2026, 9, 1, tzinfo=UTC),
            review_after=datetime(2026, 10, 31, tzinfo=UTC),
            sources=(EVD,),
        ),
        title="A heads-up helps pickups",
        body=body,
    )


def test_render_parse_round_trip_is_byte_identical() -> None:
    text = render(_doc())
    assert parse(text) == _doc()
    assert render(parse(text)) == text
    assert text.startswith("---\nserene_memory: 1\nkind: learning\n")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t: t.replace("kind: learning\nsubject", "subject"),  # missing key
        lambda t: t.replace("serene_memory: 1", "serene_memory: 2"),  # unknown version
        lambda t: t.replace("status: ACTIVE", "status: TRUSTED"),  # unknown status
        lambda t: t.replace("\n", "\r\n"),  # CRLF
        lambda t: t.replace("counterevidence:", "confidence: 0.97\ncounterevidence:"),  # extra key
        lambda t: t.replace("sources: " + EVD, "sources:"),  # no provenance
        lambda t: t.replace("# A heads-up", "#A heads-up"),  # malformed title
    ],
)
def test_parse_is_strict(mutate: object) -> None:
    with pytest.raises(MemoryFormatError):
        parse(mutate(render(_doc())))  # type: ignore[operator]


def test_full_diff_round_trips_create_and_update() -> None:
    old, new = render(_doc()), render(_doc(LearningStatus.STALE, "Heads-up helps.\nNow stale."))
    created = parse_full_diff(full_diff("learnings/x.md", None, old))
    assert (created.path, created.pre, created.post) == ("learnings/x.md", None, old)
    updated = parse_full_diff(full_diff("learnings/x.md", old, new))
    assert (updated.pre, updated.post) == (old, new)
    assert full_diff("learnings/x.md", old, old) == ""


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.replace("+++ b/learnings/x.md", "+++ b/learnings/y.md"),
        lambda d: d + "@@ -1,1 +1,1 @@\n-a\n+b\n",
        lambda d: d.replace("@@ -1,", "@@ -3,"),
        lambda d: d[:-30],
    ],
)
def test_diff_parser_rejects_anything_but_one_full_hunk(mutate: object) -> None:
    old, new = render(_doc()), render(_doc(body="Changed."))
    with pytest.raises(DiffFormatError):
        parse_full_diff(mutate(full_diff("learnings/x.md", old, new)))  # type: ignore[operator]


_LINE = st.text(alphabet="abc -+@#\\", max_size=12)


@settings(max_examples=150, deadline=None)
@given(old=st.lists(_LINE, max_size=12), new=st.lists(_LINE, min_size=1, max_size=12))
def test_any_change_is_reconstructible_from_the_diff(old: list[str], new: list[str]) -> None:
    before = "".join(line + "\n" for line in old) if old else None
    after = "".join(line + "\n" for line in new)
    diff = full_diff("patterns/p.md", before, after)
    if before == after:
        assert diff == ""
        return
    parsed = parse_full_diff(diff)
    assert parsed.pre == before and parsed.post == after
