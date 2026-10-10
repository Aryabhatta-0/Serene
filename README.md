# Serene

Serene is a **self-correcting, evidence-bound family intelligence agent**. It
helps a parent understand what is actually happening with their child, and
can always answer *why it believes what it believes*.

> **Models handle uncertainty; deterministic code handles authority.**
>
> what happened != what Serene remembers != what Serene believes

(The repository is still named `morrow`; the product, package and docs are Serene.)

## Trust boundary

```
model proposes -> kernel validates -> evidence supports -> parent authorizes
 -> experiments test -> Promotion Gate decides -> Dreaming consolidates
```

The model never controls epistemic promotion, safety decisions, parent
authorization, evidence validity or memory writes. Those live in the Serene
Domain Kernel, which depends on Pydantic only and never on the agent runtime.

## Status

The **foundation** is implemented and tested:

- strict Pydantic v2 domain contracts (Evidence → Observation → Pattern →
  Hypothesis → Experiment/Trial/Outcome → Learning, Investigation, MemoryPatch)
  with full provenance and supersession lineage;
- an append-only, per-child **hash-chained event ledger** (34-type closed
  taxonomy) with `append_event`, `verify_hash_chain`, `get_events_for_child`,
  `replay_events`, backed by a Supabase/Postgres migration with append-only
  triggers and RLS deny-by-default;
- five rebuildable projections (delete + replay = identical bytes);
- a fail-closed **Promotion Gate** (no level skipping), GREEN/AMBER/RED safety
  classification (RED fails closed), and an approval lifecycle that exists only
  as ledger state;
- ports for `AgentRuntime`, `EventStore`, `EvidenceBrowser`, `EvidenceVerifier`,
  `MemoryRepository`, `ObservabilitySink`, `Clock` (+ `CostModel`), with Hermes,
  Postgres, neatlogs and cfo.ai behind adapters;
- 144 tests (incl. real PostgreSQL and Hypothesis invariants), strict mypy,
  CI with no secrets, an Inspect AI scaffold, secret/PII scanning.

Not yet built: Hermes wiring, investigation loop, Telegram, Dream, UI. See
[docs/parallel-handoff.md](docs/parallel-handoff.md) for the two next branches.

## Quick start

```bash
uv sync --locked --all-extras --group dev
uv run pytest
uv run python scripts/ledger_selfcheck.py
uv run inspect eval eval/tasks/kernel_invariants.py --model mockllm/model
```

Full setup, pinned versions and the manual auth steps (Hermes, cfo.ai, Entire,
neatlogs, Supabase) are in [docs/setup.md](docs/setup.md). Copy `.env.example`
to `.env` locally; **never commit `.env`**.

## Repository layout

```
serene/domain        Canonical Pydantic v2 contracts, closed event taxonomy, canonical JSON
serene/lineage       Hashing, hash-chain verification, provenance validation, lineage tracing
serene/projections   Deterministic replay into KernelState + five read projections
serene/policies      Admission, Promotion Gate, safety, approval, acquisition ordering
serene/ledger        EventLedger: append / verify / read / replay
serene/ports         Stable Protocols the kernel depends on
serene/adapters      Hermes, Postgres/Supabase, neatlogs, cfo.ai, clock, in-memory store
serene/observability Privacy-safe, failure-isolated telemetry
serene/testing       Deterministic synthetic-family builder (synthetic data only)
serene/causal        Causal Twin (planned, #27)
serene/memory        Memory Repo + Dream (planned, #28-#32)
supabase/            config.toml + migrations (serene.domain_events, serene.projection_state)
memory_repo/         Git + Markdown durable memory
eval/                Inspect AI tasks, scenarios, baselines, scorers, reports
app/web              Next.js shell (placeholder)
app/telegram         Telegram boundary notes (branch A)
scripts/             bootstrap, ledger self-check, secret scan
docs/                architecture, event model, epistemic model, evidence, safety,
                     privacy, evaluation, setup, parallel handoff
tests/               Deterministic, adversarial and property tests
```

## Documentation

- [docs/architecture.md](docs/architecture.md) — layers, Hermes boundary, ownership, decisions
- [docs/event-model.md](docs/event-model.md) — envelope, hashing, taxonomy, admission rules
- [docs/epistemic-model.md](docs/epistemic-model.md) — ladder and promotion rules
- [docs/evidence-model.md](docs/evidence-model.md) — acquisition, browser, verifier
- [docs/safety.md](docs/safety.md) — GREEN/AMBER/RED, forbidden interventions, approvals
- [docs/privacy.md](docs/privacy.md) — data boundary, telemetry redaction, secrets
- [docs/evaluation.md](docs/evaluation.md) — Inspect AI harness, baselines, scorers
- [docs/setup.md](docs/setup.md) — toolchain, pins, manual steps
- [docs/parallel-handoff.md](docs/parallel-handoff.md) — the two next branches

## Engineering principles

- Fail closed around safety, promotion, evidence validity and authorization.
- Preserve raw history; derive rebuildable projections.
- Level-5 learnings always carry bounded scope and review/expiry semantics.
- Every consequential intervention requires explicit parent approval, recorded
  as ledger state from an authenticated channel.
- Dreaming proposes patches; it never silently rewrites memory.
- Synthetic child data only in tests, evaluation and demos.
- No LLM-as-judge where structured deterministic scoring is possible.
