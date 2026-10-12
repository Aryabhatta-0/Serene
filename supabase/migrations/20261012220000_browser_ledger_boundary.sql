-- Browser sessions read projections, never canonical ledger payloads. RLS
-- still scopes backend-mediated reads, but is not a substitute for this grant
-- boundary: raw events carry private identity/source fields intentionally
-- excluded from the web projections. Backend and synthetic-eval grants stay.
revoke select on serene.domain_events from public, authenticated;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'revoke select on serene.domain_events from anon';
  end if;
end;
$$;
