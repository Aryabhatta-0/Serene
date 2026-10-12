# Live Memory/Dream (#99)

The ledger-only `memory_review` projection is a deterministic fold of verified
kernel state. The separately built `memory_dream` projection joins that state to
an immutable Git snapshot. It includes the existing `memory-dream-view/1` fields:
ledger head, memory head, kept documents (status, scope, review dates, provenance
and per-file writing revision), unreadable paths, Dream stages and proposed,
committed and rejected patches with their review results and refusal reasons.

## Snapshot rule

The snapshot revision is the last `MEMORY_PATCH_COMMITTED.commit_sha` in ledger
order. The committer prepares this immutable commit object, records the SHA in
the admitted event, and then compare-and-set publishes the Git branch. The
projection hook may read the prepared object after that event; it never reads
the branch or uncommitted worktree. Reviews/rejections/proposals can publish new
ledger detail against the same snapshot. Before the first recorded commit,
documents are explicitly empty and `memory_head` is forty zeroes (no Git commit).
Before any Memory/Dream activity, the empty `memory_review` row signals empty UI.

The snapshot adapter accepts full 40-character commit ids only. A symbolic ref,
wrong returned revision, missing repository or unavailable commit fails clearly;
there is no HEAD fallback. The complete batch is built and privacy-checked before
the projection transaction, so a failed rebuild (including `--replace`) leaves
existing rows intact. A failed append hook never rolls back the admitted event;
telemetry records its error type and backfill repairs the read side.

Retain all Git objects referenced by the ledger, including prepared objects
left unreachable by an interrupted branch publish. Git garbage collection must
not prune those objects. Recover them from the memory repository backup if lost;
replay cannot invent missing bytes. This does not change committer authority,
admission, review policy, evaluation or Maya semantics.

## Deployment and rebuild

Apply `20261012200000_memory_projection.sql`. The backend's existing
`SERENE_MEMORY_REPO_PATH` points to a repository **root directory** for the live
publisher: each child's Git repository is at `<root>/<child_id>`. It must be the
same repository used by that child's committer. Single-repository operators must
place their repository in that child-scoped directory before enabling this
publisher. No repository path, child id or service credential is sent in payloads.
Tests and embedded callers can inject an explicit `(child_id, commit_sha)` snapshot
resolver into `postgres_ledger` / `backfill_projections`.

With the backend quiet after deploying the projection definition:

```sh
uv run python scripts/rebuild_projections.py --replace
```

The command verifies each ledger chain and resolves the recorded commit before
writing rows. Missing Git input produces a code-only failure, never a success
with empty documents. It never appends events. Pure `rebuild_projections(events)`
still rebuilds only ledger projections; `backfill_projections` explicitly adds
the versioned Git input. Repeating either at the same ledger/Git revisions yields
identical canonical payloads regardless of current HEAD.

## Web

`/memory` → `LiveMemory` → signed-in parent's selected child from `FamilyRecord`
→ existing RLS-scoped projection snapshot/Realtime feed → validated Memory view.
The UI shows loading, live, reconnecting (last published data), empty, error and
no session/no child states. A missing Memory/Dream row after activity is an error.
Child changes remount and discard previous data; reconnect takes a new snapshot.
The route imports no fixture. `/demo/maya` keeps its existing canonical source.

No production database migration, repository relocation or backfill is performed
by merging code. Operators must apply the migration and supply the retained Git
repositories before live families can see populated memory.
