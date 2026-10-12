# Final documentation validation (#60 → #61 → #62)

Initial baseline: `42c82b58c8966f0aada9c382575c811cd93176d1`. Final refreshed
main: `6b8207300271620e775d33879add3533d59ad992` on 2026-10-12. This includes
the final controlled-dev/1 evidence in PR #89, completed core docs in PR #90,
the #37 Experiments/Approval surface and concurrently merged README
[PR #91](https://github.com/Sathvikar01/Serene/pull/91). This lane changes documentation and
its reference checks only; no runtime, product, evaluation behavior, frozen
artifact or holdout execution is changed.

## Manual cross-check

| Requirement | Finding / evidence |
| --- | --- |
| Five canonical documents (#60) | [architecture](architecture.md), [evidence](evidence-model.md), [safety](safety.md), [privacy](privacy.md), [evaluation](evaluation.md) remain consistent with current main; [previous detailed audit](documentation-review.md) maps authority, non-goals and excluded technologies to implementation/history |
| Exact DEV result | [PR #89](https://github.com/Sathvikar01/Serene/pull/89), [report](controlled-dev-1.md), [summary](../eval/reports/archive/2026-10-12-controlled-dev-1/summary.json): PASS, A62/62 vs B3/39 unsupported, VERIFIED 0/22, attempts 305/275, tokens 4,187,529/3,863,797; no declared safety/provenance regressions; all 72 arm runs PARKED_UNRESOLVED |
| Evaluation limitations | Historical DEV FAIL, replay INCONCLUSIVE, live-gate/3–5 INVALID retained; #67 unmerged; holdout not run; DEV does not establish baseline superiority, general resolution or statistical significance |
| Authority | Parent identity/exact approval, independent external verifier, adjacent promotion, Dream/Critic/single committer, retained refutations, no cost override; structured checks do not semantically certify arbitrary prose or prove causal truth |
| Integration vs deployment | Maya runs real domain services with scripted model/browser/Telegram I/O; Twin/Memory UI sources remain UNCONNECTED, projection transport exists but no page subscribes; no live/deployed demo claim |
| New #37 surface | Experiments view, decision panel and WebApprovalChannel are implemented; exact shown digest/class and single-use receipt go through admission. The adapter trusts a transport-authenticated principal; shipped page passes no transport. All five docs rechecked; no live approval UI claim |
| Privacy / economics | #59 merged; safe telemetry differs from inference-provider context; synthetic public artifacts; genuine cfo.ai readback with assumed rates/usage/cash/revenue, not measured production dollars; default runtime costs unknown |
| Entire | #54 open, verified milestone Git/PR references do not establish complete ordered native checkpoint coverage; separate index branch is not silently incorporated into main |
| README (#61) | Thesis/problem/diagram/trust boundary/Maya/setup/reset/NeatLogs/DEV/economics/Entire/privacy/methodology/evidence links present; stale foundation-only status and planned-feature list removed; keep #61 open for #53/#54 strict dependencies |
| Checklist (#62) | [20-row checklist](final-demo-checklist.md): 16 bounded PASS proofs, four BLOCKED conditions (holdout, full improvement acceptance, Entire checkpoints, connected live presentation); all rows carry evidence and visible proof; complete demo build remains BLOCKED |
| Scope | No feature, scorer/oracle/protocol/threshold/report change, no live model call, holdout, external message, deployment or transcript publication |

## Execution receipt

Validation results are recorded here after execution; PR checks are the final
merge gate. The default documentation checker now includes the README,
checklist, this receipt and all five canonical docs. It validates local links,
heading anchors, repository paths/reports, referenced GitHub issues/PRs and
pinned GitHub files. It does not prove prose claims or crawl arbitrary websites.

Executed on Windows with Python 3.11.9:

- Fresh **local clone** of documentation commit
  `753b44a5100d749bc990b47bffb808b0c12a481a` into an ignored workspace, with a
  new virtualenv and no `.env`; `uv sync --locked --all-extras --group dev`
  installed the locked dependencies. The smoke uses current tracked source,
  not copied local credentials or an existing installation. Git/uv were already
  installed on the host; this is not a hosted deployment or clean-OS test.
- Checklist commands reset → demo → reset → demo succeeded, all 18 beats each
  time. Baseline SHA-256:
  `41836ad96c19ec844870b7e185bd8ad548ad3beab90318350e07c93b15488681`.
  Both canonical domain report hashes:
  `4000dac552cca6086d39e352795c2a2c79a0bedc69c823247a08c47173e12c7e`.
  Both report-file hashes (including final newline):
  `0b26ae8379ed333a7cade5019648b6b3f93d5a24ba3e1deb62b6989276b13c26`.
  The visible HTML/JSON contains 63 events, scoped memory
  `learnings/maya-pickup.md`, commit
  `a811431e499a46cceb1ba8217c114c78e34e0c68`, one SUPPORTED Twin edge and two
  CANDIDATE alternatives. These three values were regenerated after the policy
  version bump to `safety/2` and `promotion/3` (#97); the versions are recorded
  in the demo's events, so the hashes changed while all 18 beats, the baseline
  hash and the event count did not. Before that bump they were `3752477f…`,
  `71d1d036…` and `a4d97b94…`. All generated files remain ignored.
- Fresh-clone README Maya/reset tests: **5 passed, 1 skipped** in 130.98s.
  The skip is Windows symlink permission; Linux CI exercises that path.
  Focused documentation/Maya/reset/controlled-decision suite in the primary
  checkout: **27 passed, 1 skipped** in 79.75s (same host-permission skip).
- Default checker at initial smoke: **8 documents, 343 link/path references, 72 GitHub issue/PR
  numbers, two pinned remote files, zero failures**. Supporting setup/web/Telegram
  notes: **3 documents, 21 references, nine issue/PR numbers, zero failures**.
- Archived `decide()` over all 36 saved pairs reproduces the exact PASS summary
  (excluding only the manifest hash added by the runner), with
  `holdout_executed=False`. No private raw state was recounted and no live call
  was made. Trace CSV and cfo.ai readback were inspected, not regenerated.
- Ledger self-check: 25 events, hash chain OK, replay identical, tamper detected.
  Economics report reproduction: identical. Ruff lint/format and strict mypy
  (97 product files): pass. Secret/history scan and env audit: zero findings;
  synthetic audit at initial baseline: all 87 reviewed assets unchanged. Final diff passes whitespace
  checks and contains documentation/reference tests only.

After rebasing onto the newly merged #37/#91 main, the documentation plus
web-approval/Experiments-view tests passed **24/24**. Maya was run again on the
new runtime baseline: all 18 beats passed with the identical domain hash above.
The current synthetic inventory is **89 reviewed assets**, with zero findings;
the two new reviewed assets came from main's #37 work, not this documentation PR.
The main runtime baseline's [four green jobs](https://github.com/Sathvikar01/Serene/actions/runs/38191229609)
are separate from the final docs PR checks. PR #91's historical auto-close of
#61 is corrected: this lane keeps it open under the user's stricter #53/#54
dependency condition. The historical fresh-clone receipt above remains labeled
with the exact commit it tested.

Final reference recheck: **8 documents, 360 link/path references, 74 GitHub
issue/PR numbers, two pinned files, zero failures**. Supporting setup/app notes:
**3 documents, 25 references, ten issue/PR numbers, zero failures**. Ruff passes
for 262 formatted files; strict mypy passes for 100 product source files on the
refreshed main. These supersede the earlier baseline's inventory/type counts.

Four required PR checks must all pass before merge; their final run is linked
from the PR and issue completion evidence. A green docs merge does not change
the four BLOCKED checklist rows or accept the complete demo build.

Issue disposition: #60 remains closed after recheck; #61 stays open because
#53/#54 strict completion is outstanding. #62 can close when its checklist,
evidence mapping and dry-run checks pass, while its documented release verdict
remains BLOCKED. Creating the checklist does not close #53/#54 or approve release.
