"""The Domain Kernel must not depend on Hermes or any adapter (issue #2)."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KERNEL_PACKAGES = (
    "domain",
    "lineage",
    "projections",
    "policies",
    "ports",
    "ledger",
    "observability",
)
FORBIDDEN_IN_KERNEL = (
    "hermes",
    "hermes_agent",
    "serene.adapters",
    "serene.testing",
    "psycopg",
    "neatlogs",
    "inspect_ai",
    "openai",
    "anthropic",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


@pytest.mark.parametrize("package", KERNEL_PACKAGES)
def test_kernel_package_has_no_forbidden_imports(package: str) -> None:
    offenders: list[str] = []
    for path in (ROOT / "serene" / package).rglob("*.py"):
        for module in _imports(path):
            if any(module == f or module.startswith(f + ".") for f in FORBIDDEN_IN_KERNEL):
                offenders.append(f"{path.relative_to(ROOT)} imports {module}")
    assert offenders == []


def test_only_the_hermes_adapter_may_mention_hermes_imports() -> None:
    for path in (ROOT / "serene").rglob("*.py"):
        if "adapters" in path.parts and "hermes" in path.parts:
            continue
        assert not any(m.split(".")[0] in {"hermes", "hermes_agent"} for m in _imports(path)), path


def test_importing_the_kernel_loads_no_runtime_or_adapter_modules() -> None:
    code = (
        "import sys\n"
        "import serene.domain, serene.lineage, serene.projections, serene.policies.admission\n"
        "import serene.ports, serene.ledger, serene.observability\n"
        "bad = sorted(m for m in sys.modules if m.split('.')[0] in "
        "{'hermes', 'hermes_agent', 'psycopg', 'neatlogs', 'inspect_ai'} "
        "or m.startswith('serene.adapters'))\n"
        "print(','.join(bad))\n"
    )
    result = subprocess.run(  # noqa: S603 - fixed interpreter and code
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
    )
    assert result.stdout.strip() == ""


def test_hermes_adapter_fails_closed_until_implemented() -> None:
    from serene.adapters.hermes import HermesAgentRuntime, HermesNotConfigured
    from serene.domain.base import new_id
    from serene.ports.agent_runtime import AgentRuntime, AgentTask

    runtime = HermesAgentRuntime()
    assert isinstance(runtime, AgentRuntime)
    task = AgentTask(
        task_id="t1", child_id=new_id("chd"), goal="g", max_steps=1, max_cost_micro_usd=0
    )
    with pytest.raises(HermesNotConfigured):
        runtime.run(task)
