# Canonical Maya demo (#56)

Run from the repository root with Python 3.11–3.13, Git and uv:

```sh
uv sync --locked --all-extras --group dev
uv run python scripts/maya_demo.py
```

To restore the exact pre-run state with one command:

```sh
uv run python scripts/demo_reset.py
```

Reset writes the canonical synthetic seed/empty-ledger baseline to
`.demo/maya/seed.json` and removes only the generated `report.json` and
`report.html`. Run the demo command again afterward. Both reset and run are
independent of the working directory, environment credentials and production
databases. There is no database URL, production mode or arbitrary reset target.
Linked workspaces/artifacts (including Windows junctions) are refused; unknown
files such as recordings are preserved. Repeated resets produce identical
baseline bytes. Every run creates a fresh in-memory ledger and throwaway Git
memory repository from this exact seed, so resetting requires no DB edits.
`tests/test_demo_reset.py` proves reset → snapshot → reset → identical snapshot
→ successful full demo, and restores the same baseline again after a run.

Open `.demo/maya/report.html` for the visible sequence and Causal Twin; retain
`.demo/maya/report.json` for exact events, provenance, hashes, prompts, memory
content and the deterministic Git memory receipt. The command prints all 18
beats and a SHA-256 over canonical report JSON. It exits nonzero on failure.
No credentials, Telegram bot, database, external website or model call is needed.

This is **synthetic Maya**, not a real child. The model wire, Telegram sender and
independent public-page read are offline fixtures. Telegram updates enter the
real authenticated `TelegramChannel`; model proposals go through
`HermesAgentRuntime` and `KernelBoundary`; the controller, `HermesBrowser`,
`EvidenceService`, independent verifier, experiment lifecycle, Promotion Gate,
Dream pipeline, Critic, Git Memory Committer and Causal Twin run unchanged.
This proves domain integration, not live Telegram/network/provider availability.
The report viewer displays actual ledger results; it is not a second runtime.

## Exact path

1. Three synthetic Telegram pickup reports become separate raw evidence and
   structured observations on three fixed-clock days.
2. A parent opens the investigation through the existing investigation service.
3. Fatigue, hunger and transition difficulty remain competing hypotheses.
4. Minimum Data policy selects missing snack-response evidence.
5. The parent receives a YES/NO/UNSURE prompt and taps NO on that exact interaction.
6. The controller selects browser acquisition of pickup-notice evidence.
7. Exactly one transient transport failure is injected; it is recorded in the ledger.
8. The scheduler yields `RETRY_SCHEDULED`; the next drive acquires evidence for
   the same request. Adapter-internal retries are disabled for this fixture so
   the failure and retry are visible at the service boundary.
9. Independent verification rejects a plausible-looking excerpt that is absent
   from the pinned synthetic source: `EXCERPT_NOT_ON_SOURCE`.
10. A new request for warning duration acquires the real pinned excerpt. All six
    independent verifier checks pass. The rejected evidence stays rejected.
11. The model proposes one reversible seven-day transition-support experiment:
    a five-minute heads-up. Code classifies it GREEN.
12. The parent taps APPROVE on the exact authenticated prompt; timers start it.
13. Two more Telegram reports describe calm pickups. The existing synthetic
    builder records the parent outcome with their real runtime-created lineage.
14. The lifecycle completes the experiment; the Gate grants 3→4, then 4→5 and
    policy creates a scoped learning with validity/review metadata.
15. Dream records ORIENT→CONSOLIDATE→REFLECT→CHALLENGE→VERIFY→PROPOSE_PATCH.
16. The Critic accepts the scoped learning and the sole Memory Committer writes
    `learnings/maya-pickup.md` to a throwaway real Git memory repository.
17. The Critic rejects “every transition everywhere” derived from one observation:
    `INSUFFICIENT_EVIDENCE:OBSERVATION_BELOW_PATTERN`. No such memory file exists.
18. The ledger-derived Causal Twin changes transition difficulty from CANDIDATE
    to SUPPORTED at level 5; fatigue and hunger stay CANDIDATE at level 3.

