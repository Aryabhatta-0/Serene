# Serene runtime: investigation and evidence path (branch A)

How a parent's message becomes evidence, how an investigation decides what to
learn next, and how outside evidence is acquired and verified. Hermes is the
model runtime; it **proposes**. Every authoritative change is a ledger event
that admission re-checks.

```
Telegram ──secret+binding──▶ TelegramChannel ──▶ OBSERVATION_REPORTED (verbatim)
                                   │                   │
                                   │                   ▼ Hermes (structure, wire contract)
                                   │            KernelBoundary ─▶ OBSERVATION_STRUCTURED
                                   │                           └▶ OBSERVATION_STRUCTURING_FAILED
                                   ▼
             APPROVAL_GRANTED/REJECTED (ChannelReceipt)   OBSERVATION_REPORTED(request_id) = micro-answer

InvestigationService (phase machine, ledger-guarded)
  UNDERSTANDING → RETRIEVING_CONTEXT → FORMING_HYPOTHESES (Hermes, ≥2 competitors)
  → NEEDS_EVIDENCE (Hermes suggests, MinimumDataPolicy picks ≤1) ─▶ EVIDENCE_REQUESTED
       ├─ ASK_PARENT → ASKING_HUMAN (one-time YES/NO/UNSURE prompt) ──────────────┐
       └─ BROWSE     → RESEARCHING (HermesBrowser, bounded) ─▶ EVIDENCE_ACQUIRED   │
                                         └▶ EVIDENCE_ACQUISITION_FAILED (counted)  │
  → VERIFYING (IndependentEvidenceVerifier) ─▶ EVIDENCE_VERIFIED / EVIDENCE_REJECTED◀┘
  → EVALUATING (Hermes) → COMPLETE | NEEDS_EVIDENCE | NEEDS_APPROVAL | PARKED_UNRESOLVED
```

## Components

| Piece | Module | Authority |
| --- | --- | --- |
| Hermes transport (OpenAI Responses API) | `serene/adapters/hermes/transport.py` | none; transport only |
| Wire contract `serene-hermes-wire/1` | `serene/adapters/hermes/wire.py` | shape only; refs resolved by the adapter |
| `HermesAgentRuntime` (`AgentRuntime` + `EvidencePlanner`) | `serene/adapters/hermes/runtime.py` | proposals only |
| Kernel boundary | `serene/investigation/boundary.py` | stamps the AGENT actor; ledger admission decides |
| Context retrieval (EXPERIENCE / MEMORY / BELIEF) | `serene/investigation/context.py` | read-only; unverified/rejected evidence withheld |
| Minimum Sufficient Childhood Data | `serene/investigation/minimum_data.py` | deterministic selection of ≤1 observation |
| Investigation controller | `serene/investigation/service.py` | phase moves are events admission re-checks |
| Ingestion | `serene/evidence/ingestion.py` | raw first, structured second |
| Bounded browser | `serene/adapters/browser/hermes_browser.py` | acquires UNVERIFIED evidence only |
| Independent verifier | `serene/evidence/verifier.py` (+ `adapters/browser/fetch.py`) | only path to VERIFIED |
| Evidence service | `serene/evidence/service.py` | appends acquisitions (SYSTEM) and verdicts (VERIFIER) |
| Telegram ingress / prompts | `serene/adapters/telegram/` | mints `ChannelReceipt`; never decides |
| Assembly / server | `serene/investigation/assembly.py`, `app/telegram/webhook_server.py` | wiring; fails closed |

The kernel (`domain`, `policies`, `projections`, `ports`, `ledger`, `lineage`,
`observability`) imports none of these (`tests/test_architecture_boundaries.py`).

## Events added by branch A

All additive; migration `supabase/migrations/20261012090000_runtime_investigation_events.sql`
regenerates the full `event_type` constraint (it sorts after #64's
`20261011090000`/`20261011120000`, so it is the definition in force).

| Event | Actor | Meaning |
| --- | --- | --- |
| `OBSERVATION_STRUCTURING_FAILED` | SYSTEM | structuring attempt *n* failed; raw evidence untouched |
| `EVIDENCE_ACQUISITION_FAILED` | SYSTEM | browse attempt *n* failed (`TRANSIENT`, `MALFORMED`, `NOT_FOUND`, `BLOCKED`, `BUDGET_EXHAUSTED`), `retryable` |
| `INVESTIGATION_PHASE_CHANGED` | SYSTEM / POLICY | phase machine move with reason codes |

Additive fields: `EvidenceRequested.{acquisition_mode, question, subject,
allowed_domains, max_age_days, predictions}`, `ObservationReported.request_id`
(micro-answers), `VerificationCheck.PROVENANCE_VALID`,
`EvidenceBrowseRequest.{subject, max_age_days}`, `EvidenceBrowseResult.reason_codes`.

