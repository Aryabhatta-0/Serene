# Final release audit — 12 October 2026

## Release candidate

Fetched main: `cc7d0afb5c0adf377003d9a3290ad700c0488347`. #105, #106 and
#107 are merged; the main baseline has all four required checks green.
This report covers the final hardening branch based on that SHA. The final
tested commit and its CI checks are recorded in the hardening PR and handoff.
Open PRs at audit start: #67 (open), #69 and #93 (draft). They were not included.
Open issues: #61, #53 and #54. The original main checkout has nine pre-existing
modified web/demo files; they were preserved. The fresh audit worktree began clean.

Graphify was rebuilt first, AST-only with `--code-only --force --no-cluster`:
514 code files, 5,874 extracted nodes and 22,677 edges. Review followed the graph's
ingress, admission, projection, memory and provenance paths.

Environment: Windows, Python 3.11.9, Node 24, Chromium; local production Next.js
servers on private ports, hosted `serene-hackathon-e2e` Supabase (PostgreSQL 17,
ap-south-1). All new records/accounts are synthetic. There is no public deployment.
The hosted project lacked the committed Twin projection migration; it was applied
before testing. The browser-ledger grant fix was also applied and tested there.

## Feature completeness

LIVE means real service transport was exercised with synthetic data. TESTED means
implementation and passing tests, without a new external-service proof. DEMO
means canonical real domain services with scripted external I/O. PARTIAL identifies
the specific missing connection. These correspond to LIVE-PROVEN, IMPLEMENTED /
TEST-ONLY, DEMO-ONLY and PARTIAL respectively; no file's existence is treated as proof.

| Feature | Status | Evidence / limit |
| --- | --- | --- |
| Telegram → Hermes | TESTED | Authenticated channel and live transport implementation; no new live Telegram/provider run in this audit; operator relay/webhook wiring is separate. |
| Authenticated ingress | TESTED | Secret, bound sender, private-chat, duplicate/update and callback tests. |
| Observation structuring | DEMO | Separate reported/structured events; failed structuring remains visible. |
| Provenance / parent and caregiver binding | TESTED | Typed canonical actors; external identities stay in private bindings. |
| Competing hypotheses | DEMO | Maya retains three alternatives. |
| Missing evidence / parent questions | DEMO | Request lineage and exact micro-answer. |
| Acquisition / failure / retry | DEMO | Injected failure, same request, bounded recovery. |
| Verifier rejection / verified evidence | DEMO | Rejected excerpt retained; subsequent capture passes six checks. |
| Next action / parked unresolved | TESTED | Controller and projection tests; archived DEV ends parked. |
| Investigation completion | PARTIAL | Existing empty/filtered-plan sufficiency limitation remains; #69 is frozen draft. |
| Experiment proposal / GREEN / AMBER / RED / reversibility | TESTED | Domain safety tests and all-stage browser fixtures; GREEN and RED also hosted. |
| Parent approve / decline | LIVE | Browser → relay → real session/guardian → channel/admission → ledger → projection → Realtime. |
| Stale digest / RED / unauthorized parent / caregiver refusal | LIVE | Hosted refusals and domain/HTTP tests; RED has no UI approval action. |
| Replay / reused request ID with different body | TESTED | HTTP idempotency tests; exact replay also hosted. |
| No optimistic decision / pending controls | LIVE | Original real WS frames held; HTTP alone does not move phase. Component tests cover double-click and disabled controls. |
| Outcome / promotion | DEMO | Approved trial, reported outcomes, adjacent checked promotion. |
| Dream proposal / accepted patch / rejected patch + reason | LIVE | Canonical scripted Maya ledger published to hosted projection and rendered on production Memory route. |
| Exact Git revision / deterministic rebuild | LIVE | Hosted Memory shows pinned Git SHA; backend refuses unavailable revision. |
| Stale / review Memory states | TESTED | Component and browser fixtures; statuses preserved. |
| Live Memory / reconnect / immediate child clearing | LIVE | Hosted production-route read plus kernel Memory lane and sync/isolation regressions. |
| Candidate / supported Twin edges | LIVE | Hosted synthetic Maya and pending-trial families. |
| Refuted / superseded Twin edges | TESTED | Backend provenance and browser fixture tests; these states were not fabricated in hosted Maya. |
| Counterevidence / complete lineage / reasons | TESTED | Projection/parser/provenance tests; hosted available edge anchors resolve. |
| External / family distinction, scope, review dates | LIVE | Privacy-safe production projection and textual provenance. |
| Raw evidence reachability | PARTIAL | Metadata/digest lineage nodes resolve; withheld raw text has no browser HTTP evidence-content endpoint. |
| Parent-only Twin access | LIVE | Other parent, caregiver and anon denied; raw private identifiers/URLs absent from Twin payload. |
| Sign in / sign out / session loss | LIVE | Real GoTrue and cross-tab session loss; no old family remains. |
| Child selection / switching | LIVE | Actual RLS-scoped selection; account-switch first-render regression fixed; late-child rows tested in kernel lane. |
| Today / Investigations / Experiments / Memory / Twin | LIVE | Clean production-route journey and seven-width audit. |
| Realtime / reconnect / resync | LIVE | Kernel append → hosted DB → projection → real WS → browser, offline append and recovery without reload. |
| NeatLogs | LIVE | Archived 54 accepted suffix exports; current-tree synthetic Maya trace: 141 spans, seven accepted batches, zero drops/errors. |
| Entire | PARTIAL | CLI enabled, Git/PR provenance present; native ordered historical checkpoint coverage/retrieval incomplete. |
| cfo.ai | LIVE | Existing saved scenario read back: 71 cells, no formula errors; local economics reproduction passes. Values are assumptions. |

