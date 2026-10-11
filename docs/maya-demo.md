# Canonical Maya demo (#56)

Run from the repository root with Python 3.11–3.13, Git and uv:

```sh
uv sync --locked --all-extras --group dev
uv run python scripts/maya_demo.py
```

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
