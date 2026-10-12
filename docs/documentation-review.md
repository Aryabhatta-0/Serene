# Core documentation review (#60)

Audit date: 2026-10-12. Source baseline:
`b8b102d4ef1ced045146ae50fa57837f5d0d9df4` (merged #59 privacy, #55 economics
and #58 required-CI work). The five canonical documents are
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
| Supabase / projection / web | Scoped SELECT RLS is implemented; old “no end-user policies” claim corrected; projections are disposable; web source UNCONNECTED; #33/#75 remain open |
| NeatLogs / privacy #59 | Merged #80 redaction, fixed error boundaries and scans described; token filters are not a universal PII detector; inference context is private external processing |
| Economics #55 | Genuine cfo.ai Scenario/readback, assumed input economics, measured historical tokens, unknown prices and exact optional confirmation boundary distinguished |
| Entire #54 | Eight verified repository-reference milestones are distinct from incomplete native checkpoints; index is on local #54 branch, not audited main; no completion claimed |
| Evaluation history | Original DEV FAIL; paired replay INCONCLUSIVE; live-gate/3, /4, /5 INVALID; preparation NOT_EVALUATED is not a later live verdict |
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

- Five canonical docs: 214 link/path references checked, zero failures;
  64 referenced GitHub issue/PR numbers and two pinned remote source files validated.
- Supporting review document also passes the link/reference check.
- Documentation regression tests: seven passed, including missing paths/anchors,
  wrong issue-versus-PR URL kinds and numeric-heading fragments.
- Repository Ruff lint/format and strict mypy: passed (96 product source files).
- Secret/history scan, environment coverage and synthetic-data audit: zero
  findings; all 76 reviewed synthetic assets/generators retain their bytes.
- Economics report reproduction and ledger replay/hash/tamper self-check: passed.
- Full backend-suite and required CI results are reported in the documentation PR.

## Exact remaining #60 item

**controlled-dev/1 — final result pending.** Its final result is not in audited
main. Keep #60 open and the documentation PR unmerged. Once final evidence is
merged, replace the single paragraph in [evaluation.md](evaluation.md#controlled-dev1)
with the exact verdict, final report/commit, safety/provenance findings,
unsupported/VERIFIED counts, paired investigation result, actual tokens/attempts
(unknown remains unknown), infrastructure limits and holdout eligibility.
Retain all historical statuses and assess #53 against the final evidence.
No pending work is described as PASS; #54's independent limitation does not
prevent accurately documenting its status. Do not start README #61 here.
