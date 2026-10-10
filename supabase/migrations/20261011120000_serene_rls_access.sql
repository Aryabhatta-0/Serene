-- Serene access boundary (issue #8): parent-owned child data, explicitly scoped
-- caregiver access, an isolated service-role backend path and synthetic-only
-- evaluation access. Adds policies on top of the deny-by-default foundation
-- (20261010120000); never edits it.
--
--   parent     reads everything about a child they are a guardian of;
--   caregiver  reads only the event families a parent explicitly granted, for
--              that child only, until the grant expires or is revoked;
--   backend    service_role (BYPASSRLS in Supabase) is the only writer of the
--              ledger and of guardianship; end users never insert ledger rows;
--   evaluation serene_eval reads SYNTHETIC children only.
--
-- End-user identity is the JWT `sub` claim (what Supabase's auth.uid() reads),
-- resolved by serene.request_user_id() so this file also runs on plain Postgres.

-- Roles ------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'serene_eval') then
    create role serene_eval nologin;
  end if;
end;
$$;

-- Registry ---------------------------------------------------------------------
create table serene.children (
  child_id    text        primary key check (child_id ~ '^chd_[0-9a-f]{32}$'),
  data_class  text        not null check (data_class in ('REAL', 'SYNTHETIC')),
  created_at  timestamptz not null default now()
);

comment on table serene.children is
  'Child registry. data_class = SYNTHETIC marks evaluation/test data; only those rows are visible to serene_eval.';

create table serene.child_guardians (
  child_id   text        not null references serene.children (child_id),
  user_id    uuid        not null,
  role       text        not null check (role = 'PARENT'),
  created_at timestamptz not null default now(),
  primary key (child_id, user_id)
);

comment on table serene.child_guardians is
  'Parent ownership. Written only by the backend (service role) after identity verification.';

create table serene.caregiver_grants (
  grant_id     uuid        primary key default gen_random_uuid(),
  child_id     text        not null references serene.children (child_id),
  caregiver_id uuid        not null,
  scope        text        not null check (scope in
                 ('observations:read', 'experiments:read', 'learnings:read')),
  granted_by   uuid        not null,
  granted_at   timestamptz not null default now(),
  expires_at   timestamptz not null,
  revoked_at   timestamptz,
  constraint caregiver_grants_not_self check (caregiver_id <> granted_by),
  constraint caregiver_grants_bounded check (
    expires_at > granted_at and expires_at <= granted_at + interval '180 days'
  )
);

create index caregiver_grants_lookup_idx
  on serene.caregiver_grants (child_id, caregiver_id, scope);

comment on table serene.caregiver_grants is
  'Explicit, narrow, expiring caregiver scopes granted by a parent. Revocation only sets revoked_at.';

-- Identity and scope helpers ----------------------------------------------------
create or replace function serene.request_user_id() returns uuid
language sql stable set search_path = '' as $$
  select nullif(
    coalesce(
      nullif(current_setting('request.jwt.claim.sub', true), ''),
      nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub'
    ),
    ''
  )::uuid
$$;

create or replace function serene.is_parent(p_child_id text) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from serene.child_guardians g
     where g.child_id = p_child_id
       and g.role = 'PARENT'
       and g.user_id = serene.request_user_id()
  )
$$;

create or replace function serene.has_caregiver_scope(p_child_id text, p_scope text)
returns boolean
language sql stable security definer set search_path = '' as $$
  select p_scope is not null and exists (
    select 1 from serene.caregiver_grants c
     where c.child_id = p_child_id
       and c.scope = p_scope
       and c.caregiver_id = serene.request_user_id()
       and c.revoked_at is null
       and c.expires_at > now()
  )
$$;

-- Which caregiver scope (if any) covers an event type. Approvals, evidence,
-- hypotheses, promotions and memory are parent-only.
create or replace function serene.event_scope(p_type text) returns text
language sql immutable set search_path = '' as $$
  select case
    when p_type in ('OBSERVATION_REPORTED', 'OBSERVATION_STRUCTURED')
      then 'observations:read'
    when p_type in (
      'EXPERIMENT_PROPOSED', 'EXPERIMENT_CLASSIFIED', 'EXPERIMENT_BLOCKED',
      'EXPERIMENT_STARTED', 'TRIAL_RECORDED', 'OUTCOME_REPORTED',
      'EXPERIMENT_COMPLETED', 'EXPERIMENT_ABANDONED', 'EXPERIMENT_OUTCOME_TIMED_OUT'
    ) then 'experiments:read'
    when p_type in ('LEARNING_RECORDED', 'LEARNING_STATUS_CHANGED', 'LEARNING_SUPERSEDED')
      then 'learnings:read'
    else null
  end
