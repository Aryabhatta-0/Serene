# Serene Evaluation

> **Status:** design specification. Implemented by issues #41–#51, #53, #58.

## 1. Goal

Prove that Serene's epistemic architecture beats ordinary assistant/memory
approaches — **using equivalent information, model and tool budgets** — and
guard against regressions deterministically.

## 2. Harness (#41)

Scaffold implemented: `eval/tasks/kernel_invariants.py` runs five frozen,
deterministic kernel scenarios (full ladder, level skip, unverified evidence, RED
with forged approval, tampered history) with an external exact-match scorer and
no model calls:

```bash
uv run inspect eval eval/tasks/kernel_invariants.py --model mockllm/model
```


Built on **Inspect AI** with frozen scenarios, deterministic execution and
structured output capture. The evaluated agent must **never grade itself**;
scoring is done by deterministic scorers over captured structure.

## 3. Baselines (matched budgets)

| Baseline | What it is | What it lacks |
| --- | --- | --- |
| A — Plain Hermes (#42) | Same model/task/information/basic tools | Serene epistemic architecture |
| B — Hermes + ordinary memory/RAG (#43) | Same history, browser, model, tool budget | Ladder, Promotion Gate, lineage governance, controlled investigation loop, Dream verification, experiment policy |

Serene is only interesting if it beats these at equal budget.

## 4. Scenarios (#44, #45)

Ten core scenarios: premature causation, hidden confounder, missing evidence,
conflicting caregivers, stale learning, wrong source, browser failure, unsafe
experiment, no-effect intervention, valid contextual learning.

Split: ~6–7 visible development scenarios and 2–3 **hidden holdouts**. Tuning
directly against the holdout is forbidden.

## 5. Scorers (deterministic, no LLM-as-judge)

| Scorer | Checks | Issue |
| --- | --- | --- |
| Authority & Safety | forbidden action, approval bypass, RED intervention, scope violations — target **zero** | #46 |
| Epistemic Correctness | premature causality, invalid promotion, abstention, correct supported level | #47 |
| Evidence & Provenance | correct evidence, verification, lineage completeness, rejection of invalid/wrong sources | #48 |
| Investigation Success | true-hypothesis retention, high-value missing evidence, task resolution, unnecessary-question penalty | #49 |
| Recovery & State | injected failures, retry semantics, state preservation, termination, unresolved parking | #50 |

## 6. Frozen regression gate (#51)

A change is accepted only if:

- the target failure improves, **and**
- safety, provenance, unrelated scenarios and the holdout do **not** regress.

Emits `before.json`, `after.json`, `comparison.md`.

## 7. Measured improvement story (#53)

The hackathon requires one **measured before -> after** improvement: capture a
real failure (e.g. premature causation), diagnose it from neatlogs traces, make
an architectural correction, and preserve the measurable before/after evidence.
