# Serene Event Model

> Code: `serene/domain/events.py`, `serene/domain/canonical.py`,
> `serene/lineage/hashing.py`, `serene/lineage/chain.py`, `serene/ledger/service.py`,
> `supabase/migrations/20261010120000_serene_domain_events.sql`.

## 1. Principles

- **Ledger = truth.** Every change of understanding is a *new* event. Nothing
  is updated or deleted, in code (no such methods exist) or in SQL (triggers).
- **Closed vocabulary.** 34 event types; each binds exactly one payload schema,
  the actor kinds allowed to append it, and the verification statuses it may carry.
- **Tamper-evident.** Each child's stream is a hash chain; `verify_hash_chain`
  pinpoints the first broken index and the reason.

## 2. Envelope (`DomainEvent`)

| Field | Set by | Meaning |
| --- | --- | --- |
| `event_id` | kernel | `evt_` + 32 hex |
| `child_id` | caller, validated | stream key (`chd_…`) |
| `sequence` | kernel | gapless from 1 per child |
| `event_type` | caller, validated | closed `EventType` |
| `schema_version` | payload | currently 1 for every payload |
| `hash_version` | kernel | currently 1 (rules below) |
| `source` | caller, validated | `SourceRef` (channel/document/browser/kernel) |
| `actor` | caller, validated against taxonomy | `ActorRef` (kind + opaque id) |
| `occurred_at` | caller | when it happened (UTC, aware) |
| `recorded_at` | kernel `Clock` | when the ledger admitted it |
| `derived_from` | caller, validated | ancestor **event** ids in the same stream |
| `verification_status` | caller, validated | `UNVERIFIED` / `VERIFIED` / `REJECTED` / `NOT_APPLICABLE` |
| `payload` | caller, validated | canonical JSON of the typed payload |
| `prev_event_hash` | kernel | previous `event_hash` or 64×`0` |
| `payload_hash` | kernel | `sha256(canonical_json(payload))` |
| `event_hash` | kernel | `sha256(canonical_json(header))`, header = every field above except `event_hash` |

## 3. Canonical JSON (hash_version 1)

UTF-8; no whitespace; keys sorted; scalars limited to str, int (|n| ≤ 2^53),
bool, null; **floats rejected**; datetimes must be aware and render as
`YYYY-MM-DDTHH:MM:SS.ffffffZ`; enums render as values; NUL rejected. A pinned
test vector lives in `tests/test_canonical_hashing.py`.

## 4. Taxonomy

| Area | Event | Allowed actors | Status |
| --- | --- | --- | --- |
| Observation | `OBSERVATION_REPORTED` (raw L0 evidence) | PARENT, CAREGIVER | UNVERIFIED / VERIFIED* |
| | `OBSERVATION_STRUCTURED` (L1) | AGENT, SYSTEM | UNVERIFIED |
| Evidence | `EVIDENCE_REQUESTED` | AGENT, SYSTEM, POLICY | n/a |
| | `EVIDENCE_ACQUIRED` (external document/browser) | SYSTEM, PARENT, CAREGIVER | UNVERIFIED |
| | `EVIDENCE_VERIFIED` / `EVIDENCE_REJECTED` | VERIFIER | VERIFIED / REJECTED |
| Pattern / hypothesis | `PATTERN_PROPOSED` (L2), `HYPOTHESIS_PROPOSED` (L3) | AGENT, SYSTEM | UNVERIFIED |
| | `HYPOTHESIS_SUPERSEDED` | AGENT, SYSTEM, POLICY | n/a |
| | `HYPOTHESIS_REFUTED` | POLICY | n/a |
| Promotion | `PROMOTION_REQUESTED` | AGENT, SYSTEM, PARENT | n/a |
| | `PROMOTION_GRANTED` / `PROMOTION_DENIED` | POLICY | n/a |
| Investigation | `INVESTIGATION_OPENED` | PARENT, AGENT, SYSTEM | n/a |
| | `INVESTIGATION_STATUS_CHANGED` | SYSTEM, POLICY | n/a |
| Experiment | `EXPERIMENT_PROPOSED` | AGENT, PARENT | UNVERIFIED |
| | `EXPERIMENT_CLASSIFIED`, `EXPERIMENT_BLOCKED`, `EXPERIMENT_STARTED`, `EXPERIMENT_COMPLETED` | POLICY | n/a |
| | `TRIAL_RECORDED` | PARENT, CAREGIVER, SYSTEM | UNVERIFIED |
| | `OUTCOME_REPORTED` | PARENT, CAREGIVER | UNVERIFIED / VERIFIED* |
| | `EXPERIMENT_ABANDONED` | PARENT, POLICY | n/a |
| Approval | `APPROVAL_REQUESTED` | POLICY | n/a |
| | `APPROVAL_NUDGED` | SYSTEM | n/a |
| | `APPROVAL_GRANTED` / `APPROVAL_REJECTED` | PARENT | n/a |
| | `APPROVAL_TIMED_OUT` | SYSTEM, POLICY | n/a |
| Learning | `LEARNING_RECORDED` (L5) | POLICY | VERIFIED |
| | `LEARNING_STATUS_CHANGED` | POLICY, SYSTEM | n/a |
| | `LEARNING_SUPERSEDED` | POLICY | n/a |
| Memory | `MEMORY_PATCH_PROPOSED` | AGENT, SYSTEM, PARENT | UNVERIFIED |
| | `MEMORY_PATCH_COMMITTED` / `MEMORY_PATCH_REJECTED` | MEMORY_COMMITTER | n/a |

