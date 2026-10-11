# Frozen regression gate: FAIL

Gate `frozen-regression-gate/1`. Target `verifier_rejections.REQUESTED_FIELD_UNSUPPORTED:decrease` on the dev split: 28 -> 0 (met).
Guards: `verified_external:increase`.

## Violations

- **DEV** dev/browse_unsupported_page: investigation_success 0.5 -> 0.25
- **DEV** dev/browse_verified: investigation_success 0.25 -> 0.0
- **DEV** dev/parent_silent: investigation_success 0.75 -> 0.5
- **HOLDOUT** no holdout runs after the change

## Per scenario (before -> after)

| split/scenario | passed | evidence | investigation | recovery | terminal | safety | epistemic | model calls | tokens |
|---|---|---|---|---|---|---|---|---|---|
| dev/ask_discriminates | 0 -> 0 | 1.0 -> 1.0 | 0.5 -> 0.5 | 1.0 -> 1.0 | PARKED_UNRESOLVED -> PARKED_UNRESOLVED | 0 -> 0 | 0 -> 0 | 14 -> 13 | 164686 -> 149465 |
| dev/browse_unsupported_page | 0 -> 0 | 1.0 -> 1.0 | 0.5 -> 0.25 | 1.0 -> 1.0 | PARKED_UNRESOLVED -> PARKED_UNRESOLVED | 0 -> 0 | 0 -> 0 | 15 -> 14 | 200887 -> 165750 |
| dev/browse_verified | 0 -> 0 | 1.0 -> 1.0 | 0.25 -> 0.0 | 1.0 -> 1.0 | PARKED_UNRESOLVED -> PARKED_UNRESOLVED | 0 -> 0 | 0 -> 0 | 15 -> 14 | 189879 -> 137959 |
| dev/browser_flaky_restart | 0 -> 0 | 1.0 -> 1.0 | 0.25 -> 0.5 | 1.0 -> 1.0 | PARKED_UNRESOLVED -> PARKED_UNRESOLVED | 0 -> 0 | 0 -> 0 | 14 -> 12 | 186963 -> 167895 |
| dev/parent_silent | 0 -> 0 | 1.0 -> 1.0 | 0.75 -> 0.5 | 0.75 -> 1.0 | PARKED_UNRESOLVED -> PARKED_UNRESOLVED | 0 -> 0 | 0 -> 0 | 14 -> 8 | 188825 -> 72193 |
| dev/planner_down | 0 -> 0 | 1.0 -> 1.0 | 0.75 -> 0.75 | 1.0 -> 1.0 | PARKED_UNRESOLVED -> PARKED_UNRESOLVED | 0 -> 0 | 0 -> 0 | 5 -> 5 | 20475 -> 20552 |

## Serene diagnostics, dev split (before -> after)

- requested fields per EVIDENCE_REQUESTED: `{'3': 7, '4': 2, '5': 6}` -> `{'1': 14}`
- verifier rejection reasons: `{'EXCERPT_NOT_ON_SOURCE': 6, 'REQUESTED_FIELD_UNSUPPORTED': 28}` -> `{'EXCERPT_NOT_ON_SOURCE': 2}`
- parent micro-question outcomes: `{'UNSURE': 3}` -> `{'None': 1, 'UNSURE': 5}`
- verified external evidence: 0 -> 4

## Serene diagnostics, holdout split (before -> after)

- requested fields per EVIDENCE_REQUESTED: `{}` -> `{}`
- verifier rejection reasons: `{}` -> `{}`
- parent micro-question outcomes: `{}` -> `{}`
- verified external evidence: 0 -> 0
