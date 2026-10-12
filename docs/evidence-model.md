# Serene evidence model

Evidence, not eloquence, constrains belief. Serene keeps what was reported,
what it remembers and what it currently believes separate. This implements the
[architecture thesis](architecture.md#thesis-and-state-ownership): **LLM proposes;
deterministic code decides.** Source: merged `main` at `6b82073` (2026-10-12).

## Reports, captures and verification

| Input | Admission and meaning | Implementation / evidence |
| --- | --- | --- |
| Parent/caregiver report | Raw bytes preserved before structuring; VERIFIED authenticates a first-hand channel report, not objective truth or caregiver agreement | [ingestion](../serene/evidence/ingestion.py), [Telegram channel](../serene/adapters/telegram/channel.py), [tests](../tests/test_telegram_ingestion.py), #9 |
| Structured observation/pattern/hypothesis | Model proposal must pass schema, lineage and introduction checks; cannot overwrite the raw report | [KernelBoundary](../serene/investigation/boundary.py), [Promotion Gate](../serene/policies/promotion.py), #17–#19 |
| External browser capture | Enters UNVERIFIED with source, content digest and provenance; successful execution gives no trust | [EvidenceService](../serene/evidence/service.py), [capture format](../serene/evidence/capture.py), #15 |
| External verifier verdict | Only the independent verifier grants VERIFIED/REJECTED; admission rechecks the decidable verdict/request constraints | [verifier](../serene/evidence/verifier.py), [external-evidence policy](../serene/policies/external_evidence.py), [tests](../tests/test_evidence_path.py), #16 |

The browser has a goal, allowed HTTPS domains, requested fields, action budget
and forbidden actions in its [port contract](../serene/ports/evidence.py).
[HermesBrowser](../serene/adapters/browser/hermes_browser.py) audits actual tool
execution against those bounds; browser and model cannot verify their own output.

The default `IndependentEvidenceVerifier` requires an independent source re-fetch
and all six checks: SOURCE_ALLOWED, DIGEST_MATCHES, SUBJECT_MATCHES,
EFFECTIVE_DATE_VALID, REQUESTED_FIELDS_PRESENT and PROVENANCE_VALID. It checks
field values occur in the excerpt, a subject token is present, the effective date
is within bounds and the excerpt occurs in the re-fetched page. Missing/unreachable
fetch or unsupported content rejects. The [HTTP fetcher](../serene/adapters/browser/fetch.py)
rejects redirects/private addresses and caps bytes. The constructor can explicitly
disable mandatory re-fetch; that mode does not establish independent source
confirmation. These are syntactic/source checks, not a semantic truth oracle.

Acquisition failures append numbered `EVIDENCE_ACQUISITION_FAILED` attempts;
replay does not replenish retry budgets. Rejected captures remain in history but
cannot support promotion. The [Maya trajectory](maya-demo.md) proves transient
failure → retry → `EXCERPT_NOT_ON_SOURCE` rejection → later verified acquisition
using an offline fictional page and the real verifier/admission code (#56).

## Minimum data and investigation boundary

The model suggests candidates; [MinimumDataPolicy](../serene/investigation/minimum_data.py)
computes ranking. Information value is ordinal: HIGH when live hypotheses predict
different answers, MEDIUM when at least one predicts an answer, LOW otherwise.
Unsafe, LOW and already-requested field subsets are excluded. The policy selects
at most one candidate by safety → evidence need → information value → burden →
latency, then cost only when the entire top evidence request is equivalent.
There is no numerical expected-information-gain claim (#13, #14).

This is a ranking of proposed candidates, not a proof the planner proposed all
useful observations. Current `Selection.sufficient` means no candidate selected;
empty or fully excluded plans can lead to COMPLETE without decisive evidence.
[Phase admission](../serene/policies/investigation.py) checks structural progress,
not every competing hypothesis pair. The unmerged
[PR #69](https://github.com/Sathvikar01/Serene/pull/69) is a proposed correction,
not implemented sufficiency on `main`. COMPLETE gives no promotion authority.

## Epistemic ladder and promotion

| Level | Meaning and deterministic requirement | Evidence |
| --- | --- | --- |
| 0 — Raw Evidence | Preserved report/capture with source and digest; external capture may still be UNVERIFIED or REJECTED | [entities](../serene/domain/entities.py), [ingestion](../serene/evidence/ingestion.py) |
| 1 — Observation | Introduced from verified level-0 evidence with valid provenance | [check_introduction](../serene/policies/promotion.py) |
| 2 — Pattern | Introduced from observations on at least two distinct occasions, with counter-observations retained | [check_introduction](../serene/policies/promotion.py) |
| 3 — Hypothesis | Pattern-derived explanation with alternatives/competitors, scope and falsification criteria; cited evidence verified | [hypothesis schema](../serene/domain/entities.py), [gate](../serene/policies/promotion.py) |
| 4 — Tested Hypothesis | One-rung promotion supported by a completed approved non-RED trial with supporting outcome and verified lineage | [evaluate_promotion](../serene/policies/promotion.py) |
| 5 — Contextual Learning | One-rung promotion/learning with tested bounded scope, outcome/counterevidence checks, no equally tested rival and validity/review metadata | [gate](../serene/policies/promotion.py), [learning policy](../serene/policies/learning.py) |

Levels 1–3 introduce derived entities; levels 4–5 promote an existing hypothesis.
The [legal transition table](../serene/policies/ladder.py) forbids level skips.
The model may request a level; deterministic policy grants or refuses it and
admission recomputes the decision. Rationale and confidence are not authority.
[Promotion tests](../tests/test_promotion_policy.py) and
[authority tests](../tests/test_promotion_authority.py) cover negative transitions
and unverified lineage (#17–#19).

Level 4 means a bounded approved N-of-1 trial supported this explanation in its
scope; it is not an estimated causal effect. Level 5 carries `valid_from`,
`review_after`, scope and reviewer metadata. Maximum validity is 180 days;
the default review window is 60 days. ACTIVE, NEEDS_REVIEW, NEEDS_RETEST, STALE
and DEPRECATED keep uncertainty/age explicit. Context drift or contradiction can
require retest/deprecation; passing the date does not create new evidence.
See [learning tests](../tests/test_learning_validity.py) (#20).

## Lineage, disagreement and refutation

[Provenance](../serene/domain/values.py) records creator, method, timestamps,
model/version where applicable, source IDs, `derived_from`, verification status
and supersession. [Lineage tracing](../serene/lineage/provenance.py) follows derived
objects to raw evidence; missing/rejected/unverified ancestry prevents promotion
([tests](../tests/test_promotion_authority.py), #7).

[Context retrieval](../serene/investigation/context.py) preserves separate observer
reports and caregiver disagreement (#21); no averaging into invented truth or
reliability scores. [Causal Twin](../serene/causal/model.py) exposes support,
counterevidence, confounders, alternatives and CANDIDATE/SUPPORTED/REFUTED/
SUPERSEDED status. Refutation appends a fact and retains the old hypothesis.
[Dream/Critic](../serene/policies/memory_review.py) requires counterevidence in
memory patches; deprecation replaces silent deletion. Reviewed memory is context,
never a new raw evidence source or a shortcut to belief promotion (#27–#32).
Critic verification checks structured fields and recorded contradictions; it
does not prove that arbitrary Dreamer prose is semantically true.

## Authority and non-goals

Parent authorization and evidence verification answer separate questions.
An approval permits one exact non-RED experiment; it does not verify a claim.
A verifier verdict confirms bounded source checks; it never approves an
intervention. Neither a model, telemetry nor cfo.ai may cross those boundaries.

[The #55 cost helper](../serene/adapters/cfoai.py) grants no access and preserves
required parent questions. Assumed prices break only policy-certified equivalence
ties; equal HIGH ordinals alone are insufficient. See [economics.md](economics.md)
and [acquisition tests](../tests/test_acquisition_costs.py).

No unverified evidence promotion, silent uncertainty, hidden deletion of refuted
beliefs, diagnosis, private-parent-group scraping, cost-reduced verification or
general causal-effect claim is permitted. Git memory/structured lineage and the
custom deterministic ladder replace extra graph-memory or statistical causal
stacks for this MVP; [architecture exclusions](architecture.md#non-goals-and-excluded-technologies)
link the recorded technology rationale. [Entire #54](https://github.com/Sathvikar01/Serene/issues/54)
is development provenance only and remains incomplete; checkpoint references
cannot substitute for child-evidence lineage.
