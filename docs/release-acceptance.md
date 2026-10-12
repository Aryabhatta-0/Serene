# Final release acceptance — 12 October 2026

## Final main

Product main after #108: **`6d680369c46232862c32596f79b684fe26fdce95`**.
#108 was merged only after confirming its unchanged head
`156a952b0c14fab35334e65c7b912006bd7355e5`, four successful required checks and
mergeability. Resulting [main CI](https://github.com/Sathvikar01/morrow/actions/runs/38256189243)
also passed all four required jobs. Subsequent acceptance documentation is tracked
by its PR/merge receipt; it changes no runtime, fixture or evaluator.

The release owner explicitly narrowed acceptance to the hackathon evidence
requirements: measured before/after evidence, NeatLogs traces, Entire checkpoints
or graph/provenance evidence, cfo.ai business plan, public repo and a demo of at
most three minutes. The [repository](https://github.com/Sathvikar01/morrow) is public.
This is readiness to record; no completed video or public web deployment is claimed.

Focused confirmation on clean merged product main:

| Check | Result |
| --- | --- |
| Required GitHub CI | 4/4 green |
| Canonical Maya | 18/18; 63 events |
| Domain SHA-256 | `4000dac552cca6086d39e352795c2a2c79a0bedc69c823247a08c47173e12c7e` |
| Frozen handcrafted scenarios | 10/10, fixture unchanged |
| Ledger self-check | Valid chain, identical replay, tamper detected |
| Current secret/PII audit | Zero findings |
| Web production build | PASS |
| Production browser smoke | Seven shipped routes, HTTP 200, no console/page/network errors, no overflow at 390 px, no family fixtures on protected surfaces |
| Hosted login/Realtime repeat | Not repeated: private credentials were deliberately removed after the final audit; earlier hosted production-route proof remains valid for unchanged runtime |
| Archived DEV recount | 76 raw files match archived hashes; unchanged frozen decision reproduces PASS and identical summary |
| Evidence/decision regressions | 58/58 passing |
| Economics reproduction | PASS; assumptions only |

The earlier [full audit](final-release-audit.md) records hosted Auth/RLS/Realtime,
approval, reconnect/resync, Memory/Dream and Twin proof with synthetic records.
It also records the security fixes in #108: denied browser ledger SELECT,
cross-account isolation, Realtime race protection and zero current dependency
findings. No production certification is implied.

## Issues

- [#53](https://github.com/Sathvikar01/morrow/issues/53): the real failure,
  trace diagnosis, reproducible bounded DEV metrics and regression evidence meet
  the clarified acceptance; completion is recorded in its final evidence comment.
- [#54](https://github.com/Sathvikar01/morrow/issues/54): remains OPEN. Two
  retrievable native records and code provenance prove genuine use, while its
  original all-eight-milestone acceptance remains unsatisfied.
- [#61](https://github.com/Sathvikar01/morrow/issues/61): README sections,
  evidence links and reproducible setup satisfy its own acceptance under the
  clarified submission scope; completion is recorded after documentation/link checks.

## Hackathon evidence

- **NeatLogs:** 54/54 accepted controlled DEV suffix exports, a concrete
  failure/correction trace pair and independently reproduced metrics:
  unsupported rejection **62/62 → 3/39**, VERIFIED **0 → 22**, attempts
  **305 → 275**, tokens **4,187,529 → 3,863,797**. All 72 arms parked unresolved;
  #67 remains unmerged. This proves measured evidence-verification improvement,
  not general task superiority. Privacy redaction remains enabled.
- **Entire:** CLI 0.11.4 retrieves two genuine local native records. The strongest
  example maps ingestion code to runtime commit `91b44015`, checkpoint
  `01M4JMP49DYR5MABPHPD1RPT0J`, Claude Code session and model via `entire blame`.
  Unavailable trailers are not represented as retrievable checkpoints.
- **cfo.ai:** genuine saved scenario/readback and reproducible assumed business
  plan: approximately **$2.725256/family-month**, **$12 assumed revenue**,
  **77.28% assumed gross margin**, **524-day assumed runway**.

Exact commands, pair sequence references and boundaries are in
[release evidence](release-evidence.md).

## Remaining limitations

All are **DOES NOT BLOCK SUBMISSION** for the accepted local synthetic presentation:

- Holdout was not run. Controlled DEV evidence is reported only as DEV evidence and is not claimed as a holdout/generalization result.
- #67 remains unmerged; the full research regression gate is not passed.
- Entire was genuinely used during development. Retrievable historical checkpoint coverage is incomplete; no missing checkpoints were fabricated or retroactively reconstructed.
- No fresh Telegram smoke; no Telegram-specific NeatLogs claim.
- Existing empty-plan investigation limitation, metadata/digest-only raw evidence
  exposure and unnamed live graph variables remain explicit.
- No public deployment or production/security certification; accepted/false-positive
  Supabase advisor findings remain as classified in the full audit.
- Canonical Maya external I/O and its full 18-beat scenario are scripted. Hosted
  web transport, NeatLogs acceptance, Entire retrieval and cfo.ai readback are real.

## FINAL VERDICT

**GO — READY TO RECORD**
