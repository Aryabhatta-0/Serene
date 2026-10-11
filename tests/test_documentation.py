"""Core documentation must retain resolvable implementation/evidence links."""

from scripts.docs_check import CORE_DOCS, check_links


def test_core_documentation_links_resolve() -> None:
    assert check_links(CORE_DOCS) == []
