-- Branch B event vocabulary (experiment / memory blocks).
--
-- Regenerates the closed event_type check on serene.domain_events after adding
-- EXPERIMENT_OUTCOME_TIMED_OUT, MEMORY_PATCH_REVIEWED and
-- MEMORY_DREAM_STAGE_RECORDED. The foundation migration is never edited; the
-- most recent definition of this constraint is the one in force and is kept in
-- sync with serene.domain.events.EventType by tests/test_migrations.py.
-- Whoever merges second regenerates this list again (docs/parallel-handoff.md).

alter table serene.domain_events
  drop constraint domain_events_event_type_check;

alter table serene.domain_events
  add constraint domain_events_event_type_check check (event_type in (
      'OBSERVATION_REPORTED',
      'OBSERVATION_STRUCTURED',
      'EVIDENCE_REQUESTED',
      'EVIDENCE_ACQUIRED',
      'EVIDENCE_VERIFIED',
      'EVIDENCE_REJECTED',
      'PATTERN_PROPOSED',
      'HYPOTHESIS_PROPOSED',
      'HYPOTHESIS_SUPERSEDED',
      'HYPOTHESIS_REFUTED',
      'PROMOTION_REQUESTED',
      'PROMOTION_GRANTED',
      'PROMOTION_DENIED',
      'INVESTIGATION_OPENED',
      'INVESTIGATION_STATUS_CHANGED',
      'EXPERIMENT_PROPOSED',
      'EXPERIMENT_CLASSIFIED',
      'EXPERIMENT_BLOCKED',
      'EXPERIMENT_STARTED',
      'TRIAL_RECORDED',
      'OUTCOME_REPORTED',
      'EXPERIMENT_COMPLETED',
      'EXPERIMENT_ABANDONED',
      'EXPERIMENT_OUTCOME_TIMED_OUT',
      'APPROVAL_REQUESTED',
      'APPROVAL_NUDGED',
      'APPROVAL_GRANTED',
      'APPROVAL_REJECTED',
      'APPROVAL_TIMED_OUT',
      'LEARNING_RECORDED',
      'LEARNING_STATUS_CHANGED',
      'LEARNING_SUPERSEDED',
      'MEMORY_PATCH_PROPOSED',
      'MEMORY_PATCH_COMMITTED',
      'MEMORY_PATCH_REJECTED',
      'MEMORY_PATCH_REVIEWED',
      'MEMORY_DREAM_STAGE_RECORDED'
  ));
