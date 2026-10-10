# Memory document format (`serene_memory: 1`)

Code: `serene/memory/document.py` (render / strict parse), `serene/memory/diff.py`.

```markdown
---
serene_memory: 1
kind: learning
subject: lrn_<32 hex>
level: CONTEXTUAL_LEARNING
status: ACTIVE
scope: daycare_pickup, weekday_evening
valid_from: 2026-09-01T08:43:00.000000Z
review_after: 2026-10-31T08:43:00.000000Z
sources: evd_<32 hex>, evd_<32 hex>
counterevidence:
---

# A five-minute heads-up helps weekday pickups

On weekday daycare pickups, a five-minute heads-up before leaving went calmly.
```

| Field | Filled by | Checked by the Critic against |
| --- | --- | --- |
| `kind` | directory | `serene/memory/rules.py` |
| `subject` | Dreamer's choice, must exist | ledger entity; must be in the patch's `derived_from` |
| `level` | code | subject's ledger level |
| `status` | code | effective status (learnings: time + validity signals) |
| `scope` | code | subject scope |
| `valid_from` / `review_after` | code | learning validity window |
| `sources` | code | raw evidence the subject rests on (complete, verified lineage) |
| `counterevidence` | code | every contradicting / inconclusive outcome, counter-evidence and counter-observation in the ledger |
| title, body | Dreamer (may be a model) | free text; carries no authority |

Rules: keys in exactly this order, no others; LF line endings; trailing
newline; the parser rejects anything that does not re-render byte-identically.

## Patches

`MemoryPatch.diff` is a **single-hunk, full-context unified diff** (every
unchanged line is context), so both the old and the new file are reconstructible
from the diff alone:

```diff
--- /dev/null
+++ b/learnings/pickup-heads-up.md
@@ -0,0 +1,16 @@
+---
+serene_memory: 1
...
```

`CREATE` diffs start from `/dev/null` with no `base_revision`; `UPDATE` and
`DEPRECATE` carry the file's current commit as `base_revision`, and the
committer refuses them if the file or its pre-image changed (`STALE_BASE_REVISION`,
`PRE_IMAGE_MISMATCH`). `required_level` must equal the directory minimum
(`RAW_EVIDENCE` for `DEPRECATE`).
