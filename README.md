# Morrow

Morrow is a **self-correcting family intelligence agent**. It helps a parent
understand what is actually happening with their child — and, critically,
*why it believes what it believes*.

Morrow is built around one rule:

> **What happened != what Morrow remembers != what Morrow believes.**

Three layers are kept separate on purpose:

| Layer | Substrate | Meaning |
| --- | --- | --- |
| Experience | Postgres experience tables | Raw, timestamped happenings |
| Memory | Git + Markdown `memory_repo/` | Durable, reviewed, versioned knowledge |
| Belief | Causal Twin / investigation state | Currently held, evidence-bound hypotheses |

## Trust boundary

```
LLM proposes -> Code validates -> Evidence supports -> Parent authorizes
 -> Experiments test -> Promotion Gate decides -> Dreaming consolidates
```

The LLM **never** independently controls:

- epistemic promotion
- safety decisions
- parent authorization
- evidence validity
- memory promotion
- causal truth

Every important belief must answer: *"Why do you believe this?"*

## Status

**Bootstrap only.** This repository currently contains the architecture, the
documentation, the project/CI scaffolding, and a complete implementation
backlog (see Issues). No feature is implemented yet — modules under `morrow/`
declare their contract and link to the issue that will implement them. Nothing
here pretends to work.

## Stack (frozen for the MVP)

Hermes (runtime, Telegram, tools, scheduling, browser, model routing) ·
Python + Pydantic v2 (Domain Kernel) · Supabase/PostgreSQL (canonical state) ·
immutable hash-chained Event Ledger · Postgres projections · Git + Markdown
(Memory Repo) · custom Dream pipeline · deterministic Promotion Gate ·
Hermes Browser behind `EvidenceBrowser` · custom deterministic causal/epistemic
engine · Next.js · React Flow · Supabase Realtime · Inspect AI + deterministic
scorers · neatlogs · Entire · cfo.ai · XState only if it materially simplifies
UI state.

Deliberately **excluded** from the MVP (see `docs/architecture.md`): Graphiti,
Supermemory, Vektori, Mem0, Hindsight, OpenClaw, LangGraph, Temporal, Restate,
Hatchet, DBOS, Ax, DoWhy, OPA, SurrealDB, OpenFGA, SpiceDB, pgmpy, Cleanlab,
ElectricSQL, PostHog, Jev.

## Repository layout

```
app/web            Next.js web application (five surfaces)
app/telegram       Morrow-side Hermes/Telegram tool boundary
morrow/domain      Canonical Pydantic schemas + authority semantics
morrow/policies    Deterministic policies (safety, evidence, Promotion Gate)
morrow/causal      Deterministic causal / epistemic engine (Causal Twin)
morrow/lineage     Evidence / provenance lineage
morrow/projections Rebuildable read-side projections
morrow/memory      Git-backed Memory Repo + Dream pipeline
morrow/tools       Bounded tool contracts (EvidenceBrowser, ...)
memory_repo/       Git + Markdown durable memory (child, caregivers, ...)
eval/              Inspect AI harness, scenarios, baselines, scorers, reports
docs/              Architecture, evaluation, safety, evidence, privacy
tests/             Deterministic tests
```

## Documentation

- [docs/architecture.md](docs/architecture.md) — components, authority boundaries, data flow
- [docs/evidence-model.md](docs/evidence-model.md) — evidence ladder, browser, verifier, lineage
- [docs/safety.md](docs/safety.md) — GREEN/AMBER/RED, forbidden interventions, approvals
- [docs/privacy.md](docs/privacy.md) — RLS, access scopes, synthetic data, PII-safe logs
- [docs/evaluation.md](docs/evaluation.md) — Inspect AI harness, baselines, scorers

## Development

```bash
# Python (Domain Kernel + policies + tests)
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -e ".[dev]"
pytest

# Web
npm --prefix app/web install
npm --prefix app/web run typecheck
```

Copy `.env.example` to `.env` and fill in locally. **Never commit `.env`.**

## Engineering principles

- Do not optimize for LOC; do not build speculative abstractions.
- Explicit deterministic policies around authority.
- No LLM-as-judge where structured deterministic scoring is possible.
- Fail closed around safety, promotion, evidence validity and authorization.
- Preserve raw history; derive rebuildable projections.
- Level-5 learnings always carry bounded scope + expiry/review semantics.
- Every consequential intervention requires explicit parent approval.
- Every Dream produces proposed patches, never silent rewrites.
- Use synthetic child data in automated tests and evaluation.
