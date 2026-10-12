# Final documentation validation (#60 → #61 → #62)

Audit baseline: `42c82b58c8966f0aada9c382575c811cd93176d1`, fresh main on
2026-10-12. This includes the final controlled-dev/1 evidence in PR #89 and
completed core documentation in PR #90. This lane changes documentation and
its reference checks only; no runtime, product, evaluation behavior, frozen
artifact or holdout execution is changed.

## Manual cross-check

| Requirement | Finding / evidence |
| --- | --- |
| Five canonical documents (#60) | [architecture](architecture.md), [evidence](evidence-model.md), [safety](safety.md), [privacy](privacy.md), [evaluation](evaluation.md) remain consistent with current main; [previous detailed audit](documentation-review.md) maps authority, non-goals and excluded technologies to implementation/history |
| Exact DEV result | [PR #89](https://github.com/Sathvikar01/morrow/pull/89), [report](controlled-dev-1.md), [summary](../eval/reports/archive/2026-10-12-controlled-dev-1/summary.json): PASS, A62/62 vs B3/39 unsupported, VERIFIED 0/22, attempts 305/275, tokens 4,187,529/3,863,797; no declared safety/provenance regressions; all 72 arm runs PARKED_UNRESOLVED |
| Evaluation limitations | Historical DEV FAIL, replay INCONCLUSIVE, live-gate/3–5 INVALID retained; #67 unmerged; holdout not run; DEV does not establish baseline superiority, general resolution or statistical significance |
| Authority | Parent identity/exact approval, independent external verifier, adjacent promotion, Dream/Critic/single committer, retained refutations, no cost override; structured checks do not semantically certify arbitrary prose or prove causal truth |
| Integration vs deployment | Maya runs real domain services with scripted model/browser/Telegram I/O; Twin/Memory UI sources remain UNCONNECTED, projection transport exists but no page subscribes; no live/deployed demo claim |
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
  `3752477f9a66d039ba6002c72cfe9dc2e03c8e1332ccf0fe3ab728df6db9dbb9`.
  Both report-file hashes (including final newline):
  `71d1d036277cb894a0f692f55ee795f16eb8d31b2aa5cd35fd9db1589de515a2`.
  The visible HTML/JSON contains 63 events, scoped memory
  `learnings/maya-pickup.md`, commit
  `a4d97b94438d00d4a45b4d4ca3c0c6f7411c1849`, one SUPPORTED Twin edge and two
  CANDIDATE alternatives. All generated files remain ignored.
- Fresh-clone README Maya/reset tests: **5 passed, 1 skipped** in 130.98s.
  The skip is Windows symlink permission; Linux CI exercises that path.
  Focused documentation/Maya/reset/controlled-decision suite in the primary
  checkout: **27 passed, 1 skipped** in 79.75s (same host-permission skip).
- Default checker: **8 documents, 343 link/path references, 72 GitHub issue/PR
  numbers, two pinned remote files, zero failures**. Supporting setup/web/Telegram
  notes: **3 documents, 21 references, nine issue/PR numbers, zero failures**.
- Archived `decide()` over all 36 saved pairs reproduces the exact PASS summary
  (excluding only the manifest hash added by the runner), with
  `holdout_executed=False`. No private raw state was recounted and no live call
  was made. Trace CSV and cfo.ai readback were inspected, not regenerated.
- Ledger self-check: 25 events, hash chain OK, replay identical, tamper detected.
  Economics report reproduction: identical. Ruff lint/format and strict mypy
  (97 product files): pass. Secret/history scan and env audit: zero findings;
  synthetic audit: all 87 reviewed assets unchanged. Final diff passes whitespace
  checks and contains documentation/reference tests only.

Four required PR checks must all pass before merge; their final run is linked
from the PR and issue completion evidence. A green docs merge does not change
the four BLOCKED checklist rows or accept the complete demo build.

Issue disposition: #60 remains closed after recheck; #61 stays open because
#53/#54 strict completion is outstanding. #62 can close when its checklist,
evidence mapping and dry-run checks pass, while its documented release verdict
remains BLOCKED. Creating the checklist does not close #53/#54 or approve release.
