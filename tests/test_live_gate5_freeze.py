"""A new experiment identity must preserve the old contracts and evidence bytes."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from eval.runners import live_gate4_experiment as v4
from eval.runners import live_gate5_experiment as v5
from tests.frozen_contract import frozen_contract_root  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.usefixtures("frozen_contract_root")


def test_v5_decision_and_completed_pair_semantics_are_exactly_v4() -> None:
    old = ast.parse(Path(v4.__file__).read_text("utf-8"))
    new = ast.parse(Path(v5.__file__).read_text("utf-8"))
    for name in ("decide", "validate_row", "number", "count", "run_frozen_pair"):
        a = next(n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == name)
        b = next(n for n in new.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assert ast.dump(a) == ast.dump(b)
    assert v4.RULE == v5.RULE and v4.SAMPLING == v5.SAMPLING
    assert v4.PRODUCT_SHAS == v5.PRODUCT_SHAS


def test_v3_v4_frozen_bytes_remain_valid_and_v5_catalog_is_identical() -> None:
    v4.check_experiment(v4.load(v4.MANIFEST))
    from eval.runners import shared_prefix_experiment as v3

    v3.check_experiment(v3.load(v3.MANIFEST))
    old = v4.load(v4.DEFAULT_CATALOG)
    new = v5.load(v5.DEFAULT_CATALOG)
    new["protocol_version"] = old["protocol_version"]
    assert new == old
    for suffix in ("config", "installation", "internal-bridges"):
        a = v4.ROOT / f"eval/fixtures/hermes-v4-{suffix}.json"
        b = v5.ROOT / f"eval/fixtures/hermes-v5-{suffix}.json"
        assert a.read_bytes() == b.read_bytes()


def test_transport_uses_permit_and_never_caller_selected_hermes_session() -> None:
    source = (v5.ROOT / "eval/runners/live_gate5_transport.py").read_text("utf-8")
    assert "X-Hermes-Session-Id" not in source
    assert "X-Hermes-Session-Key" not in source
    assert "sdk_receipt(body, permit)" in source
    tree = ast.parse(source)
    method = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "single_attempt"
    )
    calls = [n for n in ast.walk(method) if isinstance(n, ast.Call)]
    permit = next(
        n.lineno for n in calls if isinstance(n.func, ast.Name) and n.func.id == "new_permit"
    )
    attest = next(
        n.lineno for n in calls if isinstance(n.func, ast.Attribute) and n.func.attr == "attest"
    )
    post = next(
        n.lineno for n in calls if isinstance(n.func, ast.Attribute) and n.func.attr == "Request"
    )
    assert permit < attest < post
