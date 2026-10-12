# Serene Setup

One-time environment setup. Later branches should **not** reinstall these
tools; run `scripts/bootstrap.ps1` (Windows) or `scripts/bootstrap.sh`
(Linux/macOS/WSL) to verify and sync.

## 1. Pinned toolchain

| Tool | Version / pin | How it is installed | Status in this repo |
| --- | --- | --- | --- |
| Python | 3.11 (`.python-version`) | uv-managed | required |
| uv | ≥0.11 | https://docs.astral.sh/uv/ | `uv.lock` committed; CI uses `uv sync --locked` |
| Pydantic | 2.14 (`>=2.11,<3`) | core dependency | Domain Kernel |
| pytest / Hypothesis | 9.1 / 6.168 | `dev` group | test suite + property tests |
| ruff / mypy | 0.17 / 2.4 (strict) | `dev` group | lint + types |
| psycopg | 3.3 | `postgres` extra | Postgres adapter |
| pgserver | 0.1.4 | `dev` group | bundled PostgreSQL for local tests (no Docker) |
| Inspect AI | 0.3.278 | `eval` extra | evaluation harness |
| neatlogs | 1.4.26 | `observability` extra | runtime tracing (optional) |
| Supabase CLI | ≥2.75 | https://supabase.com/docs/guides/local-development/cli/getting-started | `supabase/config.toml` (`project_id = "serene"`), migrations |
| Entire CLI | v0.11.4 | GitHub release zip, verified against `checksums.txt` | `.entire/settings.json`, Claude Code hooks in `.claude/settings.json` |
| Hermes Agent | tag `v2026.9.24` = `f97608f178d1ffeca59860195ab7da295f7c8e5f` | official installer, `-Commit`/`--commit` pin, non-interactive | **manual step** (see §3) |
| cfo.ai | remote MCP `https://api.cfo.ai/mcp` | `.mcp.json` (project scope) | **manual auth** (see §3) |

## 2. Quick start

```bash
uv sync --locked --all-extras --group dev
uv run pytest                                   # backend suite, incl. real Postgres via pgserver
uv run python scripts/ledger_selfcheck.py       # replay + hash-chain + tamper self-check
uv run inspect eval eval/tasks/kernel_invariants.py --model mockllm/model
```

`SERENE_TEST_DATABASE_URL` overrides the local pgserver with any Postgres
(CI uses a `postgres:17` service container). With Docker available,
`supabase start` runs the full local Supabase stack and `supabase db reset`
applies `supabase/migrations/`.

## 3. Manual steps (need a human; never committed)

1. **Hermes Agent install** (modifies `%LOCALAPPDATA%\hermes` / `~/.hermes` and
   the user PATH). Windows:
   `powershell -File scripts/bootstrap.ps1 -InstallHermes`, or directly
   `install.ps1 -Commit f97608f178d1ffeca59860195ab7da295f7c8e5f -NonInteractive -SkipComputerUse`.
   Linux/macOS/WSL: `scripts/bootstrap.sh --install-hermes`.
   Then `hermes setup` (model provider + keys go to `HERMES_HOME/.env`) and,
   configure Telegram separately using [the channel boundary notes](../app/telegram/README.md).
2. **cfo.ai**: in Claude Code run `/mcp`, select `cfoai`, choose
   *Authenticate*, and sign in with the cfo.ai account in the browser. Use a
   cfo.ai Scenario rather than the live Main model for any edits.
3. **Entire** (optional cloud features): `entire login`. Local checkpoints work
   without login. Session pushing is disabled (`push_sessions: false`) because
   the repository is public; enable it only deliberately.
4. **neatlogs**: set `NEATLOGS_API_KEY` (and optionally `NEATLOGS_ENDPOINT`,
   `NEATLOGS_SESSION_ID`, `SERENE_TELEMETRY_PSEUDONYM_KEY`) in `.env`. Without a key
   telemetry is a no-op. The sink speaks HTTP to `/v1/trace` itself; the SDK extra
   is not needed for it.
