# Serene Privacy

> **Status:** telemetry redaction, synthetic-only test data, secret/PII scanning,
> the database deny-by-default boundary and parent/caregiver-scoped RLS (#8,
> `supabase/migrations/20261011120000_serene_rls_access.sql`) are implemented.

## 1. Data ownership

A child's data belongs to the **parent**. Access is explicit and scoped.

| Principal | Access |
| --- | --- |
| Parent | Reads everything about a child they are a guardian of (`serene.child_guardians`) |
| Caregiver | Only `observations:read` / `experiments:read` / `learnings:read` for one child, granted by its parent, expiring (<= 180 days), revocable |
| Backend services | `service_role`: the only writer of the ledger and of guardianship |
| Evaluation / tests | **Synthetic data only**: `serene_eval` sees `SYNTHETIC` children only |

## 2. Database boundary (implemented)

- The ledger and projections live in a dedicated `serene` schema that is not
  exposed through PostgREST.
- RLS is **enabled with no end-user policies** on both tables: `anon` and
  `authenticated` are denied by default and have all privileges revoked.
- `service_role` may `SELECT`/`INSERT` the ledger; `UPDATE`/`DELETE`/`TRUNCATE`
  are revoked and also blocked by triggers.

### 2.1 Scoped access (#8)

End-user identity is the JWT `sub` claim (`serene.request_user_id()`, the value
Supabase's `auth.uid()` reads). End users can never insert, update or delete
ledger rows, claim guardianship or change a child's data class. Approvals,
evidence, hypotheses, promotions and memory events are parent-only. A parent can
grant or revoke a caregiver scope for their own child only; a caregiver cannot
grant themselves or widen a scope. Adversarial cross-child / caregiver /
service-role / evaluation tests: `tests/test_rls.py`.

## 3. Privacy-safe observability (#52, audited by #59)

All telemetry passes through `serene.observability.SafeTelemetry`:

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

The neatlogs adapter (`serene/adapters/neatlogs_sink.py`) only receives these
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
not row contents, stderr or private paths. The web error boundary emits a fixed
message, not the exception object. Domain/validation exceptions and ledger or
memory payloads remain **private application data**, not safe log artifacts:
never dump them, stack locals, transport bodies or `exc_info` into logs. Hermes
is a separately configured runtime; do not enable its prompt/debug capture for
real family data. This audit does not certify third-party logging behavior.

## 4. Data minimisation in the domain

- Actors are opaque ids (`act_…`); no names or contact details in any schema.
- Raw evidence content is stored once, in the ledger payload, with a content
  digest; projections never copy raw text (tested).
- Model provenance records provider/model/prompt version, never prompts or
  private reasoning.

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
  Entire uses `entire login`. None of these credentials touch the repository.
- Entire is configured with `push_sessions: false` because this repository is
  public: agent session transcripts are not pushed unless a human opts in.

All demo/eval/test child and family data must be authored fiction or produced by
`SyntheticFamily` (seed-derived ids, fixed clock). `docs/synthetic-data-manifest.json`
records the reviewed input/generator/archived-output provenance and SHA-256 bytes.
`scripts/synthetic_audit.py` fails for added, changed or removed assets; review
provenance before updating the manifest. Never regenerate frozen eval results
to pass this check. Historical names such as **Maya** are fictional scenario
labels; the evidence is their synthetic source, not the spelling of a name.
Technical provider error fixtures contain sanitized runtime responses, not real
child input. The web shell connects no family record; its build-gated causal-twin
fixture has synthetic model provenance. The merged #56/#57 Maya demo uses a fixed
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

## 6. Non-goals

Serene is not a clinical or diagnostic product, and the MVP is not built for
production child data at scale.