## Bugs found

| Severity | Reproduction / root cause | Fix | Regression |
| --- | --- | --- | --- |
| P0 privacy | Owning parent's authenticated REST session could SELECT canonical ledger fields excluded from web projections. RLS scoped rows but grants still exposed raw payloads. | New migration revokes browser ledger SELECT; backend grants retained. | Four current-migration privilege-denial tests and real owning-parent REST 403/42501. Existing row-policy assertions remain tested independently in a disposable DB. |
| P0 privacy | Change authenticated account; the first committed render could expose previous account's selected child before the clearing effect. | Associate the child list with the user who loaded it; suppress mismatched first render. | Layout-effect witness failed before fix, passes after. |
| P1 reliability | Close Realtime then deliver a late row: status became live and approvals could re-enable; lagging reconnect snapshot could regress state. | Track connection separately, buffer disconnected rows and retain higher sequence for projections still present in resync. Omitted projections still clear. | Two regressions failed before fix; sync/Memory and full web suite pass. |
| P0 security | Next 14.2.35 includes Windows unauthenticated RCE and other critical advisories; test toolchain also had critical audit findings. | Next 15.5.27, PostCSS override 8.5.29, Vitest 4.1.11; adapt async searchParams and JSX transform configuration. | Zero npm audit findings, production build, 263 unit tests and browser suites. No runtime assertions weakened. |
| P2 loading UI | Credential fields were server-rendered before Auth resolved; browser CI observed duplicate fields during hydration. | Render an explicit checking-sign-in state until the stored session is known. | Server-render regression failed before fix; full component suite passes. Strict browser field locators remain unchanged. |
| P1 deployment | Hosted project had not applied the committed causal_twin constraint migration; current preparer refused. | Apply existing Twin migration. | Current hosted preparation and Twin Realtime test pass. |
| P2 documentation | Current README/checklist still described connected surfaces and dependency findings as blocked/unconnected. | Update factual current claims, retain dated audit receipts and frozen evaluation limitations. | Documentation/link and privacy scans. |

Code and regression tests are in the final hardening PR. No frozen fixture,
evaluator, #67/#69 behavior, Maya semantics or acceptance rule was changed.

## UI review

