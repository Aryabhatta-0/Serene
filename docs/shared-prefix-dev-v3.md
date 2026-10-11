# Sampling-controlled DEV protocol: live-gate/3

Status: eval-only protocol with a separately frozen sampling/decision contract in
[`shared-prefix-dev-v3-decision.md`](shared-prefix-dev-v3-decision.md). No live
experiment or holdout is authorized by this document. PR #67's product code is
unchanged. Its historical 36-run DEV experiment remains **FAIL** permanently.
This version does not reinterpret or overwrite that decision or
`frozen-regression-gate/2`. `runtime-scorers/2`, `trust-scorers/1`, oracles, prompts,
scenario fixtures, verifier rules and policy code remain unchanged.

## Estimand and tape selection

The comparison asks what changes when policy code changes **conditional on an
identical recorded upstream prefix**. It does not estimate an unconditional
live-model success rate and cannot remove downstream live sampling noise.

`eval/fixtures/shared-prefix-dev-v3.json` freezes all 36 run identities from
`pr67-ab-20261011`, selected only by original identity/index. This is a documented
fixed source study, not a search of all studies or a filter on scores. Ordering is
repetition 1,2,3 -> committed six DEV scenario order -> source A,B. Each tape
creates a new paired A/B run; source A/B is tape provenance, not evaluation arm.
There are six tape blocks per scenario, including unfavorable initial hypotheses.
Any invalid/incomplete tape refuses the whole set; it is never silently excluded.
No score, retention label, rejection, terminal outcome or apparent benefit affects
selection. File hashes pin the complete raw exchanges, source manifest and scores.

Two source tapes from the same historical repetition are not paired measurements
of one original model sample. Reusing a tape or repeating its suffix does not create
independent upstream replicates. Report every tape and downstream repetition,
raw values, descriptive medians and categorical counts/rates; no significance
claims. The fresh experiment freezes one suffix per divergent arm/tape in the
separate experiment manifest, before results.

## Freeze and identity checks

Use clean detached worktrees at current main (A) and the exact #67 head (B).
The implementation preflight used:

- A: `8fac1cbcf3780677e6b6638238abb5ea8e7d46a7`
- B: `41d3bf60daf591b8dc8fe0c18cd0a30d18b80aa2`

Only `serene/investigation/minimum_data.py` and `service.py` may differ under
`serene/`. All other tracked product files, the runtime harness, prompts, pinned
page, parent simulator, budgets, fault/retry handling and scorers must have equal
hashes/configuration. The two policy files must differ. Non-runtime web-shell
differences between main and #67 do not enter the experiment.

Before any comparison, validate all 36 tapes: consecutive sequence numbers,
complete replies/usage/tool calls, terminal source manifest, clean source SHA,
Serene-only DEV identity, exchange count, matching budget/prompt/page identities,
scorer `runtime-scorers/2`, trust scorer `trust-scorers/1`, and matching grader-only
oracle digest. No oracle is passed into model inputs. The new manifest pins
protocol implementation hashes, catalog hash, all oracle digests, both SHAs,
runtime/protected-file hashes, tape IDs and original file hashes. Every pair result
includes protocol/scorer/trust versions, oracle digest, SHAs, tape ID/hashes,
manifest hash and immutable prefix-chain hash. A changed manifest, implementation,
catalog, worktree or source tape refuses replay. Missing metadata is an error.

## Exact replay and causal-divergence rules

1. Start isolated A/B processes with the same deterministic synthetic state and
   unchanged runtime driver. Verifier page fetches read the SHA-pinned git object
   locally. The workers have no model provider and do not export telemetry.
2. At each next model call, block both arms before either can receive a reply.
   Compare the actual instruction text, input text, purpose and session header.
   UTF-8 content is exact: no trimming, parsing/reformatting of input JSON, or
   whitespace normalization. A/B actual instruction text must match; its SHA must
   also match the legacy recorder's instruction SHA. Equal hashes alone never
   replace the A/B byte comparison.
3. While model inputs agree, require both to match the next sealed
   tape request. A reply is bound to sequence + request + response/error, with an
   immutable binding hash. Validate both requests and the binding before releasing
   the same reply to either arm. Record a hash-chained shared-prefix receipt.
   Unchanged harness-injected faults are re-injected, not replayed twice.
   A permitted policy output may already differ even though the next model input
   is identical. Record that earliest output witness immediately and continue
   exact-input replay. Preserve its ledger prefix and both first output events at
   all subsequent boundaries. Record its ordinal separately from the later first
   different model input; it must never be silently replaced by a later witness.
4. At the first different next input, release **no recorded reply to either arm**.
   Require a common ledger prefix whose first different output is an
   `EVIDENCE_REQUESTED` policy decision (different payload), or policy-driven
   `INVESTIGATION_PHASE_CHANGED` with `NO_ADMISSIBLE_EVIDENCE`. Require selection
   witnesses from `minimum-sufficient-data/1` in A and `/2` in B. Equal source and
   runtime hashes plus the two-file product allowlist make this a policy witness;
   different model inputs alone never establish causality.
5. At least one next input must still match the next original source-tape input.
   If the tape has ended, one arm must have terminated. Terminal-vs-request and
   terminal output differences require the same policy witness. Otherwise fail
   closed as drift. Record both pending inputs, next ordinal, source tape position,
   matched source arm(s), common ledger hash/length, first policy outputs, selection
   witnesses and prefix-chain hash. Neither a different hypothesis reply nor an
   arbitrary ledger/input difference is labeled policy-induced.
