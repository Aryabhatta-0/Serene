# Serene Safety

> **Code:** `serene/policies/safety.py` (classifier), `serene/policies/approval.py`
> (approval binding), `serene/policies/experiments.py` (structural requirements,
> outcome window), `serene/experiments/` (N-of-1 lifecycle), `serene/policies/scorers.py`
> (Authority & Safety scorer), `serene/adapters/cfoai.py` (cost boundary).
> **Tests:** `test_safety_and_approval.py`, `test_approval_binding.py`,
> `test_red_adversarial.py`, `test_experiment_lifecycle.py`, `test_scorers.py`,
> `test_cfoai_economics.py`, `eval/tasks/trust_invariants.py`.

## 1. Fail-closed principle

Around safety, promotion, evidence validity and authorization, Serene fails
**closed**. If a decision cannot be established as safe and authorized, it does
not happen. Every authority decision is recomputed by the ledger's admission
before an event is sealed, so even a `POLICY`-attributed event cannot record a
classification, approval, start or completion the policy would not produce.

## 2. GREEN / AMBER / RED intervention classifier (#22)

| Class | Meaning | Behaviour |
| --- | --- | --- |
| GREEN | Reversible, low-burden, short (<= 14 days), known-safe category | May progress with parent approval; one nudge allowed |
| AMBER | Higher burden, longer (<= 28 days) or escalated category (caregiver coordination, sleep schedule, meal timing, screen time) | **Escalated for stronger human judgement** (section 4.2) |
| RED | Forbidden category or term, irreversible, > 28 days, unclassifiable | **Fails closed**: classified, then `EXPERIMENT_BLOCKED`; never requested, approved or started |

Lexical screening for forbidden terms can only escalate to RED, never lower a
class. Classification is deterministic and recomputed at request, grant and
start; a classifier change after a request invalidates the request
(`SAFETY_CLASS_CHANGED_SINCE_REQUEST`) and any grant (`APPROVAL_SAFETY_CLASS_STALE`).

## 3. Forbidden RED interventions (#23)

These can **never** enter experimentation, regardless of approvals or model output:
medication, supplements, allergy exposure, treatment of symptoms, restraint,
punishment, dangerous behaviour, food deprivation, sleep deprivation.
Each is blocked at lifecycle entry with an auditable `EXPERIMENT_BLOCKED`
naming the category (`FORBIDDEN_CATEGORY:<name>`). Hypothesis property tests
show every forbidden category is RED for every other field value, and every
irreversible intervention is RED.

## 4. Parent approval (#24)

### 4.1 What an approval binds

An `APPROVAL_GRANTED` is admitted only if **all** of these hold:

| Binding | Refusal codes |
| --- | --- |
| The requested **parent identity** (actor kind PARENT, exact actor id) | `APPROVER_NOT_PARENT`, `APPROVER_MISMATCH`, `ACTOR_NOT_PERMITTED` |
| The **exact intervention digest** | `INTERVENTION_DIGEST_MISMATCH` |
| An authenticated **channel receipt** on the same channel, received inside the request window, never used before | `UNAUTHENTICATED_CHANNEL`, `CHANNEL_MISMATCH`, `RECEIPT_REPLAYED`, `RECEIPT_PREDATES_REQUEST`, `RECEIPT_IN_FUTURE` |
| **Expiry** (requests: <= 7 days, never in the past) | `APPROVAL_EXPIRED`, `EXPIRY_TOO_LONG`, `EXPIRY_IN_PAST` |
| The **current safety class**, explicitly acknowledged | `SAFETY_CLASS_NOT_ACKNOWLEDGED`, `SAFETY_CLASS_CHANGED_SINCE_REQUEST` |
| An experiment still awaiting approval | `EXPERIMENT_NOT_AWAITING_APPROVAL` (a late grant cannot revive an abandoned experiment) |
| **Single use**: consumed by exactly one `EXPERIMENT_STARTED` | `APPROVAL_ALREADY_USED` |

Prose is never authority. A parent typing "sure" is an observation; the
runtime relaying it as a grant fails at the channel boundary. Only the
authenticated channel adapter can mint the `ChannelReceipt` on a real
`APPROVAL_GRANTED` from the parent.

### 4.2 AMBER escalation

AMBER is never nudged (`NUDGE_NOT_PERMITTED:AMBER`), its grant must
acknowledge AMBER explicitly, and the grant must arrive at least
`AMBER_MIN_DELIBERATION` (10 minutes) after the request
(`AMBER_DELIBERATION_TOO_SHORT`). Rejection is always immediate.

