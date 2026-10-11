# live-gate/4: experiment-owned Hermes

Eval-only. No live execution or holdout is authorized by this PR. Historical #67
DEV remains **FAIL** and its attempted live-gate/3 run remains permanently
**INVALID**. Nothing in v3, its manifest, archives, rule, or result is replaced.
#67/#69 product code, scorer v2, trust scorer, and holdout are unchanged.

## Frozen comparison

`eval/fixtures/shared-prefix-dev-v4-experiment.json` is the new experiment identity.
Its canonical SHA excludes only `manifest_sha256`; the companion `.sha256` is the
anchor. The implementation commit precedes the manifest commit to avoid a circular
identity. The eight v4 runner files and offline probe are independently hashed.

The v4 catalog differs from v3 only in its protocol version. All 36 tapes, ordering,
source hashes, oracle digests, prompts, budgets, pages, simulator, protected files,
and product SHAs are carried forward. A remains
`8fac1cbcf3780677e6b6638238abb5ea8e7d46a7`; B/#67 remains
`41d3bf60daf591b8dc8fe0c18cd0a30d18b80aa2`.

The v4 protocol/worker/comparison/metrics/decision implementation is separately
versioned, leaving v3 files intact. The decision and completed-pair implementation
are AST-identical to v3; tests enforce this in addition to exercising the original
boundary cases. Exact shared inputs receive the same bound recorded reply until
the first policy-induced model-input divergence. No recorded reply is delivered
after different input. Preserve any earlier first policy-output witness.
No-divergence completes offline with zero live attempts. Continue A's entire suffix,
then B's, once per tape, with already-spent budgets. No favorable reruns, filtering,
replacement suffixes, or holdout. Invalid integrity/infrastructure has priority and
stops the experiment. Safety/provenance rules and all evidence, investigation and
cost thresholds are unchanged; see the immutable v3 decision document for their
full definitions. A future DEV result cannot rewrite historical FAIL or INVALID.

## Runtime ownership and freeze

`OwnedRuntime` accepts installed package/interpreter/dependency paths, **never a
daemon URL**. `start` creates a fresh temporary HERMES_HOME with new state/session
directories, generates credential-free config bytes, and launches the installed
official interpreter directly. The gateway uses the official `APIServerAdapter`
inside an eval-owned bootstrap; it does not start the user's multi-platform daemon.
No source files in the Hermes installation are patched or copied.

The frozen installed identity is Hermes base **0.21.6**, display
**0.21.6+509.gf925b01**, source commit
`f925b01791fe052e7d55dc975750c0bd985aff91`. Pin the actual interpreter binary,
installation stamp, runtime source inventory, and installed dependency RECORD
identities. These are practical package identity checks, not a claim to attest
the operating system or every dependency binary. The bootstrap uses `-I -S`, adds
only the pinned source and dependency paths, ignores editable `.pth` hooks, and
sets the installed dependency environment's prefix explicitly. This avoids the
Windows venv redirector's additional PID. Lazy installs are disabled explicitly;
a changed interpreter, package, dependency selection, or unexpected bootstrap
environment is refused.

`hermes-v4-config.json` holds the exact generated YAML-compatible JSON bytes.
Freeze the SHA, provider `opencode-go`, model `deepseek-v4.1-flash`, provider URL
`https://opencode.ai/zen/go/v1`, `agent.max_turns=500`, reasoning high, provider
request/stale timeouts of 120 seconds, one Hermes API attempt, zero SDK retries,
zero auto-recovery cycles, and no fallback provider. Existing Serene transport,
wire repair, browser, verifier, worker and NeatLogs settings remain frozen in the
manifest. Fixed API bind: **127.0.0.1:18642**; a port conflict refuses startup.

The launch environment is constructed from a closed list of essential OS inputs,
experiment-generated paths/flags, and **only OPENCODE_GO_API_KEY** as the provider
credential. A fresh random API_SERVER_KEY is generated at launch. HOME, USERPROFILE,
APPDATA, LOCALAPPDATA, TEMP and TMP point into the new private home. PATH is built
from explicit interpreter/git locations. No inherited model/provider/reasoning,
max-turn, proxy, Python, gateway or API-server override is accepted, including
legacy HERMES_MAX_ITERATIONS. Other ambient variables are not forwarded.
The official config bridges have a separately frozen public allowlist in
`hermes-v4-internal-bridges.json`; their exact values must match. The only dynamic
session environment value must name an agent created in this process.

