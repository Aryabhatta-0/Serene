# Final demo acceptance checklist (#62)

Source: fresh `main` at `42c82b58c8966f0aada9c382575c811cd93176d1`
(2026-10-12, including #89 and #90). **Release verdict: BLOCKED.**
This is a release checklist, not permission to run holdout or deploy a family service.

PASS means the named, bounded proof exists and was checked. It does not imply
live external availability or production readiness. BLOCKED means that beat lacks
its required evidence. No averaging, waiver or DEV substitution turns a blocked
row into PASS. **Do not label the complete demo build accepted until every row is
PASS.** The offline Maya walkthrough can still be shown with these limitations.
CI protects code merges; this document is the manual demo release gate, not a
new automated deployment control.

## Evidence and visible proof

The generated Maya HTML lists 18 beats with ledger sequences. Its companion
JSON carries the full ledger, prompts, six verifier checks, Dream stages, memory
content/commit and before/after Twin. Commands below regenerate both; generated
files remain ignored and contain only synthetic data.

| Beat / acceptance condition | Status | Exact evidence | Demo-visible proof |
| --- | --- | --- | --- |
| Telegram: authenticated reports, exact callbacks; text cannot approve | PASS | [ingestion tests](../tests/test_telegram_ingestion.py), [approval binding](../tests/test_approval_binding.py), [Maya fixture #56](maya-demo.md) | HTML beats 1/5/12 and JSON prompts/events; explain sender and model wire are offline fixtures, not a live bot |
| Investigation: three competing explanations remain explicit | PASS | [Maya E2E](../tests/test_maya_demo.py), [controller tests](../tests/test_investigation.py) | Beat 3: fatigue, hunger, transition; competitors remain CANDIDATE after learning; disclose current empty-plan sufficiency limitation in [architecture](architecture.md#telegram-hermes-and-investigation) |
| Evidence gap: request is linked to question and micro-answer | PASS | [fixture report validation](../serene/demo/report.py), [Maya E2E](../tests/test_maya_demo.py) | Beats 4/5: snack-response request and exact NO answer; JSON request lineage |
| Browser/recovery: same request survives an injected transient failure | PASS | [Maya E2E](../tests/test_maya_demo.py), [browser adapter](../serene/adapters/browser/hermes_browser.py) | Beats 6–8: failure event, RETRY_SCHEDULED, reacquisition of same request; scripted browser, not live website |
| Independent verifier: reject fabricated excerpt, verify new capture | PASS | [verifier](../serene/evidence/verifier.py), [Maya E2E](../tests/test_maya_demo.py) | Beats 9/10: EXCERPT_NOT_ON_SOURCE retained; different evidence ID passes six checks; source checks are not child-causation proof |
| Experiment/approval: safe reversible scope, parent before start | PASS | [approval tests](../tests/test_investigation_approval.py), [safety tests](../tests/test_safety_and_approval.py), [Maya E2E](../tests/test_maya_demo.py) | Beats 11/12: GREEN five-minute warning, seven-day trial, exact parent callback; compare approval/start sequence in JSON |
| Outcome: reported support belongs to the approved trial | PASS | [Maya E2E](../tests/test_maya_demo.py), [experiment service](../serene/experiments/service.py) | Beat 13 and JSON lineage; two later synthetic calm pickups, outcome after start; no real-child claim |
| Promotion Gate: adjacent rungs, bounded learning | PASS | [promotion policy](../serene/policies/promotion.py), [Maya E2E](../tests/test_maya_demo.py) | Beat 14: 3→4 then 4→5 after outcome; JSON validity/review/scope; not universal causal proof |
| Dream diff: governed accepted patch and explained refusal | PASS | [Dream tests](../tests/test_dream.py), [committer tests](../tests/test_memory_committer.py), [Maya E2E](../tests/test_maya_demo.py) | Beats 15–17: six stages, Git receipt, scoped memory content and rejected universal claim; compare JSON memory against empty reset seed; HTML shows receipt/refusal, not a full diff editor |
| Causal Twin: supported transition edge without erasing alternatives | PASS | [Twin tests](../tests/test_causal_twin.py), [Maya E2E](../tests/test_maya_demo.py) | Beat 18 HTML table and JSON before/after: one SUPPORTED level-5 edge, two CANDIDATE level-3 edges; no numeric confidence |
| NeatLogs: safe trace receipts, not domain authority | PASS | [54 live suffix receipts](../eval/reports/archive/2026-10-12-controlled-dev-1/neatlogs-sessions.csv), [sink tests](../tests/test_neatlogs_sink.py), [privacy audit](../tests/test_privacy_audit.py) | Open CSV: 54/54 accepted exports; show session ID, batches/spans and structured rejection diagnosis in [report](controlled-dev-1.md); no private raw states or narrative export; offline Maya does not prove live logging |
| Controlled evaluation: frozen conditional DEV decision reproduced | PASS | [PR #89](https://github.com/Sathvikar01/morrow/pull/89), [summary](../eval/reports/archive/2026-10-12-controlled-dev-1/summary.json), [pairs](../eval/reports/archive/2026-10-12-controlled-dev-1/pairs.json), [decision tests](../tests/test_controlled_dev_decision.py) | Show PASS, rejections A62/62→B3/39, VERIFIED 0→22, attempts 305→275, tokens 4,187,529→3,863,797; all 72 PARKED_UNRESOLVED, zero safety/provenance regressions under declared guards; #67 unmerged |
| Holdout: one-time independent gate evidence | BLOCKED | [DEV report](controlled-dev-1.md), [missing-holdout gate tests](../tests/test_regression_gate.py), [#51](https://github.com/Sathvikar01/morrow/issues/51) | Point to “holdout was not run”; no holdout result to show, DEV PASS supplies eligibility only |
| Full before/after improvement acceptance | BLOCKED | [#53](https://github.com/Sathvikar01/morrow/issues/53), [#67 unmerged](https://github.com/Sathvikar01/morrow/pull/67), [evaluation limits](evaluation.md#6-frozen-regression-gate-51) | Show diagnosis and conditional DEV metrics, then explicitly state absent holdout/full regression-gate confirmation; do not call the product correction shipped |
| Entire: native ordered retrievable checkpoints for all eight milestones | BLOCKED | [#54](https://github.com/Sathvikar01/morrow/issues/54), [audited reference index and limitations](architecture.md#observability-economics-and-development-provenance), [#60 audit](documentation-review.md) | Show verified Git/PR evolution references and disclose incomplete genuine checkpoint coverage; local branch index is not a main artifact or a native checkpoint; never publish transcripts to fill gaps |
| cfo.ai: genuine Scenario, assumed inputs, constrained decision | PASS | [cfo.ai readback](economics/cfo-readback.json), [acceptance audit](economics/acceptance-audit.json), [decision tests](../tests/test_cfoai_economics.py) | Open [economics report](economics.md): assumed $2.725256/family-month, 77.28% margin, 524-day runway; optional estimates 9,038 vs 14,452 micro-USD only after policy equivalence; no measured production dollars |
| Reset/reproducibility: same seed and canonical report bytes | PASS | [reset tests](../tests/test_demo_reset.py), [Maya E2E](../tests/test_maya_demo.py), [reset command](../scripts/demo_reset.py) | Run reset→demo twice: identical baseline and domain SHA-256; fresh in-memory ledger/temp Git per run; unknown files preserved |
| CI: all four required jobs for audited main | PASS | [PR #90 checks](https://github.com/Sathvikar01/morrow/pull/90/checks), [workflow](../.github/workflows/ci.yml), [ruleset contract](setup.md#5-merge-gates-58) | Open four green required jobs on main's documentation baseline; this docs PR must separately pass the same four before merge; CI is not a live-model/holdout result |
| Privacy: public artifacts synthetic, secrets absent, scoped reads | PASS | [#59 / PR #80](https://github.com/Sathvikar01/morrow/pull/80), [privacy tests](../tests/test_privacy_audit.py), [RLS tests](../tests/test_rls.py), [secret scanner](../scripts/secret_scan.py) | Show zero scan findings and synthetic Maya label; explain HMAC/token-filtered metadata, backend ledger writes, inference-provider boundary and no production privacy certification |
| Connected live presentation: signed-in child → Twin/Memory UI | BLOCKED | [#84](https://github.com/Sathvikar01/morrow/issues/84), [#75](https://github.com/Sathvikar01/morrow/issues/75), [Twin source](../app/web/lib/causal-twin/source.ts), [Memory source](../app/web/lib/memory/source.ts), [known hosting advisories](privacy.md#6-non-goals) | Normal pages show UNCONNECTED; fixture routes are synthetic build-gated previews. Show Maya HTML/JSON as the domain demo, not a deployed dashboard; known Next.js/PostCSS advisories also require remediation before public hosting |

## Dry-run using this checklist only

1. From a clean clone, install with `uv sync --locked --all-extras --group dev`.
2. Run `uv run python scripts/demo_reset.py`, then `uv run python scripts/maya_demo.py`.
   Require exit 0 and 18 PASS lines. Open `.demo/maya/report.html` and its JSON.
   Walk the first ten rows using the beats/fields above; explain scripted I/O before
   starting. No bot credentials, real child data or website calls are involved.
3. Run `uv run pytest -q tests/test_maya_demo.py tests/test_demo_reset.py`.
   The E2E test compares all canonical bytes across independent repositories,
   and reset tests check baseline restoration and path guards. Reset/run once
   more and compare the printed hashes; a changed hash blocks reproducibility.
4. Open the archived [controlled report](controlled-dev-1.md),
   [all-pair table](../eval/reports/archive/2026-10-12-controlled-dev-1/all-36-pairs.csv)
   and trace CSV. Walk NeatLogs/DEV rows, including denominators, terminal states
   and the unmerged revision. Do not execute a live evaluation or holdout.
5. Open the Entire limitation and cfo.ai readback above. Run
   `uv run python scripts/economics_report.py --check`; require identical modeled
   results. Label assumptions before showing money or runway.
6. Run `uv run python scripts/docs_check.py --github` and
   `uv run python scripts/secret_scan.py --history`; require zero failures.
   Open the current PR's four checks before merging. State all four BLOCKED rows
   aloud; keep release verdict BLOCKED. No missing evidence is filled by narration.

The execution receipt is [final documentation validation](final-docs-validation.md).
A completed checklist document can satisfy #62 while its demo release gate is
BLOCKED. README #61 remains open while #53/#54 strict dependencies are incomplete;
#60's completed core-documentation acceptance remains closed. This lane changes
no product/runtime/evaluation behavior, frozen reports, thresholds or holdout state.

## Exact submission/demo narrative

> Serene helps a parent investigate before believing. In this synthetic Maya
> pickup demo, Hermes proposes competing explanations; deterministic code selects
> evidence, rejects an unsupported excerpt, requires exact parent approval, and
> promotes only the bounded learning supported by the trial. Dream proposes a
> reviewed memory change, and the Causal Twin retains alternatives. All 18 offline
> integration beats pass; the external I/O is scripted. Separately, controlled-dev/1
> passed its frozen DEV gate: unsupported rejections fell from 62/62 to 3/39 and
> VERIFIED captures rose from 0 to 22, with no declared safety/provenance regressions.
> All 72 runs still parked unresolved; #67 is unmerged and holdout was not run.
> NeatLogs has privacy-safe trace receipts, cfo.ai supplies an assumed economics
> analysis, and Entire checkpoint coverage remains incomplete. The offline demo
> is reproducible; the full release gate and connected live presentation remain
> blocked. We claim bounded integration and measured DEV evidence, not production
> readiness, general causal truth or a holdout pass.
