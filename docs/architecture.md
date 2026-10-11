# Serene Architecture

> **Status:** the kernel, investigation/evidence loop, Telegram boundary,
> experiment lifecycle, Dream and Causal Twin are implemented. The canonical
> [Maya demo](maya-demo.md) runs their real services with deterministic offline
> model/browser I/O. This proves integration, not live provider connectivity or
> production readiness. Privacy audit #59 and merge enforcement #58 remain open.

## 1. Thesis

```
what happened   !=   what Serene remembers   !=   what Serene believes
(ledger events)      (memory_repo, Git+MD)        (projections over the ledger)
```

**Core rule: models handle uncertainty; deterministic code handles authority.**
A model may interpret a parent's message, propose a pattern, a hypothesis, an
experiment or a memory patch. It can never decide that evidence is valid, that
a belief is promoted, that an intervention is safe, that a parent approved, or
that memory changes.

## 2. Layers and the dependency rule

```
                 +-----------------------------------------------+
                 |   serene.adapters  (replaceable infrastructure) |
                 |   hermes/ postgres neatlogs_sink cfoai clock     |
                 |   in_memory_event_store                          |
                 +----------------------+------------------------+
                                        | implements
                 +----------------------v------------------------+
                 |   serene.ports  (stable Protocols)             |
                 |   AgentRuntime EventStore EvidenceBrowser      |
                 |   EvidenceVerifier MemoryRepository Clock      |
                 |   ObservabilitySink CostModel                  |
                 +----------------------+------------------------+
                                        | used by
   +------------------------------------v-----------------------------------+
   |  Domain Kernel (Pydantic v2 only; no Hermes, no SDKs, no adapters)       |
   |                                                                         |
   |  serene.ledger        append_event / verify_hash_chain /                |
   |                       get_events_for_child / replay_events              |
   |  serene.policies      admission, promotion gate, safety, approval,      |
   |                       acquisition ordering                              |
   |  serene.projections   KernelState fold + 5 read projections             |
   |  serene.lineage       hashing, chain verification, provenance, tracing  |
   |  serene.observability SafeTelemetry (redaction + failure isolation)     |
   |  serene.domain        entities, value objects, closed event taxonomy,   |
   |                       canonical JSON                                    |
   +-------------------------------------------------------------------------+
```

Dependencies point inward only: `domain <- lineage <- projections <- policies
<- ledger`; `ports` depend on `domain`; `adapters` depend on everything above
them and nothing depends on `adapters`. `tests/test_architecture_boundaries.py`
fails the build if any kernel module imports Hermes, an adapter, psycopg,
neatlogs, Inspect AI or a model SDK, and checks in a fresh interpreter that
importing the kernel loads none of them.

## 3. Ownership of reasoning, execution, trust and authority

| Concern | Owner | Notes |
| --- | --- | --- |
| Interpretation / planning | Model via `AgentRuntime` (Hermes adapter) | Returns typed proposals (`AgentProposal` union) or `Abstain` / `NeedEvidence` |
| Investigation phases and acquisition selection | `InvestigationService` + `MinimumDataPolicy` | Ledger-guarded phase machine, bounded budgets and deterministic request selection |
| Browser execution / message delivery | `EvidenceBrowser` / Telegram adapters | Bounded by request contracts (domains, fields, max actions, forbidden actions); live browser execution uses Hermes |
| Trust of inputs | Kernel validation + `EvidenceVerifier` | Telegram/browser/model text is data; only verifier verdicts mark evidence VERIFIED/REJECTED |
| Epistemic authority | `policies.promotion` | Rung-by-rung; model rationale never consulted |
| Safety authority | `policies.safety` | GREEN/AMBER/RED; RED fails closed everywhere |
| Approval authority | Parent, recorded as `APPROVAL_GRANTED` from an authenticated channel | Bound to approver, intervention digest, expiry, single use |
| Truth / history | `serene.domain_events` ledger | Append-only, hash-chained; projections are disposable |
| Memory writes | `MemoryCommitter` via `MemoryRepository.commit` | Deterministic Critic and ledger-backed authorization only; Dream drafts cannot write directly |