All five production surfaces passed at 320, 375, 390, 768, 1024, 1440 and 1920 px.
Desktop/mobile screenshots were captured for every surface, including the hosted
Memory/Dream and supported Twin data. No horizontal overflow, empty action names,
console errors or hidden HTTP failures occurred in the clean journey. Desktop and
tablet hierarchy and mobile wrapping remain usable after #106.

| Page | Purpose / attention / next step / uncertainty |
| --- | --- |
| Today | Current question leads; needs-you area and reviewed learning are separate. Follow the investigation. Learning scope remains explicit. |
| Investigations | Competing explanations, missing/checked evidence and next-action rail explain progress. Reason codes without plain-language mappings remain technical. |
| Experiments | Safety words and marks, reversibility, exact decision and lifecycle make the parent action clear. Phase follows published state. |
| Memory | Kept/rejected proposals and reasons, Git revision and lineage are visible. Complete provenance creates long mobile scroll and many opaque references. |
| Causal Twin | Every edge has a textual alternative to the graph and provenance. Unnamed live variables are honestly listed; no guessed graph labels are supplied. |

Keyboard skip link, menu Escape/focus return, named controls, one H1, forms,
textual safety, reduced motion and provenance anchors are exercised by browser
and component gates. Design-token text contrast was reviewed. No axe dependency
was installed, and no screen-reader certification is claimed. Remaining visual
limits: long provenance scroll, technical reason codes, unnamed live graph variables.

## Security

Real GoTrue, RLS, guardianship and parent-only projection reads passed. Browser
cannot query ledger directly; anon cannot read protected state, caregiver grants
do not expose approvals/Memory/Twin, and only projection_state is published to
Realtime. Browser environment and bundled JS were checked for privileged values.
Current-tree secret scan, environment and synthetic-data audits pass. The history
scan reports four references to the same fake verifier token in historical blob
`75a17eba4bd7` (`tests/test_web_approval_http.py`, lines 139/145/198/286).
It is an in-memory test stand-in, not a service credential; the current tree
already uses the explicit fake prefix. Classified FALSE POSITIVE; no history rewrite.

Supabase advisors: six warnings, zero errors; four additional performance warnings:

| Finding | Classification | Reason |
| --- | --- | --- |
| Two mutable trigger search paths | ACCEPTED HACKATHON LIMITATION | SECURITY INVOKER triggers; referenced ledger relation is schema-qualified; browser writes denied. No demonstrated exploit in this surface. |
| Two authenticated SECURITY DEFINER helpers | FALSE POSITIVE | Intentional JWT-subject-bound Boolean RLS helpers, fixed empty search_path, caregiver expiry/revocation checked. |
| Leaked-password protection disabled | ACCEPTED HACKATHON LIMITATION | Synthetic local demo; enable before real-family deployment. |
| Insufficient MFA options | ACCEPTED HACKATHON LIMITATION | Synthetic local demo; no production authentication-hardening claim. |
| Four multiple permissive SELECT policies | ACCEPTED HACKATHON LIMITATION | Parent/caregiver OR policies; performance warning, not evidence of cross-family access. |

Temporary audit login/passwords are revoked after testing. Synthetic append-only
ledger evidence and pinned Memory Git objects are retained. No history rewrite.

## End-to-end journeys

| Journey | Result | Boundary |
| --- | --- | --- |
| Telegram ingress | PASS (tests/demo); live UNVERIFIED | No safe audit-owned Hermes API key was available; existing final ingress was not disturbed. |
| Investigation | PASS (canonical); PARTIAL general completion | Empty-plan limitation remains frozen. |
| Evidence verification | PASS | Canonical failure/retry/rejection/verification. |
| Experiment / approval | PASS | Real hosted approval and decline; deterministic safety/refusal tests. |
| Promotion / Dream | PASS | Canonical domain services, scripted I/O. |
| Memory / Causal Twin | PASS | Hosted production routes and scoped projections; raw evidence remains metadata-only. |
| Supabase reconnect | PASS | Real network-offline append, reconnect and resync; no reload or duplicate rendered item. |

## Evaluation