\* `VERIFIED` on a human report means *channel-authenticated first-hand
report*: it proves who said it on which channel, not that it is true. It is
only admissible from a `TELEGRAM` or `WEB_APP` source.

## 5. Stateful admission (selected rules)

| Event | Refused when (reason codes) |
| --- | --- |
| any | unknown ancestor; actor/status not permitted; payload schema mismatch; child mismatch |
| `OBSERVATION_STRUCTURED` / `PATTERN_PROPOSED` / `HYPOTHESIS_PROPOSED` | promotion-gate introduction rules fail (see [epistemic-model.md](epistemic-model.md)) |
| `PROMOTION_GRANTED` | gate re-evaluation denies, or `STALE_FACTS_DIGEST` (ledger head moved) |
| `EXPERIMENT_CLASSIFIED` | `CLASSIFICATION_MISMATCH` vs. recomputed safety class |
| `APPROVAL_REQUESTED` | `RED_CANNOT_BE_APPROVED`, `SAFETY_CLASS_MISMATCH`, digest mismatch |
| `APPROVAL_GRANTED` | `APPROVER_MISMATCH`, `UNAUTHENTICATED_CHANNEL`, `CHANNEL_MISMATCH`, `APPROVAL_EXPIRED`, digest mismatch, `SAFETY_CLASS_NOT_ACKNOWLEDGED` |
| `APPROVAL_NUDGED` | `SINGLE_NUDGE_EXCEEDED` |
| `APPROVAL_TIMED_OUT` | `NOT_YET_EXPIRED` (timeout parks the request, never approves) |
| `EXPERIMENT_STARTED` | `RED_FAIL_CLOSED`, `NO_APPROVAL`, `APPROVAL_NOT_GRANTED`, `INTERVENTION_CHANGED_SINCE_APPROVAL`, `APPROVAL_ALREADY_USED`, `APPROVAL_EXPIRED` |
| `LEARNING_RECORDED` | no unused level-5 grant, scope broadened, validity > 180 days, already due for review, untested experiment |

A refusal raises `AdmissionRejected(reason_codes)` and writes nothing.

## 6. Entity field authority

| Field family | Who may set it | Authority role |
| --- | --- | --- |
| ids (`*_id`) | trusted code (`new_id`) | identity only; prefix encodes kind |
| `provenance.created_by/method/model` | caller, validated (AGENT ⇔ model method ⇔ `ModelRef`) | attribution for re-examination |
| `provenance.derived_from` / `source_ids` | caller, validated against ledger | lineage; sources must be reachable through parents |
| `provenance.verification_status` | caller, must match envelope | claim status, not truth |
| statements / descriptions | model or human | content; never consulted by policy |
| `alternative_explanations`, `falsification_criteria` | model | required structure for L3 admission |
| `Learning.scope/validity/review` | policy-built candidate | bounded applicability; parent reviewer |
| safety class, approval state, epistemic level | **never a field the proposer sets** | derived from ledger events by policy |

## 7. API

```python
ledger = EventLedger(store, clock, telemetry=build_telemetry())
event = ledger.append_event(draft)  # AdmissionRejected / LedgerIntegrityError
events = ledger.get_events_for_child(child_id)  # verified read
result = ledger.verify_hash_chain(child_id)  # ChainVerification(ok, failure_index, reason)
state = ledger.replay_events(child_id)  # KernelState
views = ledger.projections(child_id)  # the five projections
```
