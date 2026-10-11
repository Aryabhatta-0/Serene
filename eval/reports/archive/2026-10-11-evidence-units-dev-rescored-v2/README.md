# The same runs rescored under runtime-scorers/2 (no model called)

The two live runs archived in `../2026-10-11-evidence-units-dev-v1/`, rescored under
`runtime-scorers/2` and judged by `frozen-regression-gate/2` with the same target and guard
declared for the original gate. Nothing here replaces the v1 report. This is what the
corrected scorer says about the same model outputs.

How it was made (no model call and no network):

1. `eval/runners/replay_live.py` rebuilt each run's ledgers in a worktree at the run's
   own commit (`2a39cad` before, `b3b4f5c` after), serving every model response from the
   run's recorded exchanges. All 12 replays consumed every recorded exchange. Every
   replayed request was byte-identical to the recorded one, and every replayed
   `runtime-scorers/1` score equalled the stored score.
2. `eval/runners/rescore_live.py` read each rebuilt ledger's acquisitions and rescored it.
   It also checked that the frozen v1 rule still reproduces each stored
   `investigation_success`.
3. `eval/runners/regression_gate.py --target
   verifier_rejections.REQUESTED_FIELD_UNSUPPORTED:decrease --guard
   verified_external:increase`.

Result: **FAIL**. The target is met (28 -> 0) and the guard held (0 -> 4). The two burden
"regressions" under v1 disappear: they came from field labels. One DEV violation is
left: `browse_verified` `investigation_success` 0.5 -> 0.25 (retention 1 -> 0). The
holdout was not run. The retention loss comes from hypothesis formation, which runs
before any code the change touched. The two runs already diverge at their first model
call: report structuring got byte-identical input and returned different output. So the
loss is sampling noise the gate cannot separate from a regression at n = 1. The gate
still counts it as a regression, and it is not overridden here.

`*/scores.json` are the gate's inputs (with trajectories). `*/rescore.md` show v1 and v2 side
by side per scenario. `gate/` is the gate's output.

sha256:

```
09edf0b9a0b6c80eebd175114cf2f99605b8aef01cf700ed4f28b9aa5eca82b3 after/rescore.md
c238d18abcfdec023183d8dec1c0f6502fb7f91131a5376199dc02d7a6638d4b after/scores.json
fcc844c5f2db8bcc83778f4553e1b436981c9abbe16fac617097c724bd2da6bd before/rescore.md
8630fdb2c1542a807e8862407cf83a3c12b8ad2649b44f5bbc8d877994e33b14 before/scores.json
1045e9abd11a7dac6b6c0a7de77305b956688791a184110991ef977a9d4179a7 gate/after.json
3324651c91d05709750a15f8c5923c4253636282a4cbe1c31ffa71c53a360446 gate/before.json
f0879f3b2b2308e79327f95d61a26e7570e3186865b2c267d1283500d6bef805 gate/comparison.md
```
