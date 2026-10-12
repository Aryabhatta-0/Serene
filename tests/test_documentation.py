"""Documentation verification is offline in CI; live reference checks are opt-in."""

from pathlib import Path

import pytest

from scripts import docs_check


def test_core_documentation_links_and_paths_resolve() -> None:
    assert docs_check.check_links(docs_check.CORE_DOCS) == []


def test_missing_document_is_reported(tmp_path: Path) -> None:
    assert docs_check.check_links((tmp_path / "absent.md",))


def test_checker_rejects_missing_paths_and_headings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(docs_check, "ROOT", tmp_path)
    source = tmp_path / "source.md"
    target = tmp_path / "target.md"
    target.write_text("# Real heading\n", encoding="utf-8")
    source.write_text(
        "[missing](absent.json)\n[stale heading](target.md#gone)\n"
        "`tests/absent.py`\n[outside](../outside.md)\n",
        encoding="utf-8",
    )
    failures = docs_check.check_links((source,))
    assert len(failures) == 4
    assert any("missing heading" in f for f in failures)
    assert any("outside repository" in f for f in failures)


def test_valid_anchors_encoded_paths_and_fenced_examples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(docs_check, "ROOT", tmp_path)
    source = tmp_path / "source.md"
    target = tmp_path / "with space.md"
    target.write_text("# Same heading\n# Same heading\n", encoding="utf-8")
    source.write_text(
        "# Local heading\n[local](#local-heading)\n"
        "[target](with%20space.md#same-heading-1)\n"
        "```sh\n[example](generated.json)\n```\n",
        encoding="utf-8",
    )
    assert docs_check.check_links((source,)) == []


def test_issue_ranges_and_url_numbers_are_validated(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text(
        "#17\u2013#19, #52; [issue](https://github.com/Sathvikar01/morrow/issues/60)\n"
        "[heading](privacy.md#404-unrelated)\n",
        encoding="utf-8",
    )
    assert docs_check.issue_numbers((source,)) == {17, 18, 19, 52, 60}
    assert docs_check.validate_github_refs(
        (source,), {17: "issues", 18: "issues", 19: "issues", 52: "issues"}
    ) == ["missing GitHub reference #60"]


def test_pr_number_cannot_validate_wrong_issue_url(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text(
        "[wrong](https://github.com/Sathvikar01/morrow/issues/80)\n", encoding="utf-8"
    )
    failures = docs_check.validate_github_refs((source,), {80: "pull"})
    assert len(failures) == 1
    assert "wrong GitHub URL kind" in failures[0]


def test_blob_reference_stops_at_markdown_boundary() -> None:
    text = "[source](https://github.com/Sathvikar01/morrow/blob/abcdef/docs/source.md). More\n"
    assert docs_check.GITHUB_BLOB.findall(text) == [("abcdef", "docs/source.md")]
