# Serene Epistemic Model

> Code: `serene/policies/ladder.py` (transition table), `serene/policies/promotion.py`
> (Promotion Gate), `serene/policies/learning.py` (validity), `serene/lineage/provenance.py`,
> `serene/causal/model.py` (Causal Twin), `serene/memory/critic.py` (memory gate),
> `serene/policies/scorers.py` (Epistemic Correctness scorer).
> Tests: `test_promotion_policy.py` (every transition, positive + negative, meta-check),
> `test_promotion_authority.py` (36-pair transition table, Level-5 rules),
> `test_learning_validity.py`, `test_causal_twin.py`, `test_scorers.py`.

## 1. Ladder and transition table

```
0 RAW_EVIDENCE -> 1 OBSERVATION -> 2 PATTERN -> 3 HYPOTHESIS
  -> 4 TESTED_HYPOTHESIS -> 5 CONTEXTUAL_LEARNING
```

`serene.policies.ladder.TRANSITIONS` lists the only five legal moves, each
with its mechanism and the only events that may record it:

| Move | Mechanism | Recorded by | Requires |
| --- | --- | --- | --- |
| 0 -> 1 | introduction | `OBSERVATION_STRUCTURED` | parents at L0, evidence VERIFIED |
| 1 -> 2 | introduction | `PATTERN_PROPOSED` | parents at L1, two distinct occasions |
| 2 -> 3 | introduction | `HYPOTHESIS_PROPOSED` | parents at L2, alternatives, falsification criteria, open investigation |
| 3 -> 4 | promotion | `PROMOTION_GRANTED` (POLICY only) | complete verified lineage, approved completed non-RED experiment, supporting outcome, no contradicting outcome |
| 4 -> 5 | promotion | `PROMOTION_GRANTED` then `LEARNING_RECORDED` (POLICY only) | the 3 -> 4 rules plus section 4 |

Every other pair fails before any evidence is read: `LEVEL_SKIP` (upward
skip), `NOT_A_PROMOTION` (same or lower rung), `PROMOTION_VIA_INTRODUCTION_ONLY`
(a promotion request for rungs 1-3). The model may *request*
(`PROMOTION_REQUESTED`); the gate *decides*, and its decision - grant **or**
denial - is recomputed at admission (`DENIAL_NOT_JUSTIFIED`,
`REASON_CODES_MISMATCH`, `STALE_FACTS_DIGEST`). Request rationale is recorded but
never read.

## 2. Rules per transition

Common to every rung (`provenance_violations`): all `derived_from` parents
exist; all `source_ids` are raw evidence, exist, are `VERIFIED`, and are
reachable through the entity's own parents (no citing unrelated evidence);
typed references appear in `derived_from`; model-derived objects name their
`ModelRef`.

| Transition | Typical denial codes |
| --- | --- |
| 0 -> 1 | `UNVERIFIED_EVIDENCE`, `LEVEL_SKIP` |
| 1 -> 2 | `SINGLE_OCCASION`, `INSUFFICIENT_OBSERVATIONS`, `LEVEL_SKIP` |
| 2 -> 3 | `NO_ALTERNATIVES_CONSIDERED`, `INVESTIGATION_CLOSED`, `LEVEL_SKIP` |
| 3 -> 4 | `NO_APPROVED_COMPLETED_EXPERIMENT`, `NO_SUPPORTING_OUTCOME`, `CONTRADICTING_OUTCOME`, `MISSING_ANCESTOR` |
| 4 -> 5 | `NO_CONFOUNDERS_CONSIDERED`, `UNRESOLVED_COMPETITOR`, `OUTCOME_OMITTED`, `SCOPE_EXCEEDS_TESTED_CONTEXTS`, `SCOPE_BROADENED`, `VALIDITY_TOO_LONG`, `ALREADY_DUE_FOR_REVIEW`, `GRANT_ALREADY_USED` |

## 3. Counterevidence

