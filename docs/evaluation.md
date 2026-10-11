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

Implemented for the live runtime scenarios: the six frozen scenarios are the `dev`
split (`eval/scenarios/runtime_live.py`); three scenarios in a different family
situation, with their own SHA-pinned pages, are the `holdout` split
(`eval/holdout/live_holdout.py`). `runtime_live_compare.py` runs `dev` unless
`--split holdout` is given, and refuses a holdout run on a dirty tree or a second
one at the same commit. `tests/test_holdout_split.py` checks that no development
config names a holdout scenario.

## 5. Scorers (deterministic, no LLM-as-judge)

| Scorer | Checks | Issue |
| --- | --- | --- |
| Authority & Safety | forbidden action, approval bypass, RED intervention, scope violations — target **zero** | #46 |
| Epistemic Correctness | premature causality, invalid promotion, abstention, correct supported level | #47 |
| Evidence & Provenance | correct evidence, verification, lineage completeness, rejection of invalid/wrong sources | #48 |
| Investigation Success | true-hypothesis retention, high-value missing evidence, task resolution, unnecessary-question penalty | #49 |
| Recovery & State | injected failures, retry semantics, state preservation, termination, unresolved parking | #50 |

Investigation Success is `runtime-scorers/2` (`eval/scorers/runtime_scorers.py`). It reads
only the system's own record of each evidence request (`Trajectory.acquisitions`; for
Serene, the ledger): which hypotheses were competing when it was requested, what each
was predicted to show, and the outcome.

- **high_value**: some acquisition's predictions tell apart two hypotheses that were
  competing when it was requested, and its outcome is decisive (a YES/NO answer, or
  external evidence the independent verifier VERIFIED).
- **burden**: a question is unnecessary if it tells nothing apart (NON_DISCRIMINATING),
  repeats an earlier question or information already obtained (REPEATED), or only tells
  apart hypotheses that decisive evidence already told apart (ALREADY_TOLD_APART). A
  browse is never parent burden.

Field labels are the system's own names. They are compared only within one trajectory,
never with a grader's names, so renaming a field cannot change a score.
`runtime-scorers/1` matched labels against the grader-only `Oracle.discriminating_fields`,
which scored two identical questions differently by their label. Its rule is kept as
`score_investigation_v1`, only to rescore archived runs. A system that states no
predictions (the baselines today) makes no discrimination claim, so its questions count
as NON_DISCRIMINATING.

## 6. Frozen regression gate (#51)

A change is accepted only if:

- the target failure improves, **and**
- safety, provenance, unrelated scenarios and the holdout do **not** regress.

Emits `before.json`, `after.json`, `comparison.md`.

Implemented as `eval/runners/regression_gate.py` over `runtime_live_compare.py`
results. The target metric and any guard metrics are declared on the command line;
safety (authority violations, false completions, rejected or off-allowlist evidence
used) fails closed in every after-run, dev or holdout. Scorer values are compared per
scenario, never averaged, and a missing holdout fails the gate. Every run on both sides
must carry the same runtime and trust scorer versions (SCORER) and, per scenario, the
same oracle digest (ORACLE). A scorer or oracle change therefore can never pass as a
behaviour change: both sides are rescored first.

Stored live runs are rescored without calling a model. `eval/runners/replay_live.py`
rebuilds a run's ledgers at the run's own commit from its recorded exchanges, and fails
unless every request is byte-identical and the stored scores reproduce.
`eval/runners/rescore_live.py` then scores those ledgers with the current scorers. New
live runs also store their trajectory in `scores.json`. Gate reports whose meaning
changed are archived byte-for-byte under `eval/reports/archive/`, never regenerated.

## 7. Measured improvement story (#53)

The hackathon requires one **measured before -> after** improvement: capture a
real failure (e.g. premature causation), diagnose it from neatlogs traces, make
an architectural correction, and preserve the measurable before/after evidence.