The result is a scoped synthetic N-of-1 learning, not a universal causal or
clinical claim. Completion of the investigation does not mean all competing
explanations were disproved. Browser policy text provides context, not proof
of a child's response. Synthetic parent outcomes are the experimental support.

## Reproducibility and judging

```sh
uv run pytest tests/test_maya_demo.py -q
```

The E2E test runs the entire fixture twice in independent Git repositories and
compares **all canonical report bytes**, including the hash-chained ledger,
timestamps, entity IDs, Causal Twin, memory content and Git commit SHA. It also
checks exact failure/recovery request linkage, rejection/verification order,
all six checks, GREEN classification, parent-before-start-before-outcome order,
adjacent promotions, all Dream stages and the accepted/rejected patches.
The normal CI kernel job collects these tests. Frozen evaluation inputs and
scorers are not part of this fixture and are unchanged.

Each command uses a new in-memory ledger and temporary Git memory repository.
Only the JSON and HTML evidence persist in the ignored `.demo/maya/` directory.

## Web recording: canonical demo mode

From the repository root in PowerShell, with Node.js 20+, Python 3.11–3.13,
Git and uv installed:

```powershell
uv sync --locked --all-extras --group dev
uv run python scripts/demo_reset.py
uv run python scripts/maya_demo.py
Set-Location app/web
npm ci
npm run build
$env:SERENE_DEMO_MODE = "1"
npm run start -- --hostname 127.0.0.1 --port 3200
```

Open **http://127.0.0.1:3200/demo/maya**. The page explicitly displays
`DEMO MODE — synthetic Maya scenario`. This is a local, read-only demo adapter,
not the production Supabase/Auth path. Without `SERENE_DEMO_MODE=1` on the
server, the page shows Not Found and its state endpoint returns 404. Keep this recording
server on localhost. The server needs uv and the repository's Python environment.

The page reuses `InvestigationDetail`, `ExperimentsView`, `MemoryView` and
`CausalTwinSurface`. `/demo/maya/state` invokes `scripts/maya_web_state.py`, which
reads only the fixed `.demo/maya/report.json`, validates the canonical report and
its hash chain, and replays its events through the existing read-only projection
and view builders. No extra result fixture, database connection, kernel drive,
model call, or memory write is involved. Browser responses contain validated
views, not the raw report's evidence/actor data. No kernel or demo behaviour changes.

Today shows the final investigation status, the competing explanations,
remaining uncertainty and the policy's next action. Choose an earlier **Recorded
investigation checkpoint** to show missing evidence and its selected source;
these are actual ledger prefixes. The final view retains rejected and verified
evidence with checks and reasons. Experiment shows GREEN classification, the
recorded Telegram parent approval, outcome and both adjacent Gate promotions.
Memory shows the scoped learning, all Dream stages, the committed patch, and the
rejected universal patch with its reason. Causal Twin switches between the
report's before and after snapshots; links open the existing provenance panel.

To regenerate while the server stays running, open another terminal at the
repository root and run:

```powershell
uv run python scripts/demo_reset.py
uv run python scripts/maya_demo.py
```

Click **Reload generated report** (or refresh the page). The artifact modification
receipt changes; the domain SHA-256 remains identical because the canonical
scenario is deterministic. Reload after reset alone shows an unavailable report
and clears previous domain results. Missing, malformed or invalid reports fail
closed. The endpoint and browser fetch both disable caching.

Without authentication, production `/today`, `/investigations`, `/experiments`,
`/memory` and `/causal-twin` retain their honest unconnected state. This demo makes
no authentication or RLS changes.
**#87 (production sign-in/child selection) and #84 (authenticated WEB_APP approval
transport) remain open.** This page cannot submit approval decisions.

Verification:

```powershell
uv run pytest tests/test_maya_web_state.py -q
Set-Location app/web
npm run typecheck
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

The dedicated `maya-demo` Playwright project runs reset → demo → artifact →
server adapter → rendered components, then reset → unavailable → regenerate →
fresh receipt with the same canonical hash, without restarting the web server.
It also checks desktop/tablet/mobile widths and the unconnected production Today.
CI installs the locked Python runtime for this project and runs all existing
kernel, Inspect eval, web and Playwright gates.
