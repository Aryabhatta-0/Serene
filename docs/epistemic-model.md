# Serene Epistemic Model

> Code: `serene/policies/promotion.py`, `serene/lineage/provenance.py`.
> Tests: `tests/test_promotion_policy.py` (every transition, positive + negative,
> with a meta-check that all five transitions are covered).

## 1. Ladder

```
0 RAW_EVIDENCE -> 1 OBSERVATION -> 2 PATTERN -> 3 HYPOTHESIS
  -> 4 TESTED_HYPOTHESIS -> 5 CONTEXTUAL_LEARNING
```

No rung may be skipped. Rungs 1–3 are reached by **introducing** a new entity
whose parents sit exactly one rung below. Rungs 4–5 are **promotions** of an
existing hypothesis decided by the gate and recorded as `PROMOTION_GRANTED`.
The model may *request*; only the gate *decides*. Request rationale text is
recorded but never read.

## 2. Rules per transition

Common to every rung (`provenance_violations`): all `derived_from` parents
exist; all `source_ids` are raw evidence, exist, are `VERIFIED`, and are
reachable through the entity's own parents (no citing unrelated evidence);
typed references (`evidence_ids`, `observation_ids`, `pattern_ids`, …) appear in
`derived_from`; model-derived objects name their `ModelRef`.

| Transition | Admitted only if | Typical denial codes |
| --- | --- | --- |
| 0 → 1 Observation | parents are L0 evidence, all `VERIFIED` | `UNVERIFIED_EVIDENCE`, `LEVEL_SKIP` |
| 1 → 2 Pattern | ≥2 distinct L1 observations from ≥2 occasions, all active | `SINGLE_OCCASION`, `INSUFFICIENT_OBSERVATIONS`, `LEVEL_SKIP` |
| 2 → 3 Hypothesis | L2 pattern parents; alternatives or competitors listed; falsification criteria; open investigation; cited support/counter-evidence verified | `NO_ALTERNATIVES_CONSIDERED`, `INVESTIGATION_CLOSED`, `LEVEL_SKIP` |
| 3 → 4 Tested hypothesis | hypothesis active; complete verified lineage; ≥1 experiment **completed** that started under a **granted, consumed, non-RED** approval; ≥1 `SUPPORTS` outcome and no `CONTRADICTS` | `NO_APPROVED_COMPLETED_EXPERIMENT`, `NO_SUPPORTING_OUTCOME`, `CONTRADICTING_OUTCOME` |
| 4 → 5 Contextual learning | grant to level 5 for this hypothesis, unused; learning scope ⊆ hypothesis scope; validity window ≤ 180 days, current; parent reviewer; retest triggers; experiments/outcomes tested | `SCOPE_BROADENED`, `VALIDITY_TOO_LONG`, `ALREADY_DUE_FOR_REVIEW`, `GRANT_ALREADY_USED` |

`max_permitted_level(hypothesis)` returns the highest rung the current ledger
supports, capped at 4 because rung 5 additionally requires an explicit, scoped
learning candidate.

## 3. What level 4 does *not* mean

Serene does not perform statistical causal inference. Level 4 means "an
approved, bounded N-of-1 experiment ran and its recorded outcomes support and do
not contradict the hypothesis in this scope". It is never presented as a causal
effect size.

## 4. Level-5 semantics

A `Learning` always carries `Scope(child_id, contexts)`, a `ValidityWindow`
(`valid_from`, `review_after`), `ReviewMetadata` (parent reviewer, retest
triggers) and starts `ACTIVE`. Status transitions are a closed state machine
(`ACTIVE ↔ NEEDS_REVIEW`, `→ NEEDS_RETEST`, `→ STALE`, `→ DEPRECATED` terminal).
`effective_learning_status(record, now)` never presents a learning past
`review_after` as `ACTIVE`.

## 5. Supersession

Changed understanding appends `HYPOTHESIS_SUPERSEDED` / `LEARNING_SUPERSEDED`;
the superseded object remains in the ledger and in lineage traces.
`trace_lineage(entity_id, state)` reconstructs the full chain from any entity
down to raw evidence and reports missing ancestors.
