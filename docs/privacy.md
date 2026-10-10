# Serene Privacy

> **Status:** telemetry redaction, synthetic-only test data, secret/PII scanning
> and the database deny-by-default boundary are implemented. Parent/caregiver
> scoped RLS policies are issue #8 (branch A/B follow-up, see handoff).

## 1. Data ownership

A child's data belongs to the **parent**. Access is explicit and scoped.

| Principal | Access |
| --- | --- |
| Parent | Full access to their child's data (policies: #8) |
| Caregiver | Explicit, narrow scopes only (#8) |
| Backend services | Service role; the only path to `serene.*` today |
| Evaluation / tests | **Synthetic data only** (`serene.testing`) |

## 2. Database boundary (implemented)

- The ledger and projections live in a dedicated `serene` schema that is not
  exposed through PostgREST.
- RLS is **enabled with no end-user policies** on both tables: `anon` and
  `authenticated` are denied by default and have all privileges revoked.
- `service_role` may `SELECT`/`INSERT` the ledger; `UPDATE`/`DELETE`/`TRUNCATE`
  are revoked and also blocked by triggers.

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
redacted attributes, sets them as `serene.*` span attributes and is a no-op
without `NEATLOGS_API_KEY`. `capture_logs` is disabled.

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
