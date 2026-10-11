-- Branch A (feat/runtime-investigation-evidence): extend the closed event
-- vocabulary with the observation / evidence / investigation events added in
-- serene.domain.events. Applied migrations are never edited; this file
-- regenerates the event_type check constraint as the COMPLETE current union
-- (foundation + branch B 20261011090000 + branch A), kept honest by
-- tests/test_migrations.py, which reads the latest definition.
--
--   OBSERVATION_STRUCTURING_FAILED  structured extraction failed; raw evidence untouched
--   EVIDENCE_ACQUISITION_FAILED     one failed, ledger-counted acquisition attempt
--   INVESTIGATION_PHASE_CHANGED     investigation reasoning-loop state machine

alter table serene.domain_events
  drop constraint if exists domain_events_event_type_check;

alter table serene.domain_events
  add constraint domain_events_event_type_check check (event_type in (
      'OBSERVATION_REPORTED',
      'OBSERVATION_STRUCTURED',
      'OBSERVATION_STRUCTURING_FAILED',
      'EVIDENCE_REQUESTED',
      'EVIDENCE_ACQUIRED',
      'EVIDENCE_ACQUISITION_FAILED',
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
      'INVESTIGATION_PHASE_CHANGED',
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
