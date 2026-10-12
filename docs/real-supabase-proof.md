# Hosted Supabase runtime proof — 12 October 2026

This supersedes the blocked hosted acceptance in [the original proof](web-e2e-proof.md).
The existing active healthy `serene-hackathon-e2e` project
(`pfgsidswnccmekqqydly`, `ap-south-1`, PostgreSQL 17) was used. No project was
created or unrelated project modified. The application and production approval
server ran locally; Auth, PostgREST, PostgreSQL and Realtime were hosted Supabase.
The checkout started from merged main `018b5c982a38746a21c612f03a5a5c4280c424ce`.

## Real service evidence

All eight committed Serene migrations are applied, including the current
Memory projection constraint. The five tables exist with RLS enabled:
`domain_events`, `projection_state`, `children`, `child_guardians`, and
`caregiver_grants`. Existing Auth, RLS, grants and publication were inspected;
their product design was preserved. Email/password Auth is enabled; anonymous
Auth is disabled. Authenticated custom-schema requests use `Accept-Profile: serene`.

Three fresh synthetic Auth users and two synthetic children were created.
Each parent has only its own child; the caregiver has only `learnings:read`.
All seeded and subsequent events use `postgres_ledger` and its production
projection publisher. No real family information was used.

| Boundary | Observed result |
| --- | --- |
| Auth UI | `/sign-in` obtains a real session; Parent A's selector contains only child A; Parent B's selector contains only child B. |
| Signed out / session loss | No child data or selector; cross-tab real sign-out clears the original tab and displays `Your session ended`. |
| Data API / RLS | Parent A reads its projections; an unfiltered request contains only A; Parent B gets zero rows for A; caregiver cannot read parent-only projections or select a child in the parent UI. Anonymous request receives 401 / SQLSTATE 42501. |
| Write boundary | Neither anon nor authenticated can insert ledger events; authenticated cannot insert/update/delete projections. Anon has no `serene` schema usage; authenticated does. |
| Publication | `supabase_realtime` publishes only `serene.projection_state`; no `domain_events` publication. |
| Append / Realtime | A normal synthetic kernel append changes PostgreSQL and delivers an actual Supabase `postgres_changes` WebSocket frame with the committed child and sequence. Today updates without reload; Investigations shows the same event. |
| Offline / resync | Browser network disabled; UI displays `Reconnecting`; a backend append remains invisible while offline. Reconnection resyncs to the current projection with one matching heading and no foreign-child frames. |
| Approval | Browser → `/api/approvals` → production `/web/approvals` → real Auth verification → guardian/binding → `WebApprovalChannel` → ledger → PostgreSQL → real Realtime changes the stage to `APPROVED`. Decline reaches `ABANDONED`. |
| No optimistic approval | Actual server `postgres_changes` frames are held using Playwright's server pass-through. The accepted HTTP response leaves `AWAITING_APPROVAL`; releasing those original real frames changes the stage. No Auth, REST, or WebSocket response is fabricated. |
| Refusal / replay | Other parent and caregiver receive 403; stale digest returns `INTERVENTION_DIGEST_MISMATCH` without ledger change; exact browser-request replay returns the same granted result with no second decision. RED has no approve action. |

Final independent `check`: `sequence=55`, `decisions=3`, `verified=true`.
It verifies the real ledger hash chain and that every projection's sequence/hash
equals the ledger head. This includes an earlier approval committed during
timeout diagnosis, followed by the final approval and decline.

The hosted run exposed one genuine bug: the relay's ten-second timeout could
expire after the hosted kernel committed. It now waits up to sixty seconds;
there is a focused regression test for a twenty-second response and the bounded
unavailable case. Auth, RLS, approval admission and transport contracts are unchanged.

## Verification and exact test outcome

- Full pytest: **1,458 passed**, one Windows symlink skip, four Inspect deprecation warnings.
- Ruff lint/format and mypy: passed (293 formatted files; 107 typed source files).
- Inspect: **20/20**; frozen core scenarios **10/10**; Maya **18/18**.
  Canonical Maya report SHA-256 remains
  `4000dac552cca6086d39e352795c2a2c79a0bedc69c823247a08c47173e12c7e`.
