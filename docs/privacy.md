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

## 3. Privacy-safe observability (implemented, #52 partial)

All telemetry passes through `serene.observability.SafeTelemetry`:

- **Allow-listed keys only** (event type, ids, sequence, actor/source kind,
  decision, reason codes, policy version, …).
- **Token-like values only**: any value with whitespace or free text is dropped,
  so report text, hypotheses and narratives cannot leak by accident even under an
  allow-listed key.
- **Child ids are pseudonymized** with a keyed HMAC
  (`SERENE_TELEMETRY_PSEUDONYM_KEY`) or dropped when no key is configured.
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

## 4. Data minimisation in the domain

- Actors are opaque ids (`act_…`); no names or contact details in any schema.
- Raw evidence content is stored once, in the ledger payload, with a content
  digest; projections never copy raw text (tested).
- Model provenance records provider/model/prompt version, never prompts or
  private reasoning.

## 5. Secrets and logging audit (#59 partial)

- `.env.example` documents every variable read by `serene/`, `scripts/`,
  `eval/` with empty secret values (tested).
- `scripts/secret_scan.py` scans tracked and untracked files for credential
  formats and personal email addresses; it runs in CI and in the test suite.
- Hermes keeps its own secrets in `HERMES_HOME/.env`; cfo.ai uses browser OAuth;
  Entire uses `entire login`. None of these credentials touch the repository.
- Entire is configured with `push_sessions: false` because this repository is
  public: agent session transcripts are not pushed unless a human opts in.

## 6. Non-goals

Serene is not a clinical or diagnostic product, and the MVP is not built for
production child data at scale.
