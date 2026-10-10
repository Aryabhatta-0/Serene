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


# ------------------------------------------------------------------ policy layer
# Deterministic authority (serene/policies/**) sits below the feature and runtime
# layers: the memory feature layer may call policy, never the reverse.
POLICY_FORBIDDEN = (
    "serene.memory",
    "serene.adapters",
    "serene.testing",
    "serene.ledger",
    "serene.experiments",
    "serene.causal",
    "serene.observability",
    "serene.ports.agent_runtime",
    "hermes",
    "hermes_agent",
    "openai",
    "anthropic",
    "google.genai",
    "google.generativeai",
    "mistralai",
    "cohere",
    "litellm",
    "ollama",
    "inspect_ai",
    "psycopg",
    "pgserver",
    "neatlogs",
)
POLICY_ALLOWED_SERENE = {"domain", "lineage", "policies", "ports", "projections"}


# `serene.ports/__init__` loads every port Protocol, including the agent-runtime
# contract; policy may not import it, but loading the pure contract is not a runtime.
PORT_CONTRACTS = ("serene.ports.agent_runtime",)


def _forbidden(module: str, allowed: tuple[str, ...] = ()) -> bool:
    banned = (f for f in POLICY_FORBIDDEN if f not in allowed)
    return any(module == f or module.startswith(f + ".") for f in banned)


def _qualified_imports(source: str, package: str) -> set[str]:
    """Absolute modules `source` imports, including `from pkg import sub` and relative forms."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = package.split(".")
            if node.level:
                base = base[: len(base) - node.level + 1]
                module = ".".join([*base, *([node.module] if node.module else [])])
            else:
                module = node.module or ""
            found.add(module)
            found.update(f"{module}.{alias.name}" for alias in node.names)
    return found


def test_policy_layer_imports_no_feature_adapter_runtime_or_model_modules() -> None:
    paths = sorted((ROOT / "serene" / "policies").rglob("*.py"))
    assert any(p.name == "admission.py" for p in paths)
    offenders = [
        f"{path.relative_to(ROOT)} imports {module}"
        for path in paths
        for module in sorted(
            _qualified_imports(path.read_text(encoding="utf-8"), "serene.policies")
        )
        if _forbidden(module)
    ]
    assert offenders == []


@pytest.mark.parametrize(
    "form",
    [
        "import serene.memory.critic",
        "from serene.memory import critic",
        "from serene import memory",
        "from ..memory.critic import review_patch",
        "from serene.adapters.git_memory import GitMemoryRepo",
        "import anthropic",
        "from hermes_agent import Agent",
    ],
)
def test_policy_boundary_detector_catches_every_import_form(form: str) -> None:
    assert any(_forbidden(m) for m in _qualified_imports(form, "serene.policies"))


def test_importing_every_policy_loads_only_kernel_modules() -> None:
    code = (
        "import importlib, pkgutil, sys\n"
        "import serene.policies\n"
        "for m in pkgutil.iter_modules(serene.policies.__path__):\n"
        "    importlib.import_module('serene.policies.' + m.name)\n"
        "print(' '.join(sorted(sys.modules)))\n"
    )
    result = subprocess.run(  # noqa: S603 - fixed interpreter and code
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
    )
    loaded = result.stdout.split()
    assert "serene.policies.admission" in loaded
    assert "serene.policies.memory_review" in loaded
    assert [m for m in loaded if _forbidden(m, PORT_CONTRACTS)] == []
    layers = {m.split(".")[1] for m in loaded if m.startswith("serene.")}
    assert layers <= POLICY_ALLOWED_SERENE, layers - POLICY_ALLOWED_SERENE


def test_memory_critic_is_the_policy_review_not_a_copy() -> None:
    from serene.memory import critic, diff, document, rules
    from serene.policies import memory_format, memory_review

    assert critic.review_patch is memory_review.review_patch
    assert critic.review_payload is memory_review.review_payload
    assert critic.expected_front is memory_review.expected_front
    assert critic.CRITIC_VERSION == memory_review.CRITIC_VERSION == "memory-critic/1"
    assert rules.PATH_RULES is memory_review.PATH_RULES
    assert document.parse is memory_format.parse
    assert document.render is memory_format.render
    assert diff.parse_full_diff is memory_format.parse_full_diff
