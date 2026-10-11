# live-gate/5: pipe-safe identity and permit-bound SDK receipts

This is an eval-only successor to immutable live-gate/4. Historical records remain:
original #67 DEV **FAIL**, paired replay **INCONCLUSIVE**, live-gate/3 **INVALID**,
and live-gate/4 **INVALID**. None is rerun, replaced, or reinterpreted. #67/#69,
scorer v2, oracles, holdout, and all v3/v4 protocol, manifest, archive and result
bytes remain unchanged. This PR authorizes no live execution or holdout.

Implementation candidate, committed before the manifest:
`0997773a1cba128de716bd8e09289275ff5758c5`.
Canonical manifest digest:
`027cbb8d74b5355cb9ee0691f0fda404cf0a109dc1a5fbec6d121c28d3e546b1`.
The canonical digest excludes only `manifest_sha256`. Its companion `.sha256`
anchors the manifest; each implementation blob is checked against the earlier
commit. The installation/config/internal-bridge fixtures are byte copies of v4.

## The two harness corrections

1. Package identity invoked `git ls-files -z` and `git diff --quiet HEAD --`
   with inherited stdin. After startup, the gateway has a pending private-pipe
   stdin read in another thread. On Windows this can deadlock Git subprocess
   creation before any SDK call. Both commands now use `stdin=DEVNULL`, a
   10-second timeout, no stderr capture, and stdout capture only for the inventory.
   Timeout, launch and nonzero failures become deterministic `IDENTITY_GIT_*`
   refusals without command output or exception messages. Tests reproduce the
   inherited-pipe deadlock for both commands and prove both fixed calls complete.
2. `/v1/responses` does not use incoming `X-Hermes-Session-Id` as the agent
   session. Pinned Hermes chooses previous-response chain, then declared session
   key, then a new generated session. A receipt lookup using the caller's
   diagnostic session therefore cannot identify this request's SDK send. V5
   creates a one-use permit before HTTP dispatch, verifies it at admission, and
   writes and collects the SDK receipt using that same permit. The generated
   Hermes session is recorded and checked for freshness; it is not the key.

The permit binds canonical outer body, protocol request and complete envelope
digests, manifest/prefix digests, tape/pair, arm and attempt ordinal. Admission
consumes its private-pipe snapshot before the Responses handler runs. A permit
cannot be re-attested, rebound, dispatched twice or collected twice.

Each request has explicit provider/model/high reasoning and `store=false`.
Neither `previous_response_id` nor a declared conversation/session key is admitted.
Neither Hermes session header is sent. No session, profile or model state is
imported. The original protocol session reference remains inside the envelope
binding only.

At agent creation the permit is associated with the actual generated session,
including the adapter's executor-thread handoff. Pinned Hermes uses request-local
chat clients for actual sends. The same guard is attached to those clients and
the primary client; it validates the actual sending client's identity, route,
reasoning, payload and zero SDK retries. Unbound auxiliary/provider I/O remains
blocked. No Hermes source is patched or copied.

After HTTP completion, including an HTTP error, the caller requires exactly one
receipt for the attested permit. Missing, wrong, duplicate, rebound or mismatched
receipts refuse the attempt. The receipt contains the permit, PID/config identity,
provider/model/high reasoning, max turns, nonempty fresh generated session, and
serialized SDK payload hash. It contains no prompt, credentials, provider error
text or raw family data. A second send marks the permit invalid before outbound
I/O. Frozen product transport retries still create separately recorded attempts.

## Unchanged evaluation

All 36 tapes and their committed order, exact shared-prefix rules, A-then-B suffix
order, one suffix per arm/tape, no favorable reruns or replacements, scorer/oracle
identities, evidence/investigation/cost thresholds, safe NeatLogs requirements and
INVALID precedence are carried forward from v4. Tests compare the decision and
completed-pair functions' ASTs directly to v4. Protocol/worker/metrics/coordinator
changes are version/import/path changes only.

A: `8fac1cbcf3780677e6b6638238abb5ea8e7d46a7`.
B/#67: `41d3bf60daf591b8dc8fe0c18cd0a30d18b80aa2`.

Hermes remains base **0.21.6**, display **0.21.6+509.gf925b01**, source
`f925b01791fe052e7d55dc975750c0bd985aff91`, with the same pinned interpreter,
installation stamp, source inventory and dependency RECORD identities. It runs
only as a fresh experiment-owned child/home/state/session store on
**127.0.0.1:18642**, provider **opencode-go**, model **deepseek-v4.1-flash**,
reasoning **high**, max turns **500**, no fallback or inherited routing overrides.
The user daemon is never discovered or used.

Local process/config/request/SDK checks retain v4's assurance limits. They do not
attest the OS, every dependency binary, remote provider defaults, sampling
internals or remote determinism. No temperature or seed is sent. Remote
nondeterminism is not evidence of local configuration drift.

## Offline boundary proof

Before the implementation commit, the real installed Responses route received
the exact Tape-1/Arm-A pending request reconstructed through shared-prefix replay,
then a minimal synthetic request. Each used a pre-admitted permit, placeholder
credential and blocked provider network. Each reached the actual guarded SDK
serialization/send boundary, wrote exactly one permit-bound receipt, and denied
outbound I/O. Only after writing that receipt, offline mode invoked Hermes'
normal interrupt path to prevent recovery sends. No provider response was mocked.

Both local HTTP requests completed with status 200 and the owned process alive.
That status describes local interrupted handling, not model or task success.
The exact outer request digest was
`ad50e4a4eb2844535e6778cd77fab6f24007cf4caa0ca651fcc5c3089776ee03`.
The two generated session IDs were distinct. The archived allowlisted receipts
contain no input text, keys or response/error bodies. These diagnostics are not
evaluation samples and require no NeatLogs delivery.

The offline-only probe requires explicit installation and source-tape paths:

```text
uv run python -m eval.runners.live_gate5_probe
  --installation-root <installed-hermes> --python <installed-base-python>
  --site-packages <installed-dependency-site-packages>
  --arm-a <clean-detached-A> --arm-b <clean-detached-B>
  --tape-root <frozen-source-tapes> --out <new-diagnostic-directory>
```

The [verification record](../eval/reports/archive/2026-10-11-live-gate-v5/verification.json)
records the deterministic checks and safe diagnostic receipts. All 36 offline
tapes reproduced v4's prefix hashes and boundaries: 30 first divergences and
6 no-divergence completions, with zero live calls. Offline replay stops at
divergence and makes no new product evaluation claim.

V5 is technically prepared for one separately authorized fresh live evaluation.
There is no v5 live verdict, holdout eligibility, holdout run or automatic merge.
