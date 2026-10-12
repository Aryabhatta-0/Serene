# Serene safety

Audited against merged `main` at `6b82073` on 2026-10-12.
**LLM proposes; deterministic code decides.** Models may propose explanations
and experiments; they cannot change policy, verify their own evidence, grant
parent approval, promote beliefs or publish durable memory.
See [architecture.md](architecture.md) and [evidence-model.md](evidence-model.md).

## Safety and experiment boundary (#22–#26)

[Classification](../serene/policies/safety.py),
[structural requirements](../serene/policies/experiments.py),
[approval policy](../serene/policies/approval.py) and
[stateful admission](../serene/policies/admission.py) are deterministic. A
`POLICY`-attributed draft still must match the policy's result; a model rationale
cannot waive a requirement. These are structural/lexical checks, not a clinical
risk assessment or a guarantee that arbitrary real-world prose is safe.

| Class | Implemented rule | Human boundary |
| --- | --- | --- |
| GREEN | Known-safe category, reversible, low burden and ≤14 days | Exact authenticated parent approval required; at most one nudge |
| AMBER | Escalated category, higher burden or longer duration within ≤28 days | Explicit AMBER acknowledgment; at least ten minutes' deliberation; no nudge |
| RED | Forbidden category/term, irreversible, >28 days or unclassifiable | Blocked; no parent or model may override |

Forbidden categories include medication, supplements, allergy exposure,
treatment of symptoms, restraint, punishment, dangerous behavior, food deprivation
and sleep deprivation. Lexical matches can only escalate classification.
[Lifecycle entry](../serene/experiments/lifecycle.py) records `EXPERIMENT_BLOCKED`
for RED; request/grant/start checks also refuse it. Negative/property evidence:
[RED adversarial tests](../tests/test_red_adversarial.py),
[safety and approval tests](../tests/test_safety_and_approval.py).

The experiment must specify distinct, meaningful intervention/outcome/comparison,
be reversible, use at most four contexts within the hypothesis scope, and belong
to the same investigation. Requirements are recomputed for approval request,
grant and start; malformed or placeholder plans cannot proceed.

## Parent/human authorization boundary (#24, #40)