5. **Supabase hosted project** (when one exists): `supabase login`,
   `supabase link --project-ref …`, `supabase db push`. Then see
   [activating the live web app](#activating-the-live-web-app-87).

### Activating the live web app (#87)

Today and Investigations read the signed-in parent's child's projection state
over Supabase Realtime. Nothing below is committed; values live in `.env` and
the hosting environment.

1. **Schema exposure.** In the hosted project's *API settings*, add `serene`
   to the exposed schemas (local: already in `supabase/config.toml`). RLS stays
   on for every `serene` table; nothing here changes a grant or a policy.
2. **Realtime publication.** `supabase db push` applies
   `20261012150000_projection_realtime.sql`, which adds only
   `serene.projection_state` to `supabase_realtime`. Check with
   `select tablename from pg_publication_tables where pubname = 'supabase_realtime'`:
   `projection_state` is listed and `domain_events` is not.
3. **Auth.** Email + password sign-in must be enabled (*Authentication →
   Providers → Email*). Parents are Supabase Auth users; Serene keeps only the
   opaque user id.
4. **Guardianship.** The backend (service role) records each parent:
   `insert into serene.children (child_id, data_class) values ('chd_…', 'REAL')` and
   `insert into serene.child_guardians (child_id, user_id, role) values ('chd_…', '<auth user uuid>', 'PARENT')`.
   The web app lists only the signed-in user's own `PARENT` rows (RLS:
   `child_guardians_self_read`), and reads projection rows only for those
   children (`projection_state_parent_read`). A caregiver is never listed: their
   grant covers `active_learnings` only.
5. **Web environment.** `NEXT_PUBLIC_SUPABASE_URL` and
   `NEXT_PUBLIC_SUPABASE_ANON_KEY` (public by design; RLS decides what a
   signed-in user sees) must be set when `npm run build` runs, because Next.js
   inlines them. Without them the app builds and every surface says plainly
   that no record is connected.
6. **Kernel environment.** `SUPABASE_DB_URL` is the service-role Postgres
   connection. Every production entry point builds its ledger with
   `serene.adapters.postgres.postgres_ledger`, which publishes
   `projection_state` after each admitted append. A failed publish never undoes
   the append; it is reported as `ledger.after_append_failed`.
7. **Backfill existing ledgers once** (and after any projection definition
   change, with `--replace` while the kernel is quiet):
   `uv run python scripts/rebuild_projections.py`. It verifies each child's
   hash chain first, refuses a child whose chain does not verify, only reads
   the ledger, and prints counts only.

## 4. Roles of the external tools

| Tool | Role in Serene | Never |
| --- | --- | --- |
| Hermes | reasoning, browser and model transport behind ports; Serene owns authenticated Telegram ingestion | evidence truth, promotion, safety, approval, memory authority |
| Supabase / Postgres | canonical ledger + disposable projections | business decisions (kept in kernel code) |
| neatlogs | runtime traces with opaque ids | receiving child narratives or raw reports |
| Entire | development provenance: architecture checkpoints on commits | storing secrets; auto-pushing transcripts of a public repo |
| cfo.ai | assumed economics analysis and one constrained optional confirmation helper; default runtime costs remain unknown ([details](economics.md)) | overriding safety or evidence quality (cost is a certified-equivalence tie-breaker only) |
| Inspect AI | frozen, deterministic evaluation harness | LLM-as-judge where a deterministic scorer exists |

## 5. Merge gates (#58)

`main` is protected by the repository ruleset **`main: required CI`**. A
change reaches `main` only through a pull request whose four `CI` jobs
(`.github/workflows/ci.yml`, run on every PR and every push to `main`) pass:

| Required check (job `name:`) | What it blocks |
| --- | --- |
| `Kernel (lint, types, tests, ledger + secret checks)` | Ruff, strict mypy, all backend + deterministic policy tests (promotion, safety, approval), every SQL file in [migrations](../supabase/migrations/) applied to a real Postgres 17 (`test_migrations`, `test_postgres_ledger`, `test_rls`), ledger self-check, secret/PII scan |
| `Inspect AI eval gate (no model keys)` | `scripts/inspect_gate.py`: any INCORRECT sample or missing task in the kernel, trust or runtime scenarios |
| `Web (next.js typecheck + unit tests + build)` | frontend typecheck, unit tests, production build |
| `Web E2E (Playwright, Chromium - desktop, tablet, mobile)` | browser acceptance suite |

The checks are pinned to the GitHub Actions app. Renaming a job changes its
check name, so the ruleset must be updated in the same change or every PR
stays blocked. No approvals, up-to-date branch or linear history are
required, and there is no bypass list.
