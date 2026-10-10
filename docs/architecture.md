# Serene Architecture

> **Status:** the Domain Kernel, event ledger, projections, ports and the
> deterministic trust foundation are implemented (see "Implemented vs planned").
> Hermes wiring, investigation loop, Telegram, Dream and UI are planned work on
> the two branches in [parallel-handoff.md](parallel-handoff.md).

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
| Side effects (browse, message, schedule) | Hermes behind `EvidenceBrowser` / gateway adapters | Bounded by request contracts (domains, fields, max actions, forbidden actions) |
| Trust of inputs | Kernel validation + `EvidenceVerifier` | Telegram/browser/model text is data; only verifier verdicts mark evidence VERIFIED/REJECTED |
| Epistemic authority | `policies.promotion` | Rung-by-rung; model rationale never consulted |
| Safety authority | `policies.safety` | GREEN/AMBER/RED; RED fails closed everywhere |
| Approval authority | Parent, recorded as `APPROVAL_GRANTED` from an authenticated channel | Bound to approver, intervention digest, expiry, single use |
| Truth / history | `serene.domain_events` ledger | Append-only, hash-chained; projections are disposable |
| Memory writes | Memory Committer (branch B) via `MemoryRepository.commit` | Ledger-backed authorization only |

Every ledger append passes, in order: closed-taxonomy + payload-schema check →
actor-kind and verification-status permissions → hash-chain verification of the
existing stream (a tampered stream accepts nothing) → ancestor check →
**stateful admission** (`policies.admission`) → sealing → compare-and-set append.
Admission *recomputes* the decision for every authority-bearing event, so even a
`POLICY`-attributed `PROMOTION_GRANTED`, `EXPERIMENT_CLASSIFIED` or
`EXPERIMENT_STARTED` is refused if the deterministic policy would not produce it.

## 4. Hermes boundary

Hermes (NousResearch/hermes-agent, pinned to tag `v2026.9.24`) is replaceable
infrastructure for reasoning, tools, skills, the Telegram gateway, the browser
and model routing.

| Hermes may | Hermes must never |
| --- | --- |
| Run bounded reasoning for an `AgentTask` and return `AgentRunResult` proposals | Append authority events (taxonomy forbids `AGENT` actors on grants, starts, verification, learnings, memory commits) |
| Drive the browser for an `EvidenceBrowseRequest` | Mark evidence VERIFIED, or verify its own acquisitions |
| Deliver Telegram messages; relay parent callbacks to the channel adapter | Turn message text into an approval (approval requires a channel receipt from the authenticated adapter, on `TELEGRAM`/`WEB_APP` source) |
| Keep its own conversational memory | Be read as Serene memory or belief (its memory is context, never authority) |

Only `serene/adapters/hermes/` may import Hermes. The current adapter fails
closed (`HermesNotConfigured`) until branch A implements it.

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
| Durable reviewed knowledge | `memory_repo/` (Git + Markdown) | Written only by the Memory Committer (branch B) |
| Runtime conversation / scratch | Hermes | Advisory context only |
| Telemetry | neatlogs | Opaque ids only; never read back for decisions |

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

## 9. Implemented vs planned

Implemented here: domain contracts (#1), ledger + hash chain + taxonomy (#3, #4,
#5), projections (#6), lineage validation/tracing (#7), ladder + gate + every
transition tested (#17, #18, #19), GREEN/AMBER/RED + forbidden RED (#22, #23),
approval lifecycle core (#24), ports incl. `AgentRuntime` / `EvidenceBrowser` /
`EvidenceVerifier` contracts (#2, #15 contracts only), neatlogs seam (#52),
cfo.ai seam (#55), Inspect AI scaffold (#41), CI gates (#58), secret/PII scan (#59).

Planned: see [parallel-handoff.md](parallel-handoff.md).

## 10. Excluded technology (MVP)

| Excluded | Why |
| --- | --- |
| Graphiti, Supermemory, Vektori, Mem0, Hindsight | Memory must be inspectable Git + Markdown with a single writer |
| OpenClaw | Hermes is the runtime |
| LangGraph, Temporal, Restate, Hatchet, DBOS | Orchestration is Hermes-owned; the kernel retains authority |
| Ax | Prompts are not the authority boundary |
| DoWhy, pgmpy, Cleanlab | The epistemic engine is deterministic and custom |
| OPA, OpenFGA, SpiceDB | Authorization is Supabase RLS + kernel code |
| SurrealDB, ElectricSQL | Supabase/PostgreSQL is canonical |
| PostHog, Jev | neatlogs + Entire + cfo.ai cover observability, provenance and economics |