Every ledger append passes, in order: closed-taxonomy + payload-schema check →
actor-kind and verification-status permissions → hash-chain verification of the
existing stream (a tampered stream accepts nothing) → ancestor check →
**stateful admission** (`policies.admission`) → sealing → compare-and-set append.
Admission *recomputes* the decision for every authority-bearing event, so even a
`POLICY`-attributed `PROMOTION_GRANTED`, `EXPERIMENT_CLASSIFIED` or
`EXPERIMENT_STARTED` is refused if the deterministic policy would not produce it.

## 4. Hermes boundary

Hermes is replaceable infrastructure for reasoning, browser tools and model
routing. The installed integration uses its OpenAI-compatible Responses API;
Serene owns the authenticated Telegram ingress and investigation controller.
See [runtime.md](runtime.md) for the transport contract and tested setup.

| Hermes may | Hermes must never |
| --- | --- |
| Run bounded reasoning for an `AgentTask` and return `AgentRunResult` proposals | Append authority events (taxonomy forbids `AGENT` actors on grants, starts, verification, learnings, memory commits) |
| Drive the browser for an `EvidenceBrowseRequest` | Mark evidence VERIFIED, or verify its own acquisitions |
| Deliver Telegram messages; relay parent callbacks to the channel adapter | Turn message text into an approval (approval requires a channel receipt from the authenticated adapter, on `TELEGRAM`/`WEB_APP` source) |
| Keep its own conversational memory | Be read as Serene memory or belief (its memory is context, never authority) |

Only `serene/adapters/hermes/` may integrate the Hermes runtime. Missing live
configuration fails closed; the canonical demo instead supplies scripted
transport responses through this same adapter. It does not bypass admission.

## 5. Two representative trajectories

**Happy path** (executed by `serene.testing.build_full_ladder`, 23 events):
parent report on Telegram (`OBSERVATION_REPORTED`, VERIFIED as a first-hand
channel-authenticated report) → model-structured observations (L1) → pattern
over ≥2 occasions (L2) → investigation → hypothesis with alternatives and
falsification criteria (L3) → experiment proposed → `EXPERIMENT_CLASSIFIED`
GREEN → `APPROVAL_REQUESTED` → parent `APPROVAL_GRANTED` with channel receipt →
`EXPERIMENT_STARTED` (admission recomputed) → outcome reports → completed →
`PROMOTION_GRANTED` 3→4 → `PROMOTION_GRANTED` 4→5 → `LEARNING_RECORDED`
(scoped, 60-day review window, parent reviewer).

**Denied path** (`tests/test_safety_and_approval.py`): a model proposes a
calming supplement. Classification is RED; a `POLICY`-attributed approval
request claiming GREEN is refused (`SAFETY_CLASS_MISMATCH`,
`RED_CANNOT_BE_APPROVED`); a parent grant for a non-existent request is
refused; `EXPERIMENT_STARTED` is refused with `RED_FAIL_CLOSED` + `NO_APPROVAL`.
Each refusal raises `AdmissionRejected` and leaves the stream byte-identical.

## 6. State ownership

| Data | Store | Authority |
| --- | --- | --- |
| Domain events | `serene.domain_events` (Supabase Postgres) | Truth; append-only, hash-chained per child |
| Read models | `serene.projection_state` / in-process `KernelState` | Disposable; rebuilt by replay |
| Durable reviewed knowledge | `memory_repo/` (Git + Markdown) | Written only by the Memory Committer |
| Runtime conversation / scratch | Hermes | Advisory context only |
| Telemetry | NeatLogs / recording sink | Redacted diagnostic metadata; never read back for decisions. Known audit gaps are recorded in [privacy.md](privacy.md) |

## 7. Integrity and concurrency

- Per-child hash chain: `prev_event_hash`, `payload_hash`, `event_hash` over
  canonical JSON ([event-model.md](event-model.md)).
- Writers use compare-and-set on the stream head (`ConcurrencyConflict` on a
  stale head) plus a per-child advisory lock in Postgres; unique
  `(child_id, sequence)` and `(child_id, prev_event_hash)` prevent forks.
- Postgres triggers reject UPDATE / DELETE / TRUNCATE and any insert that does
  not extend the head. A superuser can still bypass triggers; that is detected
  by `verify_hash_chain` (tested in `tests/test_postgres_ledger.py`).

