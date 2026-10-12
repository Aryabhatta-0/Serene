# Auth, Realtime and approval proof — 12 October 2026

> Historical implementation evidence. The hosted blocker and remaining #87
> acceptance below are superseded by [the real Supabase runtime proof](real-supabase-proof.md).

The final implementation lane proves the existing `experiments-view/1` contract
through the production projection publisher and authenticated selected child.
PR #100 merged during this lane's CI run; its projection, migration, empty-row
behavior and regenerated web fixture are preserved. This lane adds the shipped-page
HTTP/PostgreSQL proof, the opt-in real-stack runner, and clears child-specific
decision state on selection changes while disabling decisions during reconnects.
It preserves auth/selection (#94) and approval transport (#98). It changes no
policy, eval protocol, holdout or frozen eval fixture.

## Environment and acceptance boundary

Real Supabase could not be exercised on this host. Neither the Supabase CLI nor
the connected account lists a Serene project, the checkout has no project-ref
link, and no Supabase URL/key/database variables are configured. Local
`supabase start` fails when opening `//./pipe/docker_engine`: the pipe does not
exist. Docker Desktop is not installed at its standard path. No unrelated
hosted project was resumed, linked or modified, and no credentials were invented.

Local PostgreSQL from `pgserver` works. The migration, publisher and RLS tests
and the browser-to-test-kernel proof run against disposable databases. Every
test record/child is synthetic. Auth responses and WebSocket delivery in the
test-kernel lane are stand-ins; they are **not** real Supabase Auth/Realtime proof.

| Issue | Evidence | Remaining acceptance |
| --- | --- | --- |
| #87 | Existing UI/session tests; real PostgreSQL publisher/RLS; opt-in real suite added | Real Supabase sign-in, scoped reads, Realtime append, network drop and resync remain blocked |
| #84 | Shipped UI → same-origin relay → production HTTP boundary, session-verifier code, guardian/binding resolution, channel, admission and PostgreSQL projection; positive and adversarial tests | Listed test-kernel criteria covered; actual Supabase session verification remains part of the blocked real-stack proof |
| #37 | Existing all-stage render tests plus live selected-child projection and browser approve/decline; RED blocked; no optimistic stage changes | Listed UI criteria covered against the test kernel |

Keep #87 open until the real boundary has been exercised. #84 explicitly accepts
a test-kernel Playwright proof; #37's render/lifecycle/RED criteria are covered
by that lane and the component tests. Their closure can cite that evidence
after merge, without claiming real Supabase Auth/Realtime acceptance.

## Test-kernel browser path

Run `npm run test:e2e:approvals` in `app/web`. It builds the shipped pages and
runs `tests/web_approval_server.py` on loopback. The browser signs in at
`/sign-in?next=/experiments`, using the production Supabase client against a
synthetic Auth service. It then follows:

`/experiments` → `POST /api/approvals` → `POST /web/approvals` →
`SupabaseSessionVerifier` (synthetic Auth response) → `PostgresGuardianRegistry`
+ `WebBindings` → `WebApprovalChannel` → `EventLedger` admission →
`postgres_ledger` publisher → `serene.projection_state` → UI.

The test holds WebSocket delivery after a real accepted HTTP decision. The UI
still says `AWAITING_APPROVAL`; only delivering the actual newer PostgreSQL
projection changes it to `APPROVED`. Decline similarly reaches `ABANDONED`.
It also verifies no RED action, RED refusal, stale digest, understated AMBER,
too-early AMBER, forged session, other-parent/caregiver refusal and replay without
a second decision. The ledger hash chain is checked at the end. Existing kernel
adversarial tests cover RED refusal at admission and replay after cache restart.

The fixture service is a tests-only module, binds loopback only, creates a
fresh disposable database, and is never imported or routed by the application.
CI runs this lane inside the existing required Web E2E check.

## Local validation

These initial counts precede integration with concurrently merged #100. The
final combined head must pass all four required CI checks again.

- Full pytest: 1,425 passed, one Windows symlink-permission skip. The subsequently
  added preparer test passed separately (one additional test).
- Ruff lint/format and mypy passed; web typecheck, 218 unit tests and production build passed.
- Standard Playwright: 127 passed, three viewport-specific skips; shipped-page
  HTTP/PostgreSQL approval lane: one passed, including adversarial cases.
- Inspect gate: 20/20 correct; all ten frozen core scenarios completed and passed.
- Secret/PII, synthetic-data and environment audits: zero findings; 95 reviewed
  synthetic assets/generators. Ledger self-check: 25 events, valid chain,
  identical replay, detected tampering.

## Real Supabase procedure (not executed here)

Use the already-linked Serene project, or `supabase start` with Docker working.
Apply current migrations (`supabase db push` for hosted; local startup applies
the local migrations), expose `serene` in PostgREST, enable email/password Auth,
and confirm only `projection_state` is in the Serene Realtime publication.
Use operator-provided `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
`SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_DB_URL` from that same project; none
belongs in a commit.

From the repository root run:

```text
uv run python -m scripts.web_supabase_e2e prepare
```

This first checks the experiments migration and Realtime publication, then
creates three unique synthetic Auth users, two children marked `SYNTHETIC`,
guardianship, a narrow caregiver grant, pending GREEN requests, and blocked RED
proposals. Every event goes through `postgres_ledger`. Test accounts and opaque
web bindings are written only to ignored `.demo/web-e2e.json`; a partial run is
retained for operator inspection and is never silently overwritten.

Then in `app/web`, with that environment inherited:

```text
npm run test:e2e:supabase
```

This separate, opt-in configuration starts the production approval server and
the production web build. It uses real Supabase Auth, PostgREST and Realtime,
without network mocks. It tests Today/Investigations live appends through
`postgres_ledger`, a genuine browser offline interval, `Reconnecting`, resync,
RLS read restrictions, and browser approve/decline/RED behavior. Missing config
is a hard failure, never a skipped/passing proof. The precise no-optimistic-update
race and remaining adversarial commands are covered in the test-kernel lane.

Real-lane traces/screenshots are disabled and failure context stays in ignored
`.demo/real-web-e2e-artifacts`; never upload it. Preserve the synthetic ledger
as evidence. Use a disposable local stack if the records must be removed; the
tool does not bypass append-only protections to delete ledger events.
