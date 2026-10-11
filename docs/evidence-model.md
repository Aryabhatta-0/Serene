# Serene Evidence Model

> **Status:** lineage, acquisition policy, bounded browser, independent verifier,
> caregiver disagreement and the ladder/gate are implemented. See
> [runtime.md](runtime.md) for code contracts and [maya-demo.md](maya-demo.md)
> for the deterministic rejection/recovery trajectory (#56).

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
   -> checks SOURCE_ALLOWED, DIGEST_MATCHES, SUBJECT_MATCHES,
      EFFECTIVE_DATE_VALID, REQUESTED_FIELDS_PRESENT, PROVENANCE_VALID
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

## 8. Acquisition is not verification

`HermesBrowser` audits executed tools, HTTPS domains and action bounds from the
ledger request. A capture enters as UNVERIFIED, with a digest and provenance.
`IndependentEvidenceVerifier` uses its own fetcher to confirm the excerpt is
present on the source and all six checks pass. Missing fetch capability rejects
the evidence. The production fetcher refuses redirects/private addresses and
caps bytes. Model confidence and a successful browser call cannot grant trust.
Admission rechecks verdict structure against the original request.

Failures append `EVIDENCE_ACQUISITION_FAILED` with consecutive attempt numbers;
retry budgets survive replay. Rejected evidence stays in history but cannot
support a promoted belief. In Maya, a transient failure at ledger #23 is retried,
the resulting unsupported excerpt is rejected at #26 (`EXCERPT_NOT_ON_SOURCE`),
and a subsequent bounded request yields verified evidence at #33. The fixture's
page fetch is synthetic/offline; the verifier and admission path are real.

## 9. Authority, non-goals and technology choices

Models suggest evidence and predictions; deterministic policy selects the
request; the independent verifier grants evidence status; the Promotion Gate
decides belief level. Parent approval is a separate safety requirement, never a
verifier verdict. Observational association and a scoped N-of-1 outcome do not
establish a general causal effect.

The MVP uses structured lineage and ordinal information value rather than
DoWhy/pgmpy/Cleanlab or a second retrieval/graph-memory system. There is no
probabilistic reliability score, automatic diagnosis, scraping of private parent
groups, or cost-based reduction in source/verifier requirements. See the
excluded-technology rationale in [architecture.md](architecture.md) and the
cost equivalence boundary in [economics.md](economics.md) (#55).
