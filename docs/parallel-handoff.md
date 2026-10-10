# Parallel Handoff: two next branches

Both branches start from the foundation PR
(`feat(core): establish Serene domain kernel and event foundation`). Neither
needs the other to start. Environment setup is done; do **not** reinstall tools
(run `scripts/bootstrap.*` only to verify). Use the agent-engineering skills
(`agent-architecture`, `deterministic-authority`, `evidence-provenance`,
`structured-output-design`, `agent-testing`, plus `human-in-the-loop`,
`agent-security`, `agent-observability`, `agent-failure-recovery` where triggered).

## Shared, frozen-by-default surface

Owned by neither branch. Change only additively, in small commits that name the
other branch's owner as reviewer:

| Path | Rule |
| --- | --- |
| `serene/domain/**` | Additive fields/types only; never loosen validation; bump `schema_version` for breaking payload changes |
| `serene/domain/events.py` `EventType` + `EVENT_TAXONOMY` | A adds only in the *observation / evidence / investigation* blocks; B only in *experiment / approval / promotion / learning / memory* blocks |
| `serene/ports/**`, `serene/ledger/**`, `serene/lineage/**` | Contract changes need both owners |
| `serene/projections/state.py` | Add new `match` cases only for your own events |
| `supabase/migrations/` | Never edit an applied migration; add new timestamped files. Whoever merges second regenerates the `event_type` check constraint (kept honest by `tests/test_migrations.py`) |
| `.env.example`, `docs/architecture.md` §9 | Append-only edits |

Invariants both branches must keep green: `uv run ruff check .`, `uv run mypy`,
`uv run pytest` (incl. Postgres + Hypothesis), `scripts/ledger_selfcheck.py`,
`scripts/secret_scan.py`, kernel-independence tests.

---

## Branch A — `feat/runtime-investigation-evidence`

**Hermes + investigation + evidence + Telegram/runtime path.**

| | |
| --- | --- |
| Owns (exclusive) | `serene/adapters/hermes/`, `serene/adapters/telegram/` (new), `serene/adapters/browser/` (new), `serene/investigation/` (new), `serene/evidence/` (new), `app/telegram/`, `eval/baselines/`, `eval/scenarios/` (investigation/evidence scenarios), `docs/runtime.md` (new) |
| Consumes | `AgentRuntime`, `AgentTask`, `AgentRunResult`/`AgentProposal`; `EvidenceBrowser`, `EvidenceBrowseRequest/Result`; `EvidenceVerifier`, `VerificationVerdict`; `EventLedger.append_event`, `EventDraft`; `KernelState` + projections (read); `policies.acquisition.rank_acquisition_options`; `SafeTelemetry` / `build_telemetry`; `ChannelReceipt` |
| Produces | `HermesAgentRuntime.run` (real); kernel boundary service converting `AgentProposal` → `EventDraft` with the AGENT actor stamped by the kernel; Telegram channel adapter that verifies the webhook secret and mints `ChannelReceipt`; events `OBSERVATION_REPORTED/STRUCTURED`, `EVIDENCE_REQUESTED/ACQUIRED/VERIFIED/REJECTED`, `INVESTIGATION_OPENED/STATUS_CHANGED`, `PATTERN_PROPOSED`, `HYPOTHESIS_PROPOSED/SUPERSEDED`, `EXPERIMENT_PROPOSED`, and parent `APPROVAL_GRANTED/REJECTED` delivered through Telegram |
| Issues | #2 (complete), #9, #10, #11, #12, #13, #14, #15 (impl), #16, #21, #40, #42, #43, #48, #49, #50, #52 (trace coverage), #53 |
| Must not | let Hermes append POLICY/VERIFIER/MEMORY_COMMITTER events; treat model text as approval; call the verifier from inside the browser adapter |

## Branch B — `feat/trust-experiments-memory`

**Promotion + safety + experiments + memory/Dream path.**

| | |
| --- | --- |
| Owns (exclusive) | `serene/policies/` (extend promotion, safety, approval, admission), `serene/experiments/` (new), `serene/memory/` (Memory Repo I/O, Memory Committer, Dream, Critic), `serene/adapters/git_memory.py` (new), `serene/causal/`, `memory_repo/`, RLS migrations for #8, `docs/safety.md`, `docs/epistemic-model.md` |
| Consumes | `EventLedger`, `KernelState`, projections; `MemoryRepository`, `CommitAuthorization`, `CommitReceipt`; `CostModel`; `Clock`; `SafeTelemetry` |
| Produces | N-of-1 lifecycle service (classification → approval request → single nudge → timeout/park → start → `WAITING_FOR_OUTCOME` timeout → completion); `EXPERIMENT_CLASSIFIED/BLOCKED/STARTED/COMPLETED/ABANDONED`, `APPROVAL_REQUESTED/NUDGED/TIMED_OUT`, `PROMOTION_*`, `HYPOTHESIS_REFUTED`, `LEARNING_*`, `MEMORY_PATCH_*` events; Git `MemoryRepository` adapter; single-writer Memory Committer; Dream pipeline that only proposes patches; learning staleness/retest jobs; RLS policies |
| Issues | #8, #17–#20 (extend), #22–#26, #27, #28–#32, #46, #47, #55 (cfo.ai cost table) |
| Must not | add model calls inside policy decisions; let Dream write `memory_repo/` directly; weaken any existing fail-closed test |

## Interfaces between A and B

| Seam | Producer → consumer | Contract |
| --- | --- | --- |
| Experiment proposals | A (`EXPERIMENT_PROPOSED`) → B (classification/approval) | ledger events only; no direct calls |
| Approval UX | B (`APPROVAL_REQUESTED`, `pending_approvals` projection) → A (Telegram prompt) → A (`APPROVAL_GRANTED/REJECTED` with `ChannelReceipt`) → B (admission already enforced by kernel) | |
| Timers | A's runtime scheduler calls B's lifecycle functions (`nudge_due`, `timeout_due`) | pure functions over `KernelState` + `Clock` returning `EventDraft`s |
| Promotion | A (`PROMOTION_REQUESTED`) → B (`PROMOTION_GRANTED/DENIED`) | |
| Memory | B (`MEMORY_PATCH_*`, `memory_repo/`) → A (contextual retrieval reads via `MemoryRepository.read`) | read-only for A |

## Merge dependencies

1. Foundation PR merges first.
2. A and B proceed in parallel; either may merge first. The second rebases and
   resolves only the shared-surface hot spots above (taxonomy blocks, reducer
   cases, migration constraint, `.env.example`).
3. After both: demo fixture + reset (#56, #57), scenarios/holdout/regression
   gate (#44, #45, #51), Supabase Realtime + UI (#33–#39), README/docs (#60–#62).
4. Record one Entire checkpoint per milestone (#54): ingestion, investigation,
   verifier, promotion gate, Dream, eval improvement, Causal Twin.
