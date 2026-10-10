-- Serene immutable domain event ledger (issues #3, #4, #5) and disposable
-- projection storage (issue #6).
--
-- Invariants enforced here (defence in depth; the kernel enforces them first):
--   * append-only: UPDATE / DELETE / TRUNCATE on domain_events always fail;
--   * per-child hash chain linkage: sequence is gapless from 1 and
--     prev_event_hash equals the previous event's event_hash;
--   * closed event vocabulary (kept in sync with serene.domain.events.EventType
--     by tests/test_migrations.py);
--   * RLS enabled with no end-user policies: deny by default until issue #8
--     adds parent/caregiver-scoped policies. Only the service role (which
--     bypasses RLS) and the owner can read or append.
-- Hash *values* are recomputed and verified by the kernel (verify_hash_chain);
-- the database guarantees that history cannot be rewritten through SQL DML.

create schema if not exists serene;

create table serene.domain_events (
  event_id            text        primary key check (event_id ~ '^evt_[0-9a-f]{32}$'),
  child_id            text        not null check (child_id ~ '^chd_[0-9a-f]{32}$'),
  sequence            bigint      not null check (sequence >= 1),
  event_type          text        not null check (event_type in (
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
      'MEMORY_PATCH_REJECTED'
  )),
  schema_version      integer     not null check (schema_version >= 1),
  hash_version        integer     not null check (hash_version = 1),
  source              jsonb       not null,
  actor               jsonb       not null,
  actor_kind          text        generated always as (actor ->> 'kind') stored,
  occurred_at         timestamptz not null,
  recorded_at         timestamptz not null,
  derived_from        text[]      not null default '{}',
  verification_status text        not null check (verification_status in
                        ('UNVERIFIED', 'VERIFIED', 'REJECTED', 'NOT_APPLICABLE')),
  payload             jsonb       not null,
  prev_event_hash     text        not null check (prev_event_hash ~ '^[0-9a-f]{64}$'),
  payload_hash        text        not null check (payload_hash ~ '^[0-9a-f]{64}$'),
  event_hash          text        not null unique check (event_hash ~ '^[0-9a-f]{64}$'),
  inserted_at         timestamptz not null default now(),
  constraint domain_events_child_sequence_key unique (child_id, sequence),
  constraint domain_events_child_prev_hash_key unique (child_id, prev_event_hash)
);

create index domain_events_child_type_idx on serene.domain_events (child_id, event_type);

comment on table serene.domain_events is
  'Append-only, per-child hash-chained Serene ledger. Truth. Never updated or deleted.';

-- Chain linkage on insert ----------------------------------------------------
create or replace function serene.enforce_chain_link() returns trigger
language plpgsql as $$
declare
  head_sequence bigint;
  head_hash     text;
begin
  select e.sequence, e.event_hash into head_sequence, head_hash
    from serene.domain_events e
   where e.child_id = new.child_id
   order by e.sequence desc
   limit 1;

  if head_sequence is null then
    if new.sequence <> 1 or new.prev_event_hash <> repeat('0', 64) then
      raise exception 'serene ledger: first event must have sequence 1 and genesis prev hash'
        using errcode = 'check_violation';
    end if;
  elsif new.sequence <> head_sequence + 1 or new.prev_event_hash <> head_hash then
    raise exception 'serene ledger: event does not extend the chain head'
      using errcode = 'check_violation';
  end if;

  foreach head_hash in array new.derived_from loop
    if not exists (
      select 1 from serene.domain_events a
       where a.event_id = head_hash and a.child_id = new.child_id
    ) then
      raise exception 'serene ledger: unknown ancestor %', head_hash
        using errcode = 'foreign_key_violation';
    end if;
  end loop;
  return new;
end;
$$;

create trigger domain_events_chain_link
  before insert on serene.domain_events
  for each row execute function serene.enforce_chain_link();

-- Append-only ------------------------------------------------------------------
create or replace function serene.reject_ledger_mutation() returns trigger
language plpgsql as $$
begin
  raise exception 'serene ledger is append-only: % is not permitted', tg_op
    using errcode = 'insufficient_privilege';
end;
$$;

create trigger domain_events_no_update
  before update on serene.domain_events
  for each row execute function serene.reject_ledger_mutation();

create trigger domain_events_no_delete
  before delete on serene.domain_events
  for each row execute function serene.reject_ledger_mutation();

create trigger domain_events_no_truncate
  before truncate on serene.domain_events
  for each statement execute function serene.reject_ledger_mutation();

-- Disposable projection state --------------------------------------------------
create table serene.projection_state (
  child_id        text        not null check (child_id ~ '^chd_[0-9a-f]{32}$'),
  projection      text        not null check (projection in (
      'current_child_state',
      'active_investigations',
      'active_hypotheses',
      'pending_approvals',
      'active_learnings'
  )),
  state           jsonb       not null,
  last_sequence   bigint      not null check (last_sequence >= 0),
  last_event_hash text        not null check (last_event_hash ~ '^[0-9a-f]{64}$'),
  rebuilt_at      timestamptz not null default now(),
  primary key (child_id, projection)
);

comment on table serene.projection_state is
  'Disposable read state rebuilt by replaying serene.domain_events. Never authoritative.';

-- Access boundary: deny by default ---------------------------------------------
alter table serene.domain_events enable row level security;
alter table serene.projection_state enable row level security;

revoke all on schema serene from public;
revoke all on all tables in schema serene from public;

do $$
declare
  r text;
begin
  foreach r in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke all on schema serene from %I', r);
      execute format('revoke all on all tables in schema serene from %I', r);
    end if;
  end loop;
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    execute 'grant usage on schema serene to service_role';
    execute 'grant select, insert on serene.domain_events to service_role';
    execute 'revoke update, delete, truncate on serene.domain_events from service_role';
    execute 'grant select, insert, update, delete on serene.projection_state to service_role';
  end if;
end;
$$;
