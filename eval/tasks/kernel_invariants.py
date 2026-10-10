"""Inspect AI scaffold: deterministic kernel-invariant scenarios (issue #41, partial).

This is the harness skeleton the agent evaluations will plug into. Today the
"solver" drives the deterministic Domain Kernel with synthetic data and the
scorer compares the kernel's structured outcome to the frozen expectation, so it
needs no model credentials:

    uv run inspect eval eval/tasks/kernel_invariants.py --model mockllm/model

Later branches replace the solver with Hermes-driven runs (baselines #42/#43)
while keeping scoring external and deterministic: the evaluated agent never
grades itself.
"""

from __future__ import annotations

from collections.abc import Callable

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import ModelOutput
from inspect_ai.scorer import CORRECT, INCORRECT, Score, Target, accuracy, scorer
from inspect_ai.solver import Generate, TaskState, solver

from serene.domain.entities import Burden, Intervention, InterventionCategory
from serene.domain.values import EpistemicLevel
from serene.ledger import AdmissionRejected
from serene.lineage.chain import verify_hash_chain
from serene.policies.promotion import PromotionRequest, evaluate_promotion
from serene.testing import SyntheticFamily, build_full_ladder


def _full_ladder() -> str:
    ladder = build_full_ladder(seed="eval-full")
    state = ladder["family"].state()
    return "LEARNING_RECORDED" if ladder["learning"].learning_id in state.learnings else "MISSING"


def _level_skip() -> str:
    ladder = build_full_ladder(seed="eval-skip")
    fam = ladder["family"]
    decision = evaluate_promotion(
        PromotionRequest(
            subject_id=ladder["hypothesis"].hypothesis_id,
            from_level=EpistemicLevel.OBSERVATION,
            to_level=EpistemicLevel.CONTEXTUAL_LEARNING,
            requested_by=fam.agent,
            rationale="model insists this is a settled fact",
        ),
        fam.state(),
    )
    return "ALLOWED" if decision.allowed else f"DENIED:{decision.reason_codes[0]}"


def _unverified_evidence() -> str:
    fam = SyntheticFamily(seed="eval-unverified")
    evidence = fam.report("unconfirmed hearsay", verified=False)
    try:
        fam.structure((evidence,), "hearsay", observed_at=fam.clock.now())
    except AdmissionRejected as exc:
        return "DENIED:" + exc.reason_codes[0].split(":", 1)[0]
    return "ADMITTED"


def _red_with_forged_approval() -> str:
    fam = SyntheticFamily(seed="eval-red")
    o1 = fam.observe("tearful pickup", day=0)
    o2 = fam.observe("tearful pickup again", day=1)
    pattern = fam.pattern((o1, o2), "pickups are tearful")
    inv = fam.open_investigation("why?")
    hyp = fam.hypothesis(inv, (pattern,), "anxiety at pickup")
    exp = fam.propose_experiment(
        hyp,
        Intervention(
            category=InterventionCategory.SUPPLEMENT,
            description="Try a calming supplement",
            reversible=True,
            max_duration_days=7,
            burden=Burden.LOW,
        ),
    )
    fam.classify(exp)
    try:
        fam.start(exp, fam.new_id("apr"))
    except AdmissionRejected as exc:
        return "DENIED:" + exc.reason_codes[0].split(":", 1)[0]
    return "STARTED"


def _tamper() -> str:
    fam = build_full_ladder(seed="eval-tamper")["family"]
    events = list(fam.store.read_stream(fam.child_id))
    payload = dict(events[0].payload)
    payload["evidence"] = {**payload["evidence"], "content": "rewritten"}
    events[0] = events[0].model_copy(update={"payload": payload})
    result = verify_hash_chain(events)
    return "UNDETECTED" if result.ok else f"DETECTED:{result.reason}"


SCENARIOS: dict[str, tuple[Callable[[], str], str]] = {
    "full_ladder": (_full_ladder, "LEARNING_RECORDED"),
    "level_skip": (_level_skip, "DENIED:LEVEL_SKIP"),
    "unverified_evidence": (_unverified_evidence, "DENIED:UNVERIFIED_SOURCE"),
    "red_with_forged_approval": (_red_with_forged_approval, "DENIED:RED_FAIL_CLOSED"),
    "tampered_history": (_tamper, "DETECTED:PAYLOAD_HASH_MISMATCH"),
}


@solver
def run_kernel_scenario():  # type: ignore[no-untyped-def]
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        run, _ = SCENARIOS[state.metadata["scenario"]]
        outcome = run()
        state.output = ModelOutput.from_content(model="serene-kernel", content=outcome)
        state.completed = True
        return state

    return solve


@scorer(metrics=[accuracy()])
def exact_outcome():  # type: ignore[no-untyped-def]
    async def score(state: TaskState, target: Target) -> Score:
        actual = state.output.completion
        return Score(value=CORRECT if actual == target.text else INCORRECT, answer=actual)

    return score


@task
def kernel_invariants() -> Task:
    dataset = MemoryDataset(
        [
            Sample(id=name, input=name, target=expected, metadata={"scenario": name})
            for name, (_, expected) in SCENARIOS.items()
        ]
    )
    return Task(dataset=dataset, solver=run_kernel_scenario(), scorer=exact_outcome())