An approval is a ledger event from the requested PARENT, not an inference from
conversation. [TelegramChannel](../serene/adapters/telegram/channel.py) checks
webhook secret and private-sender binding; its callback must match an unused
prompt token, parent, chat and message. Text saying “sure” is only a report.
Only the authenticated channel adapter supplies the receipt; Hermes cannot mint
approval by returning a proposal. Main now includes a typed
[WEB_APP approval channel](../serene/adapters/web/approvals.py) and
[#37 decision surface](../app/web/components/experiments/DecisionPanel.tsx).
The channel requires an already authenticated parent principal, exact shown
digest/class and replay-protected request ID, then reuses ledger admission.
Session authentication is the transport's responsibility (#84): the kernel's
[`POST /web/approvals`](../serene/adapters/web/http.py) verifies the Supabase
session, guardianship and binding before the channel runs, and a RED request
is refused there and again at admission. The
[Experiments page](../app/web/app/experiments/page.tsx) offers a decision only
to a signed-in parent for their chosen child; fixture routes are synthetic and
are not live parent authorization.

| Binding checked by policy | Effect |
| --- | --- |
| Requested parent actor ID and authenticated channel | Caregiver/model/other-parent substitution fails |
| Exact intervention digest and current safety class | Changed intervention/class requires fresh authorization |
| Channel receipt received within the request window and not replayed | Old, future, wrong-channel or reused receipts fail |
| Expiry, bounded to at most seven days | An expired grant/request cannot start a trial |
| Awaiting experiment and explicit class acknowledgment | Late grants cannot revive abandoned experiments |
| Single consumption at `EXPERIMENT_STARTED` | Approval cannot authorize multiple starts |

AMBER deliberation is a fixed ten-minute delay, not professional review or a
second approver. Parent refusal is retained; the investigation controller stops
offering further experiment proposals in that investigation. Timeout/expiry
parks or abandons work rather than approving. Tests:
[approval binding](../tests/test_approval_binding.py),
[investigation approval](../tests/test_investigation_approval.py).

Authentication and actor construction are trusted backend responsibilities.
The kernel does not cryptographically authenticate a receipt object against a
malicious operator with code/credential access; database RLS and channel checks
must surround it. See [privacy.md](privacy.md#2-database-boundary-implemented).

## Outcomes, promotion and retained uncertainty

[ExperimentLifecycleService](../serene/experiments/service.py) handles
classification, approval, start, trials, outcomes, completion, abandonment and
timers. Outcome waiting ends after declared duration plus a three-day grace.
SUPPORTS, CONTRADICTS and INCONCLUSIVE are the actual outcome enum values;
there is no separate NO_EFFECT value. A no-effect report must be represented
through the applicable non-supporting outcome, not invented as support. Silence
cannot become supporting evidence. Contradicting outcomes can
refute hypotheses; history remains append-only. See
[lifecycle tests](../tests/test_experiment_lifecycle.py).

The [Promotion Gate](../serene/policies/promotion.py) is separate from approval
and completion. It forbids level skips and unverified lineage, and requires
approved completed supporting trials for level 4 plus bounded tested scope,
counterevidence/rival checks and review metadata for level 5. External source
verification cannot approve an intervention. Parent approval cannot verify a
source. N-of-1 support is not a causal-effect estimate or treatment recommendation.
[Promotion authority tests](../tests/test_promotion_authority.py) cover bypasses.

**Known limit:** current investigation COMPLETE can follow an empty/fully
excluded planner candidate list. Admission does not prove pairwise evidence
sufficiency. Draft [PR #69](https://github.com/Sathvikar01/morrow/pull/69) is
unmerged; do not claim this gap is fixed. The controller does have explicit
PARKED_UNRESOLVED paths for missing services, exhausted budgets and timeouts.
See [architecture's completion disclosure](architecture.md#telegram-hermes-and-investigation).

[Dream](../serene/memory/dream.py) cannot commit memory. Its deterministic
[Critic](../serene/policies/memory_review.py) and single
[MemoryCommitter](../serene/memory/committer.py) enforce lineage, authority,
current base and counterevidence. Refuted/superseded hypotheses remain in the
[Causal Twin](../serene/causal/model.py); memory deprecation keeps the record.
No hidden deletion or model-written truth is permitted.

## Economics and observability cannot waive safety (#52, #55, #59)

[Acquisition policy](../serene/policies/acquisition.py) removes unsafe/ineligible
options before cost ordering. The one [cfo.ai helper](../serene/adapters/cfoai.py)
compares optional first-hand pickup-cutoff confirmation from the parent versus
an already authorized caregiver only after trusted policy certifies the same
observation, predictions, quality, evidence requirements and uncertainty reduction.
Required parent questions disable the tradeoff. Equal HIGH ordinals alone do
not establish equivalence. The helper grants no access and sends no messages;
default runtime costs remain unknown. Unknown/invalid/failing prices are not free.

The populated cfo.ai Scenario/readback is genuine analysis evidence; its prices,
usage, revenue and cash are **assumed**, not measured production economics.
See [economics.md](economics.md), [readback](economics/cfo-readback.json),
[cost tests](../tests/test_acquisition_costs.py) and
[cfo.ai tests](../tests/test_cfoai_economics.py). Cost cannot override safety or quality.

[SafeTelemetry](../serene/observability/telemetry.py) isolates sink failures and
redacts metadata; [NeatLogs](../serene/adapters/neatlogs_sink.py) redacts again.
Diagnostics cannot approve, verify, promote or write memory. #59 is merged via
[PR #80](https://github.com/Sathvikar01/morrow/pull/80); its scans and error-boundary
checks do not establish production readiness or third-party privacy certification.

## Non-goals and evidence of assurance

The MVP does not permit LLM authority over policy, autonomous parent approval,
unverified evidence promotion, cost overriding safety/quality, silent uncertainty
or hidden deletion of refuted beliefs. It provides no diagnosis, treatment,
automated real-world intervention delivery or production family-data guarantee.
Current completion limitations remain disclosed, not recast as assurance.

The [Maya integration](maya-demo.md) uses synthetic input, offline external I/O,
real Telegram parsing/callback binding, verifier, experiment lifecycle and Dream
services. It proves an integrated fictional trajectory; negative/adversarial tests
prove the listed refusals. The [trust Inspect task](../eval/tasks/trust_invariants.py)
and [scorers](../serene/policies/scorers.py) test authority deterministically.
They do not establish a live-model improvement; [evaluation.md](evaluation.md)
preserves FAIL/INCONCLUSIVE/INVALID history and the separate controlled-dev/1
PASS with its unresolved-terminal and unrun-holdout limitations.

Kernel policy and Supabase RLS are the chosen small authority boundary; adding
OPA/OpenFGA/SpiceDB or a workflow engine would not replace those checks.
These exclusions have [recorded MVP rationale](architecture.md#non-goals-and-excluded-technologies).
Entire's incomplete #54 checkpoint coverage is development evidence, never
safety certification or child-evidence verification.
