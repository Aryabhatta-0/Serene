# Failing gate report, evidence units on the dev split (runtime-scorers/1)

Kept unchanged as the record of what the frozen regression gate
(`frozen-regression-gate/1`) decided before `runtime-scorers/2` changed what
`investigation_success` measures. Do not regenerate or edit these files. A later rescoring
goes next to them, never over them.

* change judged: PR #67 evidence units (`b3b4f5c`) against its harness-only base (`2a39cad`)
* live runs: `dev-before-20261011T035830Z` (2a39cad), `dev-after-20261011T043846Z` (b3b4f5c),
  one run per dev scenario, `deepseek-v4.1-flash` through Hermes v0.21.6, clean trees
* scorers: `runtime-scorers/1`, `trust-scorers/1`
* gate: target `verifier_rejections.REQUESTED_FIELD_UNSUPPORTED:decrease` (28 -> 0, met),
  guard `verified_external:increase` (0 -> 4, held), verdict **FAIL** (three DEV
  `investigation_success` drops; no holdout run)
* write-up: `docs/live-eval-2026-10-11-evidence-units.md` on the PR #67 branch

`gate/` holds the gate's own output. `dev-*/` hold its inputs (`scores.json`), the run
manifests and the run tables, copied byte-for-byte from `eval/reports/local/`. Raw model
exchanges and traces stay local.

sha256:

```
7a0d15f294df07c7dab0726dd3fc450fecd03bae807df830839f5b658158892f dev-after-20261011T043846Z/manifest.json
5943e889abe3cedc10b9e626d31fe2dbd35889efb119bfd33a9a17f1a6882c67 dev-after-20261011T043846Z/scores.json
dced89e32dfbac56ec24eae6866f22be69a4655937ad5a9248725dc3db5c28be dev-after-20261011T043846Z/table.md
614d9ff05495e1c7d77760d521363110fc12ade44d6b7171517b4720f84d16d0 dev-before-20261011T035830Z/manifest.json
c9f5e951b68f5e4991b8aa8b2063c8d90c61c64723eb5ffd4a4f5d5ddd988a38 dev-before-20261011T035830Z/scores.json
3ef2dbe45dadd3eaa4108b84deed2e744f70cfc246e3f60999f94db3d9c2c83b dev-before-20261011T035830Z/table.md
091ac7e912ecfda4c9f92bac2805023f390fec7145081fbdd24a162d55f45cae gate/after.json
9ec0a6d15f2d5fea583888299b45ae6c2e047da0610015357fce5c4404e52e66 gate/before.json
732975d4b8f8a940a2eeb515f68af31514df0302d0f86cb954775076b8cb45c7 gate/comparison.md
```