## 8. Decisions

| # | Decision | Alternatives | Why | Limitation / fallback |
| --- | --- | --- | --- | --- |
| D1 | One hash chain **per child** | Global chain | Independent verification per family, no cross-family contention, aligns with RLS scope | Cross-child ordering is not provable (not needed) |
| D2 | Ledger **re-runs policy** on authority events | Trust POLICY-attributed events | A buggy/compromised caller cannot record a grant the gate would deny | Replay per append is O(n); add snapshotting when streams grow |
| D3 | Canonical JSON bans floats, NUL, naive datetimes | Accept and normalize | Byte-identical hashing across Python and Postgres jsonb | Quantities use integers (e.g. micro-USD) |
| D4 | Kernel is Pydantic-only; Hermes behind ports | Build on Hermes primitives | Runtime is replaceable; authority stays testable without a model | Adapter work duplicates some Hermes plumbing |
| D5 | Ledger lives in a non-exposed `serene` schema with RLS deny-by-default | `public` schema + PostgREST | No accidental API exposure of child data before #8 | Clients go through the service-role backend |
| D6 | Real-Postgres tests via `pgserver` locally, service container in CI | Docker-only `supabase start` | Works on machines without Docker; same SQL as Supabase | PG16 locally vs PG17 in CI/Supabase |
| D7 | Information value and acquisition order are **ordinal** | Numeric expected information gain | No fake precision; deterministic | Coarser ranking |
| D8 | No statistical causal inference | DoWhy-style estimation | Out of scope; N-of-1 support is recorded, not estimated | Level 4 means "tested with supporting outcome", not "causal effect estimated" |

## 9. Implementation and demo boundaries

| Capability | Implementation / evidence | Issues |
| --- | --- | --- |
| Domain, ledger, replay, lineage | `serene/domain`, `ledger`, `projections`, `lineage`; real Postgres and deterministic tests | #1–#8 |
| Investigation and evidence | `serene/investigation`, `evidence`, `adapters/browser`; independent re-fetch verifier | #9–#16, #21 |
| Promotion, safety, approval and trials | `serene/policies`, `experiments`; adversarial authority tests | #17–#26 |
| Causal Twin and reviewed memory | `serene/causal`, `memory`, `adapters/git_memory.py`; accepted/rejected Dream patches | #27–#32 |
| Runtime telemetry and economics | NeatLogs adapter (#52); genuine synthetic cfo.ai Scenario and local integer model (#55) | #52, #55 |
| Canonical synthetic demonstration | Real Telegram channel, real controller/verifier/lifecycle/Dream; offline external I/O; repeatable reset | #56, #57 |
| Evaluation and release assurance | Inspect tasks and fail-closed scorer gate implemented; controlled live result pending; privacy/required-check gaps remain | #41–#51, #53, #58, #59 |

The web app is a tested read-only synthetic shell; the canonical E2E artifact is
the demo's JSON/HTML report. It is not a claim that the web shell is wired to a
live family database. [parallel-handoff.md](parallel-handoff.md) is historical
branch-planning context, not current delivery status.

Non-goals: clinical diagnosis/treatment, statistical causal effect estimation,
unsupervised interventions, autonomous approval, model-written durable memory,
production family-data hosting, and a new orchestration/evaluation platform.

## 10. Excluded technology (MVP)

| Excluded | Why |
| --- | --- |
| Graphiti, Supermemory, Vektori, Mem0, Hindsight | Memory must be inspectable Git + Markdown with a single writer |
| OpenClaw | Hermes is the runtime |
| LangGraph, Temporal, Restate, Hatchet, DBOS | The existing ledger-backed investigation controller and bounded Hermes execution suffice for this demo |
| Ax | Prompts are not the authority boundary |
| DoWhy, pgmpy, Cleanlab | The epistemic engine is deterministic and custom |
| OPA, OpenFGA, SpiceDB | Authorization is Supabase RLS + kernel code |
| SurrealDB, ElectricSQL | Supabase/PostgreSQL is canonical |
| PostHog, Jev | NeatLogs is the existing tracing seam; adding another service is unnecessary. Entire's #54 provenance limitation is not evidence of a completed integration |