### 4.3 Nudge, timeout, park

One nudge (GREEN only) at half the request window; at expiry the request is
`APPROVAL_TIMED_OUT` and the experiment `PARKED_UNRESOLVED`. Timeout never
approves.

## 5. Safe N-of-1 experiment lifecycle (#25, #26)

```
EXPERIMENT_PROPOSED (agent / parent)
 -> EXPERIMENT_CLASSIFIED            deterministic class
    -> EXPERIMENT_BLOCKED            RED or structural requirements unmet
 -> APPROVAL_REQUESTED               GREEN 48 h / AMBER 72 h
    -> APPROVAL_NUDGED (GREEN, once) -> APPROVAL_TIMED_OUT (park)
    -> APPROVAL_GRANTED / REJECTED   parent, authenticated channel receipt
 -> EXPERIMENT_STARTED               safety + approval binding recomputed
 -> WAITING_FOR_OUTCOME              until started_at + duration + 3-day grace
    -> OUTCOME_REPORTED / TRIAL_RECORDED   refused after the window
    -> EXPERIMENT_OUTCOME_TIMED_OUT  no outcome by the deadline: abandoned
 -> EXPERIMENT_COMPLETED / ABANDONED
 -> Promotion Gate                   PROMOTION_GRANTED / PROMOTION_DENIED (3 -> 4)
```

Structural requirements, recomputed at request, grant and start: an explicit
intervention, outcome measure and comparison (no placeholders, all distinct);
reversible; at most 4 contexts, all within the hypothesis scope; same
investigation. Pure step functions (`nudge_due`, `timeout_due`, `start_due`,
`learning_validity_due`) are the timer seam the lifecycle service calls.

## 6. Authority invariants (scored, target zero violations)

`score_authority` (`serene/policies/scorers.py`) replays any trajectory and
reports, separately: `FORBIDDEN_ACTION`, `APPROVAL_BYPASS`,
`RED_INTERVENTION`, `SCOPE_VIOLATION`. Any finding fails the run. It works on
logs that never went through admission (baselines), because it re-decides
every event with the same deterministic policies.

## 7. Cost never overrides safety (cfo.ai, #55)

Current implementation and the genuinely populated cfo.ai Scenario are documented
in [economics.md](economics.md). The historical v1 scaffold's local arithmetic
and evaluation fixture are retained for compatibility.
The v2 model adds provenance, storage/memory-read/telemetry costs and sensitivity.
Cost requires explicit policy eligibility and certified evidence equivalence;
required parent questions disable the tradeoff.

Evidence acquisition is ordered **safety > evidence quality > information
value > cost**; cost only breaks ties inside the top equivalence class, unsafe
options are dropped, and an unknown cost is never "free"
(`serene/policies/acquisition.py`).

The current helper compares only optional first-hand pickup-cutoff confirmation
from the parent versus an already authorized caregiver. Trusted policy must
certify equal evidence requirements, admissibility, predictions and uncertainty
reduction. Required parent questions disable the tradeoff. The helper cannot
grant access, message a caregiver or override the independent verifier.

The provenance-bearing v2 model and genuine cfo.ai readback are in
[economics.md](economics.md). Its prices, usage, revenue and cash are explicitly
assumed; they are not actual provider spend. The old
`eval/fixtures/cfoai_acquisition_decision.json` is preserved as a historical v1
fixture, not the current financial result or a globally enabled runtime planner.

## 8. Demo, non-goals and excluded technologies

The [Maya demo](maya-demo.md) (#56) proves that its GREEN proposal is approved
through the real Telegram callback binding before start, and that outcome,
promotion and Dream memory review follow in order. Synthetic outcomes describe
one fictional scoped trial; they are not a recommendation for a real child.
Negative/adversarial tests remain the evidence for RED and forged approval
refusals, which the happy-path demonstration does not perform.

Serene provides no medical diagnosis/treatment, autonomous intervention or
permission inferred from prose. A parent cannot override a RED classification.
The kernel classifier/admission and Supabase RLS suffice for this MVP; adding
OPA/OpenFGA/SpiceDB or an external workflow engine would not replace these
authority checks. See [architecture.md](architecture.md) for rationale and
[privacy.md](privacy.md) for the separate unresolved audit boundary (#59).
