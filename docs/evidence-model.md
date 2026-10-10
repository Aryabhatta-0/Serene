# Serene Evidence Model

> **Status:** lineage (#7) and the ladder/gate (#17) are implemented — see
> [epistemic-model.md](epistemic-model.md). The `EvidenceBrowser` /
> `EvidenceVerifier` contracts exist in `serene/ports/evidence.py`; acquisition
> policy, browser and verifier implementations (#13–#16) and caregiver
> disagreement (#21) are branch A.

## 1. Principle

Evidence, not eloquence, decides what Serene believes. Two questions are always
answerable: *what supports this?* and *what would change our mind?*

## 2. Evidence acquisition pipeline

```
Minimum Sufficient Childhood Data policy   (#13)
   -> identifies the smallest missing observation likely to reduce uncertainty
   -> information value is ordinal: HIGH / MEDIUM / LOW  (no fake precision)

evidence acquisition priority              (#14)
   -> Safety -> evidence requirements -> information value -> burden/latency/cost
   -> cost may NEVER override safety

bounded EvidenceBrowser contract           (#15)
   -> goal, allowed domains, requested fields, max actions, forbidden actions
   -> Hermes Browser is the MVP implementation

External Evidence Verifier                 (#16)
   -> validates source, subject/context, effective date, requested fields,
      allowed domain, provenance
   -> emits EvidenceVerified  OR  EvidenceRejected
```

## 3. Information value is ordinal

Serene does **not** invent a numeric expected-information-gain score. It ranks
the smallest missing observation as HIGH, MEDIUM or LOW value. This is honest
about uncertainty and keeps the policy deterministic and testable.

## 4. Epistemic ladder

```
0 Raw Evidence
1 Observation
2 Pattern
3 Hypothesis
4 Tested Hypothesis
5 Contextual Learning
```

The Promotion Gate (#18) computes the **maximum permitted level** from
structured evidence. The LLM may request a level; it cannot authorize one.
Skipping levels is forbidden. Every transition is covered by deterministic
tests (#19), including negative/adversarial cases.

## 5. Level-5 semantics

A Contextual Learning is only valid within a bounded scope and with an
expiry/review date (#20):

- `valid_from`, `review_after`
- status: `ACTIVE`, `NEEDS_REVIEW`, `NEEDS_RETEST`, `STALE`, `DEPRECATED`
- retest triggers when context drifts

## 6. Lineage

Every derived object carries `derived_from[]`, creator, method, model version,
verification status, supersession and source IDs (#7). A belief without a
complete lineage is not trustworthy and cannot be promoted.

## 7. Caregiver disagreement

When caregivers disagree, Serene preserves **separate observer reports** and
exposes the disagreement as context (#21). It never averages reports into a
fake truth and never invents reliability scores.
