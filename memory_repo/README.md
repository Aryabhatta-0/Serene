# Serene Memory Repo

Durable memory for Serene, stored as **Git + Markdown**. This is intentionally
not a vector store: memory must be human-readable, diffable, reviewable and
version-controlled.

| Directory | Holds |
| --- | --- |
| `child/` | Stable facts about the child (diet, sleep, sensitivities, ...) |
| `caregivers/` | Caregiver identities, roles and (separately preserved) reports |
| `routines/` | Established routines and their contexts |
| `patterns/` | Emergent patterns promoted from observations |
| `investigations/` | Summaries and resolutions of past investigations |
| `decisions/` | Parent decisions and accepted interventions |
| `learnings/` | Contextual learnings (Level 5), with scope + review dates |

## Write path

Only the **single-writer Memory Committer** (#32) may modify these files.
Investigation (#9-#21), Dreaming (#30) and parents may only *propose patches*.
Every Dream produces a proposed patch with a diff; nothing is rewritten silently.

## MVP constraints

- Simple file read/search; **no embeddings**.
- Patches are diffs with provenance and a Promotion Gate verdict.
- A Contextual Learning is only committed with bounded scope and expiry/review.
