# Core documentation review (#60)

Audit date: 2026-10-12. Source baseline:
`8b0a3c766f04a6fe953819cbb188069baa633743` (merged #59 privacy, #55 economics,
#58 required-CI, #33 projection feed, #36 Memory/Dream review and #89 controlled
DEV evidence). The five canonical documents are
[architecture](architecture.md), [evidence](evidence-model.md), [safety](safety.md),
[privacy](privacy.md) and [evaluation](evaluation.md).

## Manual consistency audit

| Claim checked across the five docs | Finding and source |
| --- | --- |
| Serene thesis / authority | Model proposals are separate from deterministic admission, promotion, safety, verification and memory publication; [kernel](../serene/ledger/service.py), [admission](../serene/policies/admission.py) |
| Parent approval / evidence verification | Authenticated callback receipt permits one exact non-RED trial; verifier confirms bounded source checks; neither substitutes for the other |
| Investigation completion | Current empty-plan sufficiency limitation explicitly disclosed in architecture/evidence/safety; #67/#69 unmerged behavior not claimed implemented |
| Provenance / epistemic ladder | First-hand VERIFIED means authenticated report; external captures require verifier checks; no rung skips; N-of-1 is scoped support, not an estimated causal effect |
| Dream / memory / Causal Twin | Six stages propose; deterministic Critic and one committer govern writes; refuted/superseded edges and counterevidence remain inspectable; prose is not semantically certified |
| Supabase / projection / web | Scoped SELECT RLS and #33 Realtime feed implemented; `serene` now exposed through PostgREST under RLS; optional publisher can lag without undoing append; no page connects the feed; #36 read-only Memory/Dream UI exists; Causal Twin/Memory sources UNCONNECTED; #75 remains open |
| NeatLogs / privacy #59 | Merged #80 redaction, fixed error boundaries and scans described; token filters are not a universal PII detector; inference context is private external processing |
| Economics #55 | Genuine cfo.ai Scenario/readback, assumed input economics, measured historical tokens, unknown prices and exact optional confirmation boundary distinguished |
| Entire #54 | Eight verified repository-reference milestones are distinct from incomplete native checkpoints; index is on local #54 branch, not audited main; no completion claimed |
| Evaluation history | Original DEV FAIL; paired replay INCONCLUSIVE; live-gate/3, /4, /5 INVALID; preparation NOT_EVALUATED is not a later live verdict; separate controlled-dev/1 PASS is now merged, with no holdout or resolved terminals |
| CI #58 | Merged #81 and active ruleset 24892907 require PR + four Actions checks; classic-protection 404 does not imply absent enforcement |
| Non-goals / excluded technology | All six required prohibitions explicit; technology exclusions traced to original committed architecture rationale, with current ownership clarified |
| Scope | README, product/eval behavior, frozen manifests/tapes/scorers/oracles/reports and holdout unchanged; no live evaluation or provider calls |

The #54 index was revalidated read-only at local commit
`8b15e36befa96cea506344ffba310d0fcbdbad44` with its existing
`uv run python scripts/entire_provenance.py --github`: all eight Git/GitHub
mappings verified. This does not verify complete native checkpoint coverage,
publish that branch or change #54.

## Reproducible checks

```sh
uv run python scripts/docs_check.py --github
uv run pytest -q tests/test_documentation.py
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python scripts/secret_scan.py --history
uv run python scripts/env_audit.py
uv run python scripts/synthetic_audit.py
uv run python scripts/economics_report.py --check
uv run python scripts/ledger_selfcheck.py
uv run pytest -q
```

The documentation checker validates inline local Markdown paths/heading anchors,
backtick repository paths and report targets. `--github` checks referenced
issue/PR numbers (including ranges), URL kinds and pinned remote source files
using read-only `gh` API calls. CI runs the offline documentation test as part of
pytest; no account or provider key is needed. This is not a general Markdown
parser, arbitrary external-site crawler or automatic proof of prose accuracy.

Recorded local results:

- Five canonical docs: 238 link/path references checked, zero failures;
  68 referenced GitHub issue/PR numbers and two pinned remote source files validated.
- Supporting review document also passes (six docs, 246 references;
  69 issue/PR numbers, zero failures).
- Documentation regression tests: seven passed, including missing paths/anchors,
  wrong issue-versus-PR URL kinds and numeric-heading fragments.
- With the 14 merged controlled-decision tests: 21 targeted tests passed.
  Calling frozen `decide()` on the 36 archived pairs reproduces PASS and the
  identical summary, excluding only the manifest digest added by `run()`.
- Repository Ruff lint/format and strict mypy: passed (97 product source files).
- Secret/history scan, environment coverage and synthetic-data audit: zero
  findings; all 87 reviewed synthetic assets/generators retain their bytes.
- Economics report reproduction and ledger replay/hash/tamper self-check: passed.
- Full backend-suite and required CI results are reported in the documentation PR.

## Completion status and independent limits

The only pending #60 paragraph was updated after #89 merged into main:
[controlled-dev/1](evaluation.md#controlled-dev1) now records its final PASS,
report/commit, safety/provenance findings, unsupported/VERIFIED counts, paired
investigation result, measured usage, infrastructure limits and holdout eligibility.
The archived decision is reproduced read-only; no raw private artifact is
recounted or rewritten here. Historical FAIL/INCONCLUSIVE/INVALID statuses remain.
There is no remaining documentation blocker once PR CI passes. #54's incomplete
checkpoint coverage, #53's open improvement-story acceptance, #67's unmerged
product change, its unrun holdout, #75's full Twin projection and the unconnected
web pages are explicitly documented limitations, not claims of completion.
This task does not close those issues or begin README #61.
