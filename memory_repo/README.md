# Serene Memory Repo

Durable memory for Serene, stored as **Git + Markdown**. This is intentionally
not a vector store: memory must be human-readable, diffable, reviewable and
version-controlled. Document format: [SCHEMA.md](SCHEMA.md).

| Directory | Holds | Subject | Minimum level |
| --- | --- | --- | --- |
| `learnings/` | Contextual learnings, with scope + review dates | `lrn_` | 5 CONTEXTUAL_LEARNING |
| `routines/` | Established routines and their contexts | `lrn_` | 5 |
| `patterns/` | Emergent patterns promoted from observations | `pat_` | 2 PATTERN |
| `child/` | Stable facts about the child (diet, sleep, sensitivities, ...) | `pat_` / `lrn_` | 2 |
| `caregivers/` | Caregiver roles and routines (opaque ids, no names) | `pat_` / `lrn_` | 2 |
| `investigations/` | Summaries of investigations | `hyp_` | 3 HYPOTHESIS |
| `decisions/` | Parent-approved interventions | `exp_` with a granted approval | 3 |

The directory fixes the subject kind and the minimum level (`serene/policies/memory_review.py`).
Withdrawing a document (`DEPRECATE`) needs no promotion authority.

## Layers

```
experience  = serene.domain_events (Postgres ledger)        what happened
memory      = this repo (Git + Markdown)                     what Serene remembers
belief      = Causal Twin / investigation state (projections) what Serene believes
```

Belief is rebuilt from the ledger only and never reads these files.

## Write path (single writer)

```
Dream / Agent / Parent  --MEMORY_PATCH_PROPOSED-->  ledger
Critic (deterministic)  --MEMORY_PATCH_REVIEWED-->  ledger   (admission recomputes it)
Memory Committer        prepare commit object -> MEMORY_PATCH_COMMITTED(sha) -> publish
                        or MEMORY_PATCH_REJECTED(reason codes)
```

Only the **Memory Committer** (`serene/memory/committer.py`) writes here, and
only after a passed Critic review that still holds at commit time. Every commit
carries `Serene-Patch-Id`, `Serene-Proposal-Event`, `Serene-Review-Event`,
`Serene-Ledger-Head` and `Serene-Authorization` trailers. Any commit or working
tree edit not recorded in the ledger is reported by the audit and makes reads
fail closed.

The directories in this repository are the layout template. At runtime the
memory repo is a separate Git repository (`SERENE_MEMORY_REPO_PATH`), created
with `GitMemoryRepository.init`.

## MVP constraints

- Simple file read/search; **no embeddings**.
- Patches are full-context diffs with provenance and a Critic verdict.
- A Contextual Learning is only committed with bounded scope and expiry/review,
  and is withdrawn (status marked) when it becomes due for review, needs a
  retest, goes stale or is deprecated.
