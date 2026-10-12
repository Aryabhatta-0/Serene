# Serene Privacy

> **Status:** audited against merged `main` at `6b82073` on 2026-10-12.
> [#59](https://github.com/Sathvikar01/morrow/issues/59) is closed by merged
> [PR #80](https://github.com/Sathvikar01/morrow/pull/80). Telemetry redaction,
> synthetic-data provenance, secret/env scans and scoped RLS are implemented;
> this is a repository audit, not production readiness or compliance certification.

## 1. Data ownership

A child's data belongs to the **parent**. Access is explicit and scoped.

| Principal | Access |
| --- | --- |
| Parent | Reads everything about a child they are a guardian of (`serene.child_guardians`) |
| Caregiver | Only `observations:read` / `experiments:read` / `learnings:read` for one child, granted by its parent, expiring (<= 180 days), revocable |
| Backend services | `service_role`: the only writer of the ledger and of guardianship |
| Evaluation / tests | **Synthetic data only**: `serene_eval` sees `SYNTHETIC` children only |

## 2. Database boundary (implemented)

- The ledger and projections live in a dedicated `serene` schema. Merged #33's
  [API configuration](../supabase/config.toml) exposes that schema through
  PostgREST for projection snapshots; RLS and grants still govern access.
- The foundation migration enables RLS and revokes end-user privileges.
  The later [#8 migration](../supabase/migrations/20261011120000_serene_rls_access.sql)
  adds explicit scoped SELECT policies/privileges for `authenticated` and
  synthetic-only `serene_eval`; `anon` remains denied. It is stale to describe
  current `main` as having no end-user read policies.
- `service_role` may `SELECT`/`INSERT` the ledger; `UPDATE`/`DELETE`/`TRUNCATE`
  are revoked and also blocked by triggers.

### 2.1 Scoped access (#8)

End-user identity is the JWT `sub` claim (`serene.request_user_id()`, the value
Supabase's `auth.uid()` reads). End users can never insert, update or delete
ledger rows, claim guardianship or change a child's data class. Approvals,
evidence, hypotheses, promotions and memory events are parent-only. A parent can
grant or revoke a caregiver scope for their own child only; a caregiver cannot
grant themselves or widen a scope. Adversarial cross-child / caregiver /
service-role / evaluation tests: [RLS tests](../tests/test_rls.py).
Caregivers can read only scoped event families; only `learnings:read` exposes
the `active_learnings` projection. A grant does not permit approvals, evidence,
hypotheses, promotion or memory reads. Backend service credentials bypass RLS
and must remain private; RLS does not replace backend identity verification.

[PostgresProjectionStore](../serene/adapters/postgres.py) can replace projection
rows, while ledger writes remain backend-only and append-only. The five
[read views](../serene/projections/views.py) are disposable outputs of replay,
never authorization inputs. Merged #33's
[Realtime migration](../supabase/migrations/20261012150000_projection_realtime.sql)
publishes only `serene.projection_state`, not the ledger. The
[web feed](../app/web/lib/projections/supabase.ts) uses a child-filtered snapshot
and subscription under the signed-in user's RLS, not a browser service key.
Its optional backend publisher cannot undo a durable ledger append on failure;
read state can lag and be rebuilt. No page creates the feed yet;
[Causal Twin](../app/web/lib/causal-twin/source.ts) and
[Memory](../app/web/lib/memory/source.ts) sources remain UNCONNECTED.
#75 complete Causal Twin provenance projection remains open. No deployed
family-data service is established by these tests.

## 3. Privacy-safe observability (#52, audited by #59)

All application telemetry passes through
[SafeTelemetry](../serene/observability/telemetry.py):

- **Allow-listed keys only** (event type, ids, sequence, actor/source kind,
  decision, reason codes, policy version, …).
- **Token-like values only**: any value with whitespace or free text is dropped,
  so report text, hypotheses and narratives cannot leak by accident even under an
  allow-listed key.
- **Child ids are pseudonymized** with a keyed HMAC
  (`SERENE_TELEMETRY_PSEUDONYM_KEY`) or dropped when no key is configured.
- Raw child/person/actor ids and recognizable credential tokens are rejected
  even under an allowed key. `child_ref` accepts only the HMAC output shape.
- **Failure isolation**: any sink exception is swallowed and counted; ledger
  outcomes are byte-identical with a crashing sink (tested).
- Redaction is applied centrally in `SafeTelemetry.emit`; kernel code never
  talks to a sink directly, so callers cannot bypass it.

The [NeatLogs adapter](../serene/adapters/neatlogs_sink.py) only receives these
redacted attributes, re-applies the same `redact` (so a direct caller cannot bypass
it), sets them as `serene.*` span attributes and is a no-op without
`NEATLOGS_API_KEY`. It posts over HTTPS with the standard library (no SDK), never
follows a redirect (the key is not forwarded), packs spans into bodies under the
ingest limit, caps pending spans, and reports failures as codes (`HTTP_403`,
`REDIRECT_REFUSED`, ...) in a `FlushReport`, never as response text.

Span names use the same central validation even for direct sink calls. Workflow,
session, end-user and verification-marker fields accept safe opaque tokens only;
never put a person's name, Telegram id or authentication/session secret there.
The ingest API key appears only in the request header. No SDK auto-instrumentation
is installed by the adapter, and arbitrary OTEL resource fields are not exported.

Tokens are not a general PII classifier. Allowed metadata must be fixed codes,
enums, generated correlation ids, counts or public source hosts; never rename
private text to an allowed key. Keep URLs, query strings, prompts, tool arguments,
raw parent/caregiver messages and private evidence out of telemetry.

The Python application has no raw logging/print path (guarded by a test).
Database constraint failures and Git subprocess failures expose fixed codes,
not row contents, stderr or private paths. Both web error boundaries emit fixed
messages, not exception objects. Domain/validation exceptions and ledger or
memory payloads remain **private application data**, not safe log artifacts:
never dump them, stack locals, transport bodies or `exc_info` into logs. Hermes
is a separately configured runtime; do not enable its prompt/debug capture for
real family data. This audit does not certify third-party logging behavior.

## 4. Data minimisation and external processing

- Actor identity uses opaque IDs. Raw reports and other free-text application
  fields can contain personal information; the schema is not a PII detector.
- Raw evidence and structured interpretations are private ledger payloads.
  The core presentation projections omit raw evidence content, but in-process
  `KernelState` retains entities for policy decisions. Replaying or serializing
  internal state is not a privacy-safe export.
- The merged #36 [Memory/Dream view](../serene/memory/view.py) omits child/actor
  identifiers and evidence content, but includes memory text, patch rationale
  and diffs. It is private review data, not safe telemetry or a public export;
  a read-only UI does not remove its confidentiality requirements.
- Main's #37 [Experiments read view](../serene/experiments/view.py) includes
  intervention/outcome text and reasons, while omitting child/actor IDs. It is
  private application data, not safe telemetry. Its
  [web approval adapter](../serene/adapters/web/approvals.py) trusts a parent
  principal supplied by authenticated transport. That transport (#84) verifies
  the Supabase session with Supabase Auth, keeps only the opaque user id,
  resolves the bound `act_` PARENT actor (never writing Supabase ids to the
  ledger) and logs no user or child id. The `experiments` projection carries
  the same read view, parent-only under RLS. Synthetic
  Experiments fixture routes do not establish deployed family authorization.
  [Real Supabase acceptance remains pending](web-e2e-proof.md).
- The #75 [Causal Twin provenance view](../serene/causal/provenance.py) omits
  child, actor and `src_` source ids (actors appear only by kind) and never
  quotes raw evidence: a raw-evidence node shows its kind, channel, capture
  time, content digest and verification checks, and an external source only
  its public host (never its URI). It does include derived display text
  (observation statements, pattern descriptions, hypothesis statements, outcome
  summaries, learning statements), so it is private application data, not
  telemetry. Tests pin these omissions (`tests/test_twin_provenance.py`).
- Model provenance stores provider/model/prompt-version identifiers, not full
  prompts or private reasoning. This does not mean runtime tasks contain no
  private content: [context retrieval](../serene/investigation/context.py) and
  [Hermes transport](../serene/adapters/hermes/transport.py) send task context to
  the configured runtime/provider. Redacted NeatLogs exports do not redact that
  application inference channel. Provider retention/deletion is not certified.
- Telegram bindings map private platform identities to opaque actors outside
  the ledger. The [channel](../serene/adapters/telegram/channel.py) and its
  current in-memory binding/prompt registries are trusted infrastructure, not
  a complete production identity/session store.

**LLM proposes; deterministic code decides.** Parent approval authorizes an exact
experiment; it is not blanket consent to export family data. Evidence verification
confirms bounded source checks; it is not a privacy/legal review of arbitrary
pages. Telemetry and cfo.ai cannot authorize collection, widen access or alter
safety/quality. #55's saved [cfo.ai requests/readback](economics.md) contain the
synthetic assumed operating model only, not family records or measured bills.

## 5. Operational audit (#59)

- Copy `.env.example` to gitignored `.env` and set only integrations in use.
  Never commit `.env`, credentials, auth exports, private keys, database dumps,
  real family input or raw agent sessions. Rotate/revoke any exposed key before
  removing it; deletion alone does not revoke credentials in history.
- `scripts/env_audit.py` covers Python (including aliased/copied environments),
  web, bootstrap scripts and Supabase substitutions. Host/generated/test-only
  variables have explicit purposes in `INTERNAL`; the frozen gateways' three
  dynamic environment-comparison expressions are individually reviewed. These
  are not setup secrets. New operator variables must enter `.env.example` with
  empty secret values and a purpose comment. Offline tests need no provider keys.
- `scripts/secret_scan.py` scans every tracked and untracked non-ignored file,
  including lockfiles and binary bytes, with no file/suffix exclusions. It fails
  on credential formats, bearer/credential literals, personal email candidates
  and forbidden env files. Reports contain path/line/type, never matched values.
  Exact fingerprinted offline test stand-ins and documentation/developer email
  domains are reviewed exceptions; they are not family data. Pattern scanning
  cannot establish server-side credential validity or recognize every possible
  secret. Review any candidate privately; never paste it into an issue or PR.
- Hermes keeps its own secrets in `HERMES_HOME/.env`; cfo.ai uses browser OAuth;
  optional Entire cloud features use `entire login`. Local checkpoint inspection
  does not require cloud login. Credentials must remain outside tracked files.
- Entire is configured with `push_sessions: false` because this repository is
  public: agent session transcripts are not pushed unless a human opts in.

Checks and receipts are in [PR #80](https://github.com/Sathvikar01/morrow/pull/80);
the reviewed inventory is [synthetic-data-manifest.json](synthetic-data-manifest.json).
Executable evidence: [secret scan](../scripts/secret_scan.py),
[environment audit](../scripts/env_audit.py), [synthetic audit](../scripts/synthetic_audit.py),
[privacy tests](../tests/test_privacy_audit.py), [telemetry tests](../tests/test_observability.py)
and [sink tests](../tests/test_neatlogs_sink.py).

All demo/eval/test child and family data must be authored fiction or produced by
`SyntheticFamily` (seed-derived ids, fixed clock). `docs/synthetic-data-manifest.json`
records the reviewed input/generator/archived-output provenance and SHA-256 bytes.
`scripts/synthetic_audit.py` fails for added, changed or removed assets; review
provenance before updating the manifest. Never regenerate frozen eval results
to pass this check. Historical names such as **Maya** are fictional scenario
labels; the evidence is their synthetic source, not the spelling of a name.
Technical provider error fixtures contain sanitized runtime responses, not real
child input. The web shell connects no family record; its build-gated Causal Twin
and kernel-generated Memory/Dream fixtures have reviewed synthetic provenance.
The merged #56/#57 Maya demo uses a fixed
fictional seed, scripted model/browser I/O and a temporary synthetic memory repo;
its report is explicitly marked synthetic and its reset accepts only the canonical
seed. Their implementations are unchanged by this audit. Hashes attest reviewed
bytes, not an automatic real-person detector.

Run before committing (the existing CI test suite runs the same checks):

```sh
uv run python scripts/secret_scan.py --history
uv run python scripts/env_audit.py
uv run python scripts/synthetic_audit.py
uv run pytest tests/test_repo_hygiene.py tests/test_privacy_audit.py tests/test_observability.py tests/test_neatlogs_sink.py tests/test_runtime_tracing.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

### Historical integrity tests and current privacy fixes

The immutable v3/v4/v5 experiments pin the old runtime source bytes. Their
contract tests now read runtime bytes from pre-audit Git revision
`be0cd9c8dfee04458d399b656a561b14126ab71f` in a temporary test context. The
snapshot is not imported or executed. Manifests, tapes, scorer/gate code and
archived evidence are copied from the current checkout and retain their actual
byte checks; none of their hashes or historical outcomes is changed.

`tests/test_frozen_contract_context.py` proves that the unchanged frozen gates
still refuse the current privacy-modified runtime with `PROTECTED_RUNTIME_DRIFT`.
`tests/test_historical_snapshot_integrity.py` tampers with temporary runtime/page
bytes and proves refusal. Normal application/privacy tests continue to exercise
the current code. This test context is not an exemption for a live experiment.
The kernel CI checkout includes Git history to materialize the pinned source;
shallow local clones need `git fetch --unshallow` before the full historical suite.

## 6. Non-goals

Serene is not a clinical or diagnostic product, and the MVP is not built for
production child data at scale.

There is no implemented user-facing retention/deletion workflow, automated
credential rotation, third-party logging certification or general PII classifier.
Append-only history and reviewed memory deprecation preserve refuted beliefs;
they do not establish a legal erasure process. No silent uncertainty, hidden
deletion of refuted beliefs, autonomous parent approval, model policy authority,
unverified promotion or cost overriding safety/quality is permitted. The current
investigation-completion limitation is disclosed in [architecture.md](architecture.md).

Entire uses [local Git-ref settings](../.entire/settings.json) with session
pushing and telemetry disabled. #54 has a verified milestone reference index,
but genuine historical checkpoint coverage/retrieval is incomplete; the index
is not merged into this audited `main`. Keep #54 open; never publish private
transcripts to manufacture checkpoint coverage. See
[provenance status](architecture.md#observability-economics-and-development-provenance).
No extra memory/analytics/database stack is adopted to collect more child data;
the [recorded exclusions](architecture.md#non-goals-and-excluded-technologies)
explain the MVP choices.

On 2026-10-12, `npm audit --omit=dev` against the pinned web lockfile reports
Next.js 14.2.35 **critical** and PostCSS **high** advisory groups. Their reachability
needs separate review and remediation before public hosting; dependency versions
are unchanged by this secrets/logging audit. The offline Maya demo needs no web
server. The audit's passing privacy checks do not establish production readiness.
