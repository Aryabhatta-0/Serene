# Release sponsor evidence — 12 October 2026

This receipt was checked after merging #108 at
`6d680369c46232862c32596f79b684fe26fdce95`. It summarizes existing genuine
evidence; it creates no new experiment, historical checkpoint or holdout result.

## NeatLogs failure, diagnosis and measured correction

The [controlled DEV report](controlled-dev-1.md) and
[independent recount](../eval/reports/archive/2026-10-12-controlled-dev-1/verification.json)
record 36 fixed pairs. Unsupported rejections fell **62/62 → 3/39**, VERIFIED
captures **0 → 22**, Hermes attempts **305 → 275**, and live suffix tokens
**4,187,529 → 3,863,797**. All **72 arm runs parked unresolved**. #67 remains
unmerged; this is measured evidence-verification improvement, not general task
superiority. The full DEV-plus-holdout research regression gate is not passed.

Holdout was not run. Controlled DEV evidence is reported only as DEV evidence and is not claimed as a holdout/generalization result.

Concrete trace pair: **`controlled-dev-1-07-A` / `controlled-dev-1-07-B`**,
`07-pr67-A-r1-browser_flaky_restart`. The
[accepted session receipts](../eval/reports/archive/2026-10-12-controlled-dev-1/neatlogs-sessions.csv)
and [per-pair metrics](../eval/reports/archive/2026-10-12-controlled-dev-1/all-36-pairs.csv)
match the retained local raw worker result. Its SHA-256 is
`a61ccbcced55afc11762df4596e1f1f390781c45abf88fbab19b64b389943e5b`,
matching the pre-existing [integrity archive](../eval/reports/archive/2026-10-12-controlled-dev-1/integrity.json).

| Pair 07 evidence | Before A | After B |
| --- | --- | --- |
| Requested-field counts | 5, 5, 5 | 1 |
| Captures rejected / evaluated | 2/2 | 0/1 |
| VERIFIED captures | 0 | 1 |
| Hermes attempts | 13 | 6 |
| Live tokens | 150,373 | 69,902 |
| Accepted trace batches / spans | 10/10; 201 | 7/7; 125 |
| Dropped spans / export errors | 0 / 0 | 0 / 0 |
| Terminal | PARKED_UNRESOLVED | PARKED_UNRESOLVED |

Before: ledger sequences 19 and 53 reject captures with
`REQUESTED_FIELD_UNSUPPORTED`; requested fields include pickup/handover procedure,
noise environment, nap schedule and staff guidance. The planner bundled fields
the source did not support. After: sequence 19 is `EVIDENCE_VERIFIED`, passing
DIGEST_MATCHES, EFFECTIVE_DATE_VALID, PROVENANCE_VALID, REQUESTED_FIELDS_PRESENT,
SOURCE_ALLOWED and SUBJECT_MATCHES. The #67 correction splits requests into bounded
units; it does not relax verifier acceptance rules. The same pair contains the
injected acquisition failure/restart and recorded recovery in both arms.

Read-only acceptance verification rehashed **76 retained raw files**, with zero
integrity mismatches, and called the unchanged `decide()` on the archived
`pairs.json`: PASS, identical summary. It made no live model call or rescore.
Reproduce the decision without running an experiment:

```sh
uv run python -c "import json; from pathlib import Path; from eval.runners.controlled_dev_experiment import decide; p=Path('eval/reports/archive/2026-10-12-controlled-dev-1'); a=decide(json.loads((p/'pairs.json').read_text())); b=json.loads((p/'summary.json').read_text()); b.pop('manifest_sha256'); assert a==b; print(a['verdict'])"
uv run pytest -q tests/test_controlled_dev_decision.py tests/test_evidence_path.py
```

The 58 passing regressions cover the frozen decision's improvement threshold,
safety/provenance guards, unknown usage, incomplete runs, verifier rejection and
recovery. They do not substitute DEV for the missing holdout. Trace export uses
SafeTelemetry allow-listed metadata, HMAC identifiers and token filtering; private
raw states/narratives are not published. The final audit also obtained 141 spans
in seven accepted batches for `serene-final-audit-20261012`, with zero drops/errors,
using scripted Maya I/O. No Telegram-specific NeatLogs claim is made.

## Entire: native retrieval and code provenance

Installed **Entire CLI 0.11.4**. The following two existing local native records
were successfully retrieved using `checkpoint explain --json` (metadata only):

| Checkpoint | Real commit containing its trailer | Session / model |
| --- | --- | --- |
| `01M4JMP49DYR5MABPHPD1RPT0J` | `91b4401584e61dfde06956678399aad24d06134f`, runtime #65 | `37110e9a-2a6c-4ced-8ef1-fcb81c3c1b2b`, Claude Code / `claude-opus-5-5` |
| `01M4JGDW740K8ENKH3GYRJEH15` | `60c9dbd57bac32472c4800ed672774b100c3e2e4`, foundation #63 | `961f937d-0fd3-4116-adc7-cc2e1be10075`, Claude Code / `claude-opus-5-5` |

The first record has 12 checkpoints and one session; the second has eight and one
session. These counts are native envelope fields, not counts of covered milestones.
Both commits are real ancestors of merged main. `entire blame` on lines 1–20 of
[observation ingestion](../serene/evidence/ingestion.py) resolves all 20 lines to
the runtime commit/checkpoint/session/model above. Exact read-only commands:

```sh
entire version
entire checkpoint explain 01M4JMP49DYR5MABPHPD1RPT0J --json
entire checkpoint explain 01M4JGDW740K8ENKH3GYRJEH15 --json
entire blame serene/evidence/ingestion.py:1-20 --json
```

Blame output can include prompts; retain it privately or remove prompt fields
before sharing. Session pushing remains disabled. The records exist locally;
public Git trailers alone do not promise native retrieval from a fresh clone.
The #106 trailer `01M4QQAZVG7SQ4Z945Y79916TM` could not be retrieved and is
**not** presented as a retrievable checkpoint. No new checkpoint was fabricated
for this documentation pass. #54's all-eight-milestone criterion remains unmet.

Entire was genuinely used during development. Retrievable historical checkpoint coverage is incomplete; no missing checkpoints were fabricated or retroactively reconstructed.

Genuine available checkpoint/provenance evidence meets the release owner's
hackathon evidence scope; full history rewriting was explicitly out of scope.

## cfo.ai assumed business plan

The genuine saved cfo.ai scenario readback has 71 nonempty cells and no formula
errors. It agrees with the [reproducible model](economics.md) and
[saved readback](economics/cfo-readback.json): approximately **$2.725256 variable
cost per family-month**, **$12 assumed revenue**, **77.28% assumed gross margin**
and **524-day assumed runway**. These are operating assumptions, not production
measurements. `uv run python scripts/economics_report.py --check` reproduces them.
