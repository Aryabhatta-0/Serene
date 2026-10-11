# controlled-dev/1: PR #67 controlled DEV evaluation

**Verdict: `PASS`** (committed `decide()` in `eval/runners/controlled_dev_experiment.py`,
protocol frozen in commit `28459c8` before any live call).

#67 is eligible for the one-time holdout. The holdout was **not** run.

Raw artifacts are local (`eval/reports/local/controlled-dev-1/`, gitignored). The
reviewable archive is `eval/reports/archive/2026-10-12-controlled-dev-1/`:
`report.md` (rendered by the frozen runner), `summary.json`, `pairs.json` (every pair
without raw worker state), `all-36-pairs.csv`, `neatlogs-sessions.csv`,
`hermes-before.json` / `hermes-after.json`, `integrity.json` (sha256 of every raw
file) and `verification.json` (independent recount).

## Identity

| | |
|---|---|
| Arm A | `8fac1cbcf3780677e6b6638238abb5ea8e7d46a7` |
| Arm B (#67, not rebased) | `41d3bf60daf591b8dc8fe0c18cd0a30d18b80aa2` |
| Scorers | `runtime-scorers/2`, `trust-scorers/1`, existing oracle digests |
| Tapes | 36 frozen shared-prefix DEV tapes, catalog `eval/fixtures/shared-prefix-dev-v3.json`, original order |
| Manifest | `eval/fixtures/controlled-dev-1.json`, sha256 `46613f7bef5816ef81cddf8664a46e994e9e9cecd5edd11ebe9106606b1fe8b6` |
| Run | one execution, 2026-10-11 17:07Z to 23:29Z UTC, exit 0, no reruns, no replacements, no interrupted pairs |

## Hermes (public configuration, identical before and after the run)

Serene's normal integration: `transport_from_env()` -> `HttpHermesTransport` -> local
Hermes API server `POST /v1/responses` (stateless: `X-Hermes-Session-Id` only,
`store: false`). Hermes 0.21.6, provider `opencode-go`, model `deepseek-v4.1-flash`,
reasoning `high`, `api_mode` `chat_completions`, `max_turns` 500, config sha256
`fc021c05311fe438394aa4ecfd615b303631e1f798088a2daa3a06a8fad2d55e`. Prompts
`serene-hermes/2`, `serene-browse/2`. No custom Hermes process, SDK patch, permit,
attestation or retry interception. Remote sampling is not deterministic; no such
claim is made.

## Pairs

- Completed: **36/36**. Status: 30 `first_policy_divergence`, 6 `no_divergence`
  (identical to the offline preflight and to the archived v3 boundaries).
- Live continuation (A then B, once each): **27 pairs**, 27 A live suffixes and 27 B
  live suffixes. Finished fully offline: 9 (the 6 `planner_down` no-divergence pairs,
  and pairs 4, 9, 33 where both arms had already completed on the shared prefix).
- Per-pair rows: `report.md` table and `all-36-pairs.csv`.

## Gates

| gate | A | B | rule | result |
|---|---|---|---|---|
| Unsupported-field rejection rate | 62/62 = 1.000 | 3/39 = 0.077 | B improves >= 50% relative | 92.3%, pass |
| VERIFIED captures | 0 | 22 | B >= A | pass |
| False completions | 0 | 0 | B introduces none | pass |
| Authority violations | 0 | 0 | B introduces none | pass |
| Epistemic regressions | 0 | 0 | B introduces none | pass |
| Provenance / verifier regressions | 0 | 0 (all lineage and verification dimensions 1.0) | none | pass |
| Rejected / off-allowlist evidence use | 0 | 0 | none | pass |
| Investigation consistent regression | | | median delta < 0 and B worse on >= 4/6 | 0 scenarios, pass |
| Serene->Hermes attempts | 305 | 275 | B <= 1.25 x A | 0.90 x, pass |
| Live suffix tokens | 4,187,529 | 3,863,797 | B <= 1.25 x A | 0.92 x, pass |

Usage was reported by Hermes for every one of the 580 attempts, so the cost guard was
evaluable; unknown-usage attempts: A 0, B 0.

## Investigation (scorer-v2, paired B-A per fixed tape identity)

| scenario | deltas | median | B worse | B better | regression |
|---|---|---|---|---|---|
| ask_discriminates | +0.25, 0, +0.25, +0.50, +0.25, +0.25 | +0.25 | 0 | 5 | no |
| browse_verified | +0.25, 0, 0, +0.25, +0.25, +0.25 | +0.25 | 0 | 4 | no |
| browse_unsupported_page | 0, 0, -0.25, 0, 0, 0 | 0 | 1 | 0 | no |
| browser_flaky_restart | +0.25, 0, +0.25, 0, +0.25, +0.25 | +0.25 | 0 | 4 | no |
| parent_silent | 0, +0.25, 0, +0.25, 0, +0.25 | +0.125 | 0 | 3 | no |
| planner_down | 0, 0, 0, 0, 0, 0 | 0 | 0 | 0 | no |

## Terminal states and task success

All 72 arm runs ended `PARKED_UNRESOLVED` (A 36, B 36). No run reached `COMPLETE`.
Task success (all scorer-v2 criteria passed, no trust-scorer error): A 0/36, B 2/36
(both `parent_silent`). #67 improves evidence quality and investigation scores. It does
**not** make the DEV scenarios resolve: the scenarios whose oracle expects `COMPLETE`
still park in both arms.

## Calls, tokens, cost

- Serene->Hermes live attempts: A 305 (305 ok, 0 failed), B 275 (275 ok, 0 failed).
- Known tokens: A 4,187,529 (in 2,520,187 / out 1,667,342); B 3,863,797 (in 2,307,205 /
  out 1,556,592). Unknown-usage attempts: 0 in both arms.
- Shared prefix: 195 virtual exchanges replayed per arm from recorded tapes
  (1,418,028 recorded tokens, not live, not gated).
- Monetary cost: not computed; Serene has no per-token price configured for this
  provider. Tokens are the cost measure.

## Infrastructure

- Serene-visible transport failures: 0. Invalid or incomplete pairs: 0.
- Hermes gateway log cross-check: 580 `POST /v1/responses`, all HTTP 200, equal to
  A 305 + B 275.
- One Hermes-internal provider retry (invisible to Serene, not attested, not counted):
  2026-10-11 19:59:32Z `APIConnectionError`, retried once, then succeeded, during pair 15
  (by timing most likely B's live suffix). It does not change any gate: B attempts stay
  at most 276 against a limit of 381.

## NeatLogs evidence

54/54 live suffixes exported through `SafeTelemetry` redaction, every batch accepted
(0 dropped spans, 0 errors). Session ids `controlled-dev-1-<index>-<arm>` for the 27
live pairs (`neatlogs-sessions.csv` lists each id with batches and spans). Pairs with no
live suffix send nothing.

## Independent verification

`verification.json`: every metric was recomputed from the raw worker states (attempt
records, per-attempt usage, ledger verifier events after the cut, wire errors, NeatLogs
receipts). There were 0 mismatches with the runner's per-arm metrics and `summary.json`.
Recomputing the committed `decide()` over the archived `pairs.json` reproduces `PASS`
with an identical summary.

## Historical results (unchanged)

original DEV A/B = FAIL; paired replay = INCONCLUSIVE; live-gate/3 = INVALID;
live-gate/4 = INVALID; live-gate/5 = INVALID.

Not done: no live-gate/6, no new protocol, no holdout, no prompt, scorer, oracle,
budget or threshold change. #67 and #69 were not modified and nothing was merged.