Maya ran twice: 18/18, 63 events, identical report bytes. Domain hash:
`4000dac552cca6086d39e352795c2a2c79a0bedc69c823247a08c47173e12c7e`.
Ledger self-check: valid chain, identical replay, tamper refusal.
Frozen core scenarios: 10/10; fixture SHA remains
`bdbbc1ad63c727ecf0f17ebe98d33ce5b5ae85d4ac46e7adb489ddf9c335225b`.
Parked unsupervised vehicle is RED/refused and conflicting caregiver observation
cannot disappear during Level-5 promotion. Inspect invariants: 20/20.

Controlled DEV archive verifies PASS, 54/54 suffix exports and zero declared
mismatches. #67 remains unmerged; all 72 runs parked unresolved. Holdout was NOT
run. Today's hardening tests do not satisfy or alter the frozen improvement gate.

Release gates: Ruff, format, mypy, 1,473 pytest passes (one Windows symlink skip),
Inspect, frozen scenarios, web typecheck, 263 frontend tests, production build,
139 default Playwright passes (three deliberate viewport skips), approvals/Memory
lane 2/2, Twin lane 1/1, hosted lane 6/6 and richer hosted review lane 2/2.
Independent hosted check: sequence 41, two decisions, verified chain/projections.
A separate hosted canonical family proves pinned Memory and controlled publication
failure/recovery. No concurrent test mutates the same Maya workspace.

The first PR CI run caught the old documentation assertion requiring connected
presentation to remain BLOCKED and a transient duplicate credential form in the
tablet fixture. The documentation assertion now requires PASS with hosted receipt
and production-route evidence links; the three independent evidence blockers remain
asserted. The loading form was fixed in product code with a failing-before/passing-after
regression. Final merge requires all four checks on the latest PR commit.

## Sponsor evidence

NeatLogs: genuine archived receipts and new accepted current-tree trace, session
`serene-final-audit-20261012`. The new trace is scripted Maya with live logging,
not a live Telegram trace or a new before/after experiment. Telemetry failure
does not affect admission; only allow-listed filtered metadata leaves the kernel.

Entire: CLI commands execute, current branch checkpoint list is empty. Retrieval
of the #106 checkpoint trailer `01M4QQAZVG7SQ4Z945Y79916TM` returned checkpoint
not found. Git/PR history remains inspectable; complete native coverage is absent.
Do not fabricate replacement historical checkpoints or publish private transcripts.

cfo.ai: real saved readback has 71 nonempty cells, zero formula errors; assumed
cost 2,725,256 micro-USD/family-month, 7,728 margin basis points and 524-day runway
match the local model. These are assumed operating inputs, not production costs.

## Remaining gaps

| Gap | Submission impact |
| --- | --- |
| Hardening PR must have all four checks green and merge before recording final main. | BLOCKS SUBMISSION |
| Existing manual gate requires an independent frozen holdout/full-improvement result; it is absent. | BLOCKS SUBMISSION under the unchanged checklist. No holdout run is authorized by this audit. |
| Existing manual gate requires all eight ordered genuine Entire checkpoints; coverage/retrieval is incomplete. | BLOCKS SUBMISSION under the unchanged checklist. |
| New live Telegram/provider smoke unavailable without an audit-owned safe runtime/key. | DOES NOT BLOCK SUBMISSION for the explicitly synthetic Maya/local web narrative; live Telegram claim remains unproven here. |
| Empty-plan completion limitation (#69), raw-evidence content endpoint absent, unnamed Twin variables. | DOES NOT BLOCK SUBMISSION for the bounded canonical narrative; do not claim general resolution, raw text browsing or a fully labeled live graph. |
| No public deployment, production auth hardening, load test or screen-reader certification. | DOES NOT BLOCK SUBMISSION for user-requested local synthetic recording. |

## FINAL VERDICT

**NO-GO — FIX THESE BLOCKERS FIRST**

Merge the hardening PR only after its four checks pass. Fulfill the existing
holdout/improvement and native Entire evidence requirements through their approved
protocols, or have the release owner explicitly change the submission acceptance
scope. This audit does not waive those requirements or authorize running holdout.
