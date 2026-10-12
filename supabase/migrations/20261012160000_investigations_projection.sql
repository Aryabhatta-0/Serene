-- Serene: the `investigations` read projection (issue #35). Applied migrations
-- are never edited; this regenerates the projection check constraint as the
-- COMPLETE current list, kept honest by tests/test_migrations.py, which reads
-- the latest definition.
--
--   investigations  question, phase, hypotheses, evidence requests (selected
--                   source, predictions, verification), explicit uncertainty
--                   and the next action from serene.policies.investigation
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
      'investigations'
  ));
