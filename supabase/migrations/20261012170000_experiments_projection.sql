-- Experiments read view (#37/#84). The existing parent-only projection RLS
-- boundary and Realtime publication are unchanged. No ledger or registry
-- identity is included in the view payload. Backfill existing children after
-- deploying the new projection code (scripts/rebuild_projections.py).
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
      'experiments'
  ));
