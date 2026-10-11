-- Serene: stream disposable projection state to the web app (issue #33).
--
-- The web app reads projection state only, never the immutable ledger. On
-- Supabase, Realtime streams the tables in the `supabase_realtime`
-- publication, and checks each change against the subscriber's RLS SELECT
-- policies (issue #8: parents read their own children's rows; caregivers only
-- what they were granted). This adds serene.projection_state to that
-- publication and nothing else: serene.domain_events is never published.
--
-- Plain Postgres (tests, local) has no such publication; then this is a no-op.
-- No grant, policy or role changes.

do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime')
     and not exists (
       select 1 from pg_publication_tables
       where pubname = 'supabase_realtime'
         and schemaname = 'serene'
         and tablename = 'projection_state'
     )
  then
    execute 'alter publication supabase_realtime add table serene.projection_state';
  end if;
end;
$$;
