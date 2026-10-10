"""Bootstrap smoke tests: prove the scaffold is importable and wired.

These are deliberately shallow. Real deterministic policy/epistemic tests live
under tests/ and eval/ as the corresponding issues land.
"""

import morrow


def test_version_is_defined():
    assert morrow.__version__


def test_all_subpackages_import():
    import morrow.causal  # noqa: F401
    import morrow.domain  # noqa: F401
    import morrow.lineage  # noqa: F401
    import morrow.memory  # noqa: F401
    import morrow.policies  # noqa: F401
    import morrow.projections  # noqa: F401
    import morrow.tools  # noqa: F401


def test_pydantic_v2_is_the_pinned_major():
    import pydantic

    assert pydantic.VERSION.startswith("2.")
