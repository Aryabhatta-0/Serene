# Morrow Architecture

> **Status:** design specification for the MVP. No component below is fully
> implemented yet; each maps to issues in the tracker.

## 1. Thesis

Morrow must not confuse three different things:

```
what happened   !=   what Morrow remembers   !=   what Morrow believes
(experience)         (memory)                     (belief)
```

Most assistant systems collapse these into one vector store, which makes it
impossible to answer *"why do you believe this?"*. Morrow keeps them in
separate substrates with an explicit authority pipeline between them.

## 2. Authority pipeline

```
LLM proposes -> Code validates -> Evidence supports -> Parent authorizes
 -> Experiments test -> Promotion Gate decides -> Dreaming consolidates
```

Each stage has an owner and a failure mode:

| Stage | Owner | On failure |
| --- | --- | --- |
| Propose | LLM / Hermes | Rejected as malformed |
| Validate | Domain Kernel (Pydantic v2) | Reject (fail closed) |
| Evidence supports | Verifier + lineage | `EvidenceRejected` |
| Parent authorizes | Approval lifecycle | `PARKED_UNRESOLVED` |
| Experiments test | Safety policy + N-of-1 lifecycle | Policy blocks |
| Promote | Deterministic Promotion Gate | No promotion |
| Consolidate | Dream + Critic + Memory Committer | Patch rejected with reason |

The LLM can *request* promotion, but only the Promotion Gate *authorizes* it.

## 3. Components

### 3.1 Hermes runtime
Owns orchestration, Telegram, tool execution, scheduling, browser and model
routing. Hermes talks to Morrow only through the **Domain Kernel boundary**
(issue #2): adapter + tool interfaces. The kernel owns semantics and authority
and must remain replaceable-runtime compatible.

### 3.2 Domain Kernel (`morrow/domain`)
Canonical Pydantic v2 schemas: Observation, Evidence, Pattern, Hypothesis,
Investigation, Experiment, Trial, Outcome, Learning, MemoryPatch. Strict
validation and schema versioning. **No unstructured authority-bearing LLM
output may enter here.**

### 3.3 Event Ledger (`morrow/ledger` via projections/lineage)
Append-only `domain_events` table with `source`, `actor`, `occurred_at`,
`recorded_at`, `derived_from[]`, verification status. Tamper-evident hash chain:
canonical serialization, `prev_event_hash`, `payload_hash`, `event_hash`, plus
`append_event()` and `verify_hash_chain()`. Raw history is preserved.

### 3.4 Projections (`morrow/projections`)
Read state (`current_child_state`, `active_investigations`,
`active_hypotheses`, `pending_approvals`, `active_learnings`) is derived by
deterministic replay. The UI never reads the ledger directly as a view model
(issue #33). Projections can be deleted and rebuilt.

### 3.5 Lineage (`morrow/lineage`)
Every derived object carries `derived_from[]`, creator, method, model version,
verification status, supersession and source IDs. Lineage is the mechanism
behind *"why do you believe this?"*.

### 3.6 Memory (`morrow/memory`) — Git + Markdown
The Memory Repo is a Git repository of Markdown files
(`memory_repo/{child,caregivers,routines,patterns,investigations,decisions,learnings}`).
Simple file read/search, proposed patches, diffs and commits. **No embeddings in
the MVP.** Only the single-writer Memory Committer may modify it.

### 3.7 Dream pipeline
`ORIENT -> CONSOLIDATE -> REFLECT -> CHALLENGE -> VERIFY -> PROPOSE PATCH`.
Dreaming may propose but never directly mutate trusted memory. The Dream Critic
runs contradiction search, lineage verification and Promotion Gate validation
before any patch can be committed.

### 3.8 Causal / epistemic engine (`morrow/causal`)
Deterministic Causal Twin: candidate variables/edges, confounders, support,
counterevidence, intervention, comparison, outcomes, bounded scope. **No DoWhy**
or other external causal library in the MVP.

## 4. Epistemic ladder

```
Raw Evidence -> Observation -> Pattern -> Hypothesis -> Tested Hypothesis
 -> Contextual Learning
```

No level may be skipped silently. The maximum permitted level is computed by
the deterministic Promotion Gate from structured evidence.

## 5. Excluded technology and rationale

| Excluded | Why not in the MVP |
| --- | --- |
| Graphiti, Supermemory, Vektori, Mem0, Hindsight | Memory must be inspectable Git + Markdown with a single writer; external memory stores hide the write path |
| OpenClaw | Hermes is the frozen runtime |
| LangGraph, Temporal, Restate, Hatchet, DBOS | Orchestration is Hermes-owned; durable-workflow frameworks add authority the kernel must retain |
| Ax | Prompts are not the authority boundary |
| DoWhy, pgmpy, Cleanlab | The causal/epistemic engine must be deterministic and custom, not a black box |
| OPA, OpenFGA, SpiceDB | Authorization is Supabase RLS + Code, kept small and auditable |
| SurrealDB, ElectricSQL | Supabase/PostgreSQL is canonical |
| PostHog, Jev | neatlogs + Entire + cfo.ai cover observability, provenance and economics |

## 6. Data flow (investigation, happy path)

1. Parent sends a Telegram message -> Hermes -> `ObservationReported` (raw preserved).
2. Domain Kernel independently creates `ObservationStructured` (never overwrites raw).
3. Investigation state machine advances; contextual retrieval loads experience,
   memory and current belief state **without collapsing the three layers**.
4. Competing hypotheses are retained with supporting evidence, counterevidence,
   scope and known confounders.
5. Minimum Sufficient Childhood Data policy names the smallest missing
   observation; evidence acquisition priority orders it (Safety first).
6. `EvidenceBrowser` performs bounded acquisition; the External Evidence Verifier
   emits `EvidenceVerified` or `EvidenceRejected`.
7. Promotion Gate computes the permitted epistemic level.
8. If an intervention is warranted: safety classification -> approval lifecycle
   -> N-of-1 experiment -> outcome -> Promotion Gate.
9. Dream proposes patches; Critic verifies; Memory Committer commits or rejects.
10. Causal Twin and projections update; UI reflects state via Realtime.
