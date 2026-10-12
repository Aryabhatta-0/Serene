-- Serene: the `causal_twin` read projection. Applied migrations are never
-- edited; this regenerates the projection check constraint as the COMPLETE
-- current list, kept honest by tests/test_migrations.py, which reads the
-- latest definition.
--
--   causal_twin  the Causal Twin as the web shows it (serene/causal/web.py):
--                variables, edges with the kernel's verdicts, and the complete
--                provenance projection of every edge (#75), as of the head
--                event, with no child, actor or source ids
--
-- Rows stay disposable read state rebuilt from the ledger. RLS is unchanged:
-- parents read their children's projection rows; caregivers read only
-- active_learnings, so this projection is parent-only.

alter table serene.projection_state
  drop constraint if exists projection_state_projection_check;

alter table serene.projection_state
  add constraint projection_state_projection_check check (projection in (
      'current_child_state',
      'active_investigations',
      'active_hypotheses',
      'pending_approvals',
      'active_learnings',
      'investigations',
      'experiments',
      'memory_review',
      'memory_dream',
      'causal_twin'
  ));
