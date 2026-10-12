-- Memory review is ledger-only. Memory/Dream adds the immutable Git commit
-- referenced by the ledger. Existing parent-only RLS/publication is unchanged.
alter table serene.projection_state
  drop constraint if exists projection_state_projection_check;
alter table serene.projection_state
  add constraint projection_state_projection_check check (projection in (
    'current_child_state', 'active_investigations', 'active_hypotheses',
    'pending_approvals', 'active_learnings', 'investigations', 'experiments',
    'memory_review', 'memory_dream'
  ));