Admission (additive cases in `serene/policies/admission.py`, rules in
`policies/investigation.py` and `policies/external_evidence.py`): answers must
match an open ASK_PARENT request; acquisitions an open BROWSE request on an
allowed domain; EVIDENCE_VERIFIED for external evidence needs all six checks,
a consistent digest and an allowlisted source, recomputed from the ledger; attempt
numbers must be consecutive; phase moves must follow `PHASE_TRANSITIONS` with
their ledger guards; no new hypotheses in a terminal investigation.

## Evidence acquisition and verification

**Selection.** The model suggests candidates (fields, a yes/no question or browse
bounds, and per-hypothesis predictions). The policy computes everything else:
ordinal information value (HIGH = live hypotheses predict different answers,
MEDIUM = one predicts, LOW = never asked), then lexicographic priority
`safety > evidence need > value > burden > latency > cost > id`. Cost cannot
outrank safety, need or value. Already-requested fields are never asked again.

**Browser bounds** come from the ledger's `EVIDENCE_REQUESTED`, never the model.
After the Hermes run the adapter audits every executed tool call: only
`web_search`, `web_extract`, `browser_navigate`, `browser_snapshot`,
`browser_scroll`, `browser_back`; every URL https on the allowlist; at most
`max_actions` calls. Any violation discards the whole run. Captures must be on
the allowlist and opened by a tool; they become UNVERIFIED L0 evidence in the
canonical `serene-capture/1` text, digest-bound.

**Verifier checks** (all required for VERIFIED; otherwise REJECTED with reasons):
`SOURCE_ALLOWED`, `DIGEST_MATCHES`, `SUBJECT_MATCHES`, `EFFECTIVE_DATE_VALID`
(not future, within `max_age_days`), `REQUESTED_FIELDS_PRESENT` (each value must
appear in the excerpt), `PROVENANCE_VALID` (browser-acquired, URI matches, and the
excerpt is present in the verifier's **own** re-fetch). The fetcher allows
https/443 only, requires every resolved address to be public, pins the socket to
the vetted address with SNI and certificate checks, refuses redirects and caps bytes.
Without a fetcher the verifier fails closed (`REFETCH_UNAVAILABLE`).

## Failure handling

| Failure | Handling | Visible as |
| --- | --- | --- |
| Hermes transport TRANSIENT | 1 bounded retry, then FAILED | `runtime.call` / `browser.call` `retryable` |
| Hermes AUTH / PROTOCOL / REFUSED | no retry; run fails closed | `runtime.run` `reason_codes` |
| Hermes provider failure (HTTP 200, `completed`, zero usage, one warning line) | classified by the transport as AUTH / TRANSIENT / PROTOCOL, never read as model output | `runtime.call error_type`, `TRANSPORT_AUTH` |
| Malformed model output | one repair naming each failing field by schema location, validation type and schema bound, never model text (reasoning); browse: attempt counted as MALFORMED | `WIRE_*` codes, `runtime.run validation_issues` |
| Model executed a tool while reasoning | whole run discarded | `TOOLS_NOT_PERMITTED` |
| Browse TRANSIENT/MALFORMED | ledger-counted retry (default 3 attempts), next scheduler tick | `EVIDENCE_ACQUISITION_FAILED retryable=true` |
| Browse BLOCKED/NOT_FOUND/BUDGET_EXHAUSTED | request exhausted; back to NEEDS_EVIDENCE | `retryable=false` |
| Browse while the model runtime refuses service (AUTH/REFUSED/PROTOCOL) | `UNAVAILABLE`, not retried | `retryable=false` |
| Verifier error / unsupported page | evidence REJECTED; never used | `EVIDENCE_REJECTED` |
| Planner unavailable | PARKED_UNRESOLVED (never "sufficient") | `PLANNER_UNAVAILABLE` |
| Parent silent past 48 h | PARKED_UNRESOLVED | `PARENT_NO_RESPONSE` |
| Process restart | state rebuilt from the ledger; budgets counted from events, never reset; open browse resumes, answered requests are never re-dispatched | replay |

## Telegram

Webhook secret compared in constant time; unbound senders, groups and bots are
ignored; Telegram ids never reach the ledger. Typed text, including "approve",
is always only an observation. A button tap becomes `APPROVAL_GRANTED/REJECTED`
only if the one-time token, user, chat, message and shown intervention digest
all match. The `ChannelReceipt.message_ref` is `tg-callback:<callback_query_id>`:
unique per tap and stable when Telegram redelivers the same update, which is what
#64's `(channel, message_ref)` replay key needs. A refusal burns the token,
except `AMBER_DELIBERATION_TOO_SHORT`, which a later tap can overcome.

## Running against the installed Hermes

The adapter talks to Hermes's OpenAI-compatible API server (`POST /v1/responses`),
verified against hermes-agent v0.21.6 (`tests/test_hermes_transport.py`). The
Hermes API server must be enabled in Hermes's own `.env` (`API_SERVER_KEY` of at
least 16 characters; default port 8642), then:

```
HERMES_API_BASE_URL=http://127.0.0.1:8642/v1
HERMES_API_SERVER_KEY=<same key>
SERENE_BROWSER_ALLOWED_DOMAINS=example.org
uv run python app/telegram/webhook_server.py --port 8787
```

The server refuses to start without the ledger URL, webhook secret, bindings and
Hermes key. Hermes must not poll the same bot whose webhook Serene serves.

## Evaluation (#42, #43, #48–#50)

* Scenarios: `eval/scenarios/runtime_scenarios.py` (6 visible dev scenarios:
  ask, verified browse, unsupported page, flaky browser + restart, silent parent,
  planner down). Production stack, scripted model wire, synthetic family, fake web.
* Scorers: `eval/scorers/runtime_scorers.py`, deterministic, against a
  grader-only `Oracle`; exposure manifest `RUNTIME_EXPOSURE_MANIFEST`; a test
  proves no oracle text reaches any prompt.
* Baselines: `eval/baselines/runtime_baselines.py` (A plain Hermes, B + memory/RAG),
  same transport/browser/parent and `MatchedBudget.from_serene()`.
* `uv run inspect eval eval/tasks/runtime_investigation.py --model mockllm/model`. CI runs
  it with the kernel and trust tasks and `scripts/inspect_gate.py` fails the job unless
  every sample of all three is CORRECT (`inspect eval` alone exits 0 on INCORRECT).
* The model-facing reply schema is rendered from the wire models
  (`propose_contract`, `plan_contract` in `serene/adapters/hermes/wire.py`): exact enum
  values, list/length bounds, and only the proposal kinds the task admits. The schema
  itself is unchanged and strict; `tests/fixtures/live_rejected_proposals.json` keeps
  the live replies it rejected as regressions.
* Live runs: `eval/scenarios/runtime_live.py` + `eval/runners/runtime_live_compare.py --label <x>`
  run the same six scenarios with every model call sent to the Hermes API server (no
  scripted replies) for Serene and both baselines: one simulated parent (`ParentSim`,
  runtime-visible facts only), the same injected environment faults, and one
  synthetic evidence page (`eval/fixtures/pages/`) read from its immutable
  raw.githubusercontent.com URL at a pinned commit SHA (`LIVE_SOURCES`, tag
  `eval-live-pages-v1`). The planner and every browser are told that URL as
  `pinned_sources`; a browse touching any other URL is BLOCKED (`URL_NOT_PINNED`)
  and the verifier re-fetches nothing else. Each run keeps the raw exchanges, the redacted trace and the
  scorer rows under `eval/reports/local/live/`, and sends the trace to neatlogs when
  `NEATLOGS_API_KEY` is set through the committed `NeatlogsSink` (batches under the
  ~8 KiB ingest body limit, one session id per run, an explicit flush report per run
  in `scores.json`). Metric columns name exactly what they count: runtime-scorer
  findings by their own names, `#47` epistemic errors (merged trust scorers) on every
  system's final claim, `#46` authority violations on Serene's ledger only (`n/a`
  for the ledger-less baselines), and verified/used evidence as a count (`n/a` when
  nothing was used, never a vacuous 1.00). `eval/runners/browse_prompt_ab.py` replays recorded
  browse requests live under two prompts. Measured results:
  [live-eval-2026-10-10.md](live-eval-2026-10-10.md),
  [live-eval-2026-10-11.md](live-eval-2026-10-11.md).
* `uv run python eval/runners/runtime_compare.py` writes
  `eval/reports/local/runtime_compare.json`. Baseline rows are `UNAVAILABLE` until
  a live Hermes API server is configured: scripted baseline replies would be an
  invented baseline, so no comparison is claimed from them.

## Observability

`SafeTelemetry` is the only path to the trace sink: allow-listed keys, token-only
values, HMAC-pseudonymized child ids, failure-isolated. Events: `telegram.update`,
`ingest.raw/structured`, `runtime.call/run/plan`, `boundary.run/proposal`,
`context.retrieve`, `evidence.select/requested/acquired/acquisition_failed/verdict`,
`browser.call/acquire` (tool names and hosts only), `investigation.*`,
`ledger.append`. `tests/test_runtime_tracing.py` checks coverage per #52 dimension
and that no report text, page text, URL path, child id or question reaches a trace.