- Web typecheck, **245 unit tests**, production build: passed.
- Standard Playwright: **139 passed**, three viewport skips.
- Production relay/test-kernel Playwright: **2 passed**.
- Audit/harness targeted pytest: **24 passed**; relay unit tests: **6 passed**.
- Hosted Playwright: Auth/append/offline/resync and switching/session-loss tests
  passed. The approval test passed HTTP, no-optimism, PostgreSQL, real Realtime,
  refusal, replay and decline assertions, then its last read-only ledger check
  encountered a pooler connection timeout. The identical read-only command was
  rerun successfully and returned the final result above. **The automated hosted
  invocation was 2 passed / 1 failed**, not an entirely green suite.
- Secret/PII, synthetic-data and environment audits: zero findings.
  Ledger self-check: 25 events, valid chain, identical replay and detected tampering.
  Privileged values were scanned against built browser JavaScript: zero matches.

Ignored local logs retain run details; they are not uploaded because real-service
failure artifacts can contain synthetic credentials. Synthetic passwords were
rotated and refresh sessions revoked after the proof. The temporary server DB
login was revoked/dropped and temporary key/DSN files removed. Existing synthetic
append-only evidence is retained; no ledger deletion bypass was introduced.

## Advisors and limitations

Security advisors report **six warnings, no errors**:
two [mutable trigger function search paths](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable),
two [authenticated executable SECURITY DEFINER helpers](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable),
[disabled leaked-password protection](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection),
and [insufficient MFA options](https://supabase.com/docs/guides/auth/auth-mfa).
The existing policy helpers have fixed empty search paths and bind parent/scope
checks to the verified JWT subject, including caregiver expiry/revocation.
Their authenticated execution is intentional. Advisors also report four
[multiple permissive SELECT policy performance warnings](https://supabase.com/docs/guides/database/database-linter?lint=0006_multiple_permissive_policies).
These findings are recorded without redesigning policies or Auth.

This is a synthetic hosted-stack runtime proof with local production application
servers, not evidence of a public application deployment or a production load test.
Intermittent pooler connection timeouts remain an operational limitation.
No canonical Maya semantics, safety/promotion behavior, holdout, frozen evals,
or work on #67/#69 was changed.

## Opt-in reproduction

Use an existing suitably configured project; review its schema and publication
before running. Explicitly supply `SUPABASE_URL`, `SUPABASE_ANON_KEY` and a
server-only `SUPABASE_DB_URL`. Preparing users additionally needs a server-only
`SUPABASE_SERVICE_ROLE_KEY`. Never put these in commits or browser environment.

```text
uv run python -m scripts.web_supabase_e2e prepare
cd app/web
npm run test:e2e:supabase
```

The preparer refuses to overwrite `.demo/web-e2e.json`; preserve an old manifest
before preparing a fresh run. Approval tests consume pending requests, so use
a fresh run when repeating decisions. From the repository root,
`uv run python -m scripts.web_supabase_e2e check` independently verifies the
chain, projection agreement and decision count without an Auth admin key.
Missing configuration fails explicitly. CI requires no hosted credentials.
The web process receives only public Supabase configuration; DB/admin credentials
are removed from its environment. Real-service traces, screenshots and password
form failure snapshots are disabled. Never upload ignored real-service artifacts.

Current references reviewed before changes:
[email/password Auth](https://supabase.com/docs/guides/auth/passwords),
[custom schemas](https://supabase.com/docs/guides/api/using-custom-schemas),
[Postgres Changes](https://supabase.com/docs/guides/realtime/postgres-changes),
[RLS](https://supabase.com/docs/guides/database/postgres/row-level-security),
[explicit API grants changelog](https://supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically),
[Realtime schema lockdown](https://supabase.com/changelog/realtime-schema-locked-down-against-modification).