6. State drift without a permitted policy witness fails closed, including while
   next inputs remain identical. Changing an already recorded first policy output
   or its common ledger history also fails closed. Input drift before a permitted
   policy output, wrong prompt/session, tape exhaustion at an ordinary call,
   incomplete reply, unsupported metadata or version mismatch is `INVALID`.
   Both identical terminal states require the full tape to have been consumed;
   then record `no_divergence`. A first policy output difference at termination is
   recorded even if neither arm asks another model question.

`first_policy_divergence` and `no_divergence` are protocol statuses, **not PASS**.
`INVALID` stops the experiment and preserves the failed pair's receipts.

## Optional downstream live continuation

The CLI intentionally supports only offline freeze/replay. A future explicitly
authorized live experiment can use `FrozenContinuation` + `continue_pair` with
the existing Hermes provider and NeatLogs path. No credentials are serialized.
Provider/model/config-file digest, timeout/retry settings, budget and
telemetry path are pinned in the separate experiment manifest **before replay**. The provider is
one object shared by both arms, receives only its own pending model request
(never an arm label), and must revalidate the frozen configuration before every
call. Workers retain the same already-spent virtual prefix budget; budgets are
not reset at divergence. A provider or telemetry adapter must record every live
attempt independently, including infrastructure failures; never rerun an
unfavorable suffix. Continuation completes A's entire suffix, then B's entire
suffix, once each per tape in catalog order. There is no live CLI flag to enable accidentally.

Live continuation cannot access the source-tape queue. Each reply is bound to
its own input before dispatch, copied into an append-only separate journal, and
references the sealed prefix hash. Provider mutations cannot alter recorded
requests. Each subsequent ledger must retain the entire previous boundary ledger
byte-for-byte. A completed trajectory is rescored with unchanged v2 and checked
against the worker's scores. A partial suffix remains incomplete, never zero-valued
or silently treated as success. Persist prefix checkpoints exclusively (`write_new`)
before starting a suffix, then persist suffix records in separate files; no
overwrite of prefix or historical result files is permitted.

`shared_prefix_metrics.downstream` reports full v2 scores for audit and metrics
after the first different policy output (the ledger cut, which can precede the
different model call): request field counts, unique unsupported/evaluated captures,
reason-code counts, verifier outcomes, VERIFIED captures, high_value, resolution,
burden, parent outcomes, terminal state, false completions, full authority/epistemic
findings, calls/tokens and transport infrastructure failures. Pre-divergence
hypotheses are identical within each pair and cannot be attributed as a policy
regression. Upstream retention failures remain visible in full v2, not erased.
Burden retains prior acquisition context so repeated/already-settled questions
remain unnecessary. Null capture denominators stay null. Virtual replay resource
use and actual downstream provider calls must be reported separately.

No fresh evaluation decision has been made. Prefix-only replay cannot establish
DEV PASS or holdout eligibility. The committed experiment manifest freezes the
fresh run's sample/configuration/decision rule. Its completed decision is PASS or
FAIL; invalid protocol/infrastructure state is INVALID/STOP. Neither a future pass nor this protocol changes the
historical FAIL. Holdout still requires explicit approval.

## Commands and permanent historical record

From this eval branch, with both product worktrees clean and source tapes available
outside committed code:

```powershell
uv run python -m eval.runners.shared_prefix_compare freeze `
  --arm-a <clean-main-worktree> --arm-b <clean-pr67-worktree> `
  --tape-root <pr67-ab-20261011> --manifest <new-manifest.json>
uv run python -m eval.runners.shared_prefix_compare replay `
  --arm-a <clean-main-worktree> --arm-b <clean-pr67-worktree> `
  --tape-root <pr67-ab-20261011> --manifest <new-manifest.json> --out <new-directory>
```

The raw tapes stay local; the committed catalog retains their hashes. Keep new
results under ignored `eval/reports/local/`, never committed product code. Only
synthetic DEV fixtures enter the harness. Do not load real family data or secrets
into reports/telemetry. There is no holdout or baseline runner in this protocol.

`eval/reports/archive/2026-10-11-pr67-dev-ab-fail/` preserves the original summary,
report, rule/protocol, all 36 CSV rows, NeatLogs IDs and attribution/integrity files
byte-for-byte with checksums. Added `score-inputs.json` holds all 36 original
synthetic trajectories and scores for deterministic v2 reproduction. Archive
attributes preserve historical bytes across platforms. Tests rescore all 36,
reapply the original consistent-regression clause, and assert the original FAIL.

Protocol tests also exercise identical prefix delivery, first-input divergence,
terminal divergence, both-arm barrier, request/reply binding, incomplete tapes,
outcome-blind selection, runtime/version mismatch, immutable continuation and
burden context. Full deterministic verification includes the repository's existing
tests, lint/types, ledger/secret checks and three scripted Inspect tasks.

Final offline verification is archived in
`eval/reports/archive/2026-10-11-shared-prefix-dev-v3/`: frozen manifest and all 36
compact pair records (30 policy-induced model-input divergences; six no-divergence
completions). No invalid pairs, no live model calls and no fresh DEV verdict.
Full receipts stay under ignored `eval/reports/local/prefix-final-verification/`,
with hashes retained in the committed verification record. Full pytest passed
799 tests; the final focused protocol suite passed 33 tests, including the last
continuation-boundary guard added after full-suite collection. All 20 scripted
Inspect samples, lint, formatting, types, ledger/secret checks and web build/type
checks passed. Web E2E passed 29 tests with one existing skip after installing
the missing pinned Chromium binary. That record describes the initial protocol
commit. The separate sampling/decision manifest now freezes the fresh evaluation;
it does not rewrite this historical offline verification or authorize live calls.
