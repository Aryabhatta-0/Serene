# Serene Evaluation

Inspect AI harness and deterministic scorers. See `docs/evaluation.md`.

| Directory | Holds |
| --- | --- |
| `scenarios/` | Visible development scenarios (~6–7) |
| `holdout/` | Hidden holdouts (~2–3), never tuned against directly |
| `fixtures/` | Synthetic child data and scenario fixtures |
| `baselines/` | Baseline A (Plain Hermes) and Baseline B (Hermes + memory/RAG) |
| `scorers/` | Deterministic scorers (authority, epistemic, evidence, investigation, recovery) |
| `runners/` | Harness entrypoints and the frozen regression gate |
| `reports/` | Generated `before.json`, `after.json`, `comparison.md` |

The evaluated agent must never grade itself. All child data used here is
synthetic.
