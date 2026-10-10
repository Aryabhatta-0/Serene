# Morrow Privacy

> **Status:** design specification. Implemented by issues #8, #52, #59.

## 1. Data ownership

A child's data belongs to the **parent**. Access is explicit and scoped.

| Principal | Access |
| --- | --- |
| Parent | Full access to their child's data |
| Caregiver | Explicit, narrow scopes only (least privilege) |
| Backend services | Service-scoped access (service role), never parent UI paths |
| Evaluation / tests | **Synthetic data only** |

## 2. Row Level Security (#8)

Supabase Postgres RLS enforces the boundary:

- Parent owns child data; policies key on the authenticated parent.
- Caregivers receive explicit scopes (e.g. a single routine, a time window).
- Backend/service operations use the service-scoped role, isolated from
  end-user credentials.
- Evaluation runs against synthetic child data; no real child data in CI, tests
  or eval fixtures.

## 3. PII-safe observability (#52)

neatlogs tracing records context IDs, hypotheses, tool selection/args, browser
actions, verification, failures/retries, state, tokens, latency and cost —
**without unnecessary child PII**. Redaction is applied at the logging boundary,
not left to callers.

## 4. Secrets and logging audit (#59)

- No credentials in the repository.
- `.env.example` documents every variable with empty values.
- Demo and evaluation use synthetic child data.
- Logs are PII-safe by construction and documented.
- Secret handling (loading, rotation, scope) is documented.

## 5. Non-goals

Morrow is not a clinical or diagnostic product, and the MVP is not built for
production child data at scale — it is a research-grade demonstration of
trustworthy, evidence-bound reasoning under a strict privacy boundary.
