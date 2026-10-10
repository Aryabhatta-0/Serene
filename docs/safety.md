# Morrow Safety

> **Status:** design specification. Implemented by issues #22–#26, #46, #58, #59.

## 1. Fail-closed principle

Around safety, promotion, evidence validity and authorization, Morrow fails
**closed**. If a decision cannot be established as safe and authorized, it does
not happen.

## 2. GREEN / AMBER / RED intervention classifier (#22)

| Class | Meaning | Behaviour |
| --- | --- | --- |
| GREEN | Reversible, low-risk | May enter the experiment pipeline with parent approval |
| AMBER | Uncertain / higher burden | Escalates for explicit judgement before any action |
| RED | Not acceptable autonomously | **Fails closed** — never enters autonomous experimentation |

## 3. Forbidden RED interventions (#23)

These can **never** enter autonomous experimentation:

- medication
- supplements
- allergy exposure
- treatment of symptoms
- restraint
- punishment
- dangerous behaviour
- food deprivation
- sleep deprivation

## 4. Parent approval lifecycle (#24)

States: `APPROVE` / `REJECT` / `TIMEOUT`, with a **single** nudge and
`PARKED_UNRESOLVED` on non-response. `WAITING_FOR_OUTCOME` also has timeout
handling — an approved experiment that never reports an outcome does not hang
forever.

## 5. Safe N-of-1 experiment lifecycle (#25, #26)

```
ExperimentProposed -> safety policy -> ApprovalRequested -> Approved
 -> Started -> OutcomeReported -> Completed -> PromotionGate
```

Every experiment is reversible, minimal, context-limited, and records explicit
intervention, outcome, comparison, provenance and parent approval.

## 6. Authority invariants (scored, target zero violations)

- No forbidden action executes.
- No approval is bypassed.
- No RED intervention runs autonomously.
- No experiment exceeds its declared scope.

These are checked deterministically by the Authority & Safety scorer (#46) and
enforced as CI quality gates (#58).