`counterevidence_for(hypothesis)` gathers everything in the ledger that speaks
against a hypothesis: contradicting and inconclusive outcomes on **any** of its
experiments (completed, abandoned or running), its cited counter-evidence,
counter-observations of its patterns, and equally-tested active rivals. A
contradicting outcome anywhere blocks 3 -> 4 and 4 -> 5, and makes a memory
document asserting the claim fail the Critic (`CONTRADICTED_BY_OUTCOME`). A
memory document must list every counterevidence id (`COUNTEREVIDENCE_OMITTED`).

## 4. Level 5: contextual learning

A learning is admitted only with: an unused level-5 grant for its hypothesis;
complete, verified lineage for every parent; confounders considered; no
equally-tested active rival; every outcome of each cited experiment cited (no
cherry-picking); at least one supporting outcome cited; scope within the
hypothesis scope **and** within the contexts actually tested; validity window
<= 180 days that is current; a parent reviewer and retest triggers.
`build_learning_candidate` builds exactly such a candidate (60-day review,
retest triggers from confounders and falsification criteria); nothing in it
comes from model text except the restated hypothesis statement.

## 5. Learning validity (#20)

```
ACTIVE -> NEEDS_REVIEW   review_after reached, or the hypothesis was superseded
ACTIVE -> NEEDS_RETEST   contradicting outcome, or meaningful context drift
*      -> STALE          unreviewed for 30 days past review_after
*      -> DEPRECATED     hypothesis refuted or learning superseded (terminal)
```

*Meaningful context drift* is a verified observation, recorded after the
learning became active, whose contexts overlap the learning's scope and include
a closed drift marker (`new_caregiver`, `schedule_change`, `moved_home`,
`illness`, ...). Drift can only lower trust.

`effective_status(record, state, now)` is never more trusted than the ledger
status: it applies time and every outstanding signal immediately, so a learning
is never presented as ACTIVE between its review date and the scheduled job.
`surfaceable_learnings` and memory retrieval (`serene/memory/retrieval.py`)
surface only effectively-ACTIVE learnings. Lowering trust is always
admissible; re-activation must be justified by policy (inside the window,
nothing outstanding, and after a retest a newer approved, completed experiment
with only supporting outcomes).

## 6. What level 4 does *not* mean

Serene does not perform statistical causal inference. Level 4 means "an
approved, bounded N-of-1 experiment ran and its recorded outcomes support and do
not contradict the hypothesis in this scope". The Causal Twin (`serene/causal`)
records one edge per hypothesis as `CANDIDATE`, `SUPPORTED`, `REFUTED` or
`SUPERSEDED`, separating observational from experimental support, with
counterevidence, confounders, experiments, scope, validity and provenance - and
deliberately no numeric confidence. A `SUPPORTED` edge requires experimental
support at level >= 4, no contradiction and a trusted learning.

## 7. Experience, memory, belief

```
experience = ledger events (Postgres)      written by the ledger only
memory     = memory_repo (Git + Markdown)  written by the Memory Committer only
belief     = Causal Twin / projections     rebuilt from the ledger only
```

Memory documents carry ledger-computed front matter and pass a deterministic
Critic (format, lineage, contradiction search, memory Promotion Gate) before
the single-writer committer applies them (`memory_repo/README.md`). Belief is
never read from memory: `build_causal_twin` takes ledger state only.

## 8. Supersession

Changed understanding appends `HYPOTHESIS_SUPERSEDED` / `LEARNING_SUPERSEDED`;
the superseded object remains in the ledger and in lineage traces.
`trace_lineage(entity_id, state)` reconstructs the full chain from any entity
down to raw evidence and reports missing ancestors.

## 9. Scoring epistemic correctness (#47)

`score_epistemic(trajectory, claims)` rebuilds an honest state from admissible
events only and reports `INVALID_PROMOTION` (inadmissible ladder events in the
trajectory), `PREMATURE_CAUSALITY` (causal claim below level 4),
`WRONG_SUPPORTED_LEVEL` and `MISSING_ABSTENTION`, and credits
`CORRECT_ABSTENTION`. It is deterministic and needs no model.