$$;

create or replace function serene.is_synthetic(p_child_id text) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from serene.children ch
     where ch.child_id = p_child_id and ch.data_class = 'SYNTHETIC'
  )
$$;

revoke all on function serene.request_user_id() from public;
revoke all on function serene.is_parent(text) from public;
revoke all on function serene.has_caregiver_scope(text, text) from public;
revoke all on function serene.event_scope(text) from public;
revoke all on function serene.is_synthetic(text) from public;
grant execute on function serene.request_user_id() to authenticated;
grant execute on function serene.is_parent(text) to authenticated;
grant execute on function serene.has_caregiver_scope(text, text) to authenticated;
grant execute on function serene.event_scope(text) to authenticated;
grant execute on function serene.is_synthetic(text) to serene_eval;

-- Row level security ---------------------------------------------------------------
alter table serene.children enable row level security;
alter table serene.child_guardians enable row level security;
alter table serene.caregiver_grants enable row level security;

-- Ledger: read-only for end users, filtered per child and per scope.
create policy domain_events_parent_read on serene.domain_events
  for select to authenticated
  using (serene.is_parent(child_id));

create policy domain_events_caregiver_read on serene.domain_events
  for select to authenticated
  using (serene.has_caregiver_scope(child_id, serene.event_scope(event_type)));

create policy domain_events_eval_synthetic_read on serene.domain_events
  for select to serene_eval
  using (serene.is_synthetic(child_id));

-- Projections: parents; caregivers with learnings:read see active learnings only.
create policy projection_state_parent_read on serene.projection_state
  for select to authenticated
  using (serene.is_parent(child_id));

create policy projection_state_caregiver_read on serene.projection_state
  for select to authenticated
  using (
    projection = 'active_learnings'
    and serene.has_caregiver_scope(child_id, 'learnings:read')
  );

create policy projection_state_eval_synthetic_read on serene.projection_state
  for select to serene_eval
  using (serene.is_synthetic(child_id));

-- Registry rows: visible to their parent or to a caregiver with any live grant.
create policy children_parent_read on serene.children
  for select to authenticated
  using (serene.is_parent(child_id));

create policy children_caregiver_read on serene.children
  for select to authenticated
  using (
    serene.has_caregiver_scope(child_id, 'observations:read')
    or serene.has_caregiver_scope(child_id, 'experiments:read')
    or serene.has_caregiver_scope(child_id, 'learnings:read')
  );

create policy children_eval_synthetic_read on serene.children
  for select to serene_eval
  using (data_class = 'SYNTHETIC');

create policy child_guardians_self_read on serene.child_guardians
  for select to authenticated
  using (user_id = serene.request_user_id());

-- Grants: the parent issues and revokes; the caregiver sees their own grants.
create policy caregiver_grants_parent_read on serene.caregiver_grants
  for select to authenticated
  using (serene.is_parent(child_id));

create policy caregiver_grants_caregiver_read on serene.caregiver_grants
  for select to authenticated
  using (caregiver_id = serene.request_user_id());

create policy caregiver_grants_parent_insert on serene.caregiver_grants
  for insert to authenticated
  with check (
    serene.is_parent(child_id)
    and granted_by = serene.request_user_id()
    and caregiver_id <> serene.request_user_id()
    and revoked_at is null
  );

create policy caregiver_grants_parent_revoke on serene.caregiver_grants
  for update to authenticated
  using (serene.is_parent(child_id) and revoked_at is null)
  with check (serene.is_parent(child_id) and revoked_at is not null);

-- Privileges -------------------------------------------------------------------
revoke all on serene.children, serene.child_guardians, serene.caregiver_grants from public;

grant usage on schema serene to authenticated, serene_eval;
grant select on serene.domain_events, serene.projection_state to authenticated;
grant select on serene.children, serene.child_guardians, serene.caregiver_grants
  to authenticated;
grant insert (child_id, caregiver_id, scope, granted_by, expires_at)
  on serene.caregiver_grants to authenticated;
grant update (revoked_at) on serene.caregiver_grants to authenticated;
grant select on serene.domain_events, serene.projection_state, serene.children to serene_eval;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'revoke all on serene.children, serene.child_guardians, serene.caregiver_grants from anon';
  end if;
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    execute 'grant select, insert, update on serene.children, serene.child_guardians, '
            'serene.caregiver_grants to service_role';
    execute 'grant execute on function serene.request_user_id(), serene.is_parent(text), '
            'serene.has_caregiver_scope(text, text), serene.event_scope(text), '
            'serene.is_synthetic(text) to service_role';
  end if;
end;
$$;