Credentials are passed only in the child's launch environment or to the separate
safe telemetry adapter. They are never placed in config, command arguments,
receipts, reports, or archives. Child diagnostics are discarded; failures expose
only safe refusal codes, exception types and source line locations. Temporary
state is removed on close where possible (Windows can briefly retain file locks).
It is never reused as another experiment's home.

## Every request and attempt

`OwnedExperimentProvider` is the only provider accepted by v4 `execute`. The
lower-level `ExperimentProvider` remains a deterministic audit/decision test seam;
an arbitrary observer or provider cannot enter the v4 execution entry point.
There is no live CLI or implicit credential loading.

Before each attempt, including retries, revalidate the anchored manifest, actual
clean product worktrees, protocol/scorer/oracle/protected hashes, and actual safe
NeatLogs adapter settings. The runtime then verifies its owned process is alive,
PID/executable/home/private-pipe nonce identity, package/version, generated config
bytes, and current child environment. It checks the actual listening socket bind.

Every Responses request sends explicit provider and model, and
`model_options={"reasoning":{"enabled":true,"effort":"high"}}`. The official
request decoder must preserve these values. No client temperature or seed is
sent. Each attempt receives a fresh opaque `live-gate4-...` session ID; original
protocol session identities remain in the immutable request binding. No prior
session, previous response, session key, /model setting, or profile is imported.

Attestation uses inherited pipes from the owned child, **not a hypothetical
Hermes endpoint**. The child issues a one-use permit bound to exact body digest
and session before HTTP submission. Its API admits only that exact
`POST /v1/responses`; config, session-model, profile and other mutation routes
are blocked. Config and environment are checked again before resolving the real
agent and at the SDK boundary. Resolved provider/model/base URL/max-turns/reasoning,
timeout, fallback/recovery and SDK retry settings must match. A replacement client,
unbound auxiliary SDK call or changed payload is denied before provider HTTP I/O.
Public SDK send receipts contain hashes/settings only; no authorization headers,
credential values, or prompt bodies.

Successful responses must report the frozen provider/model with `raw_request`
routing, actual usage and a successful safe NeatLogs export. STARTED and runtime
receipts are saved before I/O; SDK receipts and replies are separately saved.
Failures with unknown billed usage are INVALID, never zero-valued or permission
to rerun. Existing durable sample/order/checkpoint controls remain unchanged.

Health, detailed health, config and model-options endpoints are unnecessary. No
health response is described as loaded-config attestation. Ownership, frozen
inputs, actual in-process object checks and the guarded SDK boundary provide the
local execution evidence.

## Assurance and verification limits

The installed runtime can attest the frozen **local** values without trusting a
pre-existing daemon's defaults. The offline probe verifies the real installed
resolver, constructor, request builder, SDK serialization and pre-attempt pipe
handshake using a placeholder credential, blocked outbound sockets and an
in-memory scripted HTTP transport. It submits no live model request, exports no
telemetry and evaluates no holdout. Live conversations remain untested here.

Provider-side sampling defaults are intentionally unspecified and unverified.
This protocol freezes the policy of sending no client temperature/seed; it does
not claim deterministic sampling or attest remote provider internals. Unsupported
reasoning encodings, unexpected environment changes or execution paths fail
closed rather than being silently translated into a different experiment.

Offline startup command (explicit installed paths required):

```text
uv run python -m eval.runners.live_gate4_probe --installation-root <installed-hermes>
  --python <installed-base-python> --site-packages <installed-dependency-site-packages>
```

The command is offline-only and cannot execute the experiment. Prefix freeze and
replay use `python -m eval.runners.live_gate4_compare` with the same offline CLI
arguments as v3, using new v4 manifest/output paths. Never write into v3 locations.

Deterministic tests cover fresh homes/state, inherited overrides, config hashing
and mutation, exact loopback, explicit request options, one-use session isolation,
PID/process mismatch, pre-attempt drift, SDK payload controls, unchanged v3 bytes,
and unchanged decisions. Full verification includes Python tests/lint/types,
ledger/secret checks, all three scripted Inspect tasks, offline 36-tape replay,
and existing web type/build/browser checks. See the new v4 verification record for
actual outcomes; no live verdict is inferred from offline verification.
