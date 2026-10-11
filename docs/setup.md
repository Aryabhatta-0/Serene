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
uv run pytest                                   # 144 tests, incl. real Postgres via pgserver
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
   for branch A, `hermes gateway setup` (Telegram bot token).
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
   `supabase link --project-ref …`, `supabase db push`.

## 4. Roles of the external tools

| Tool | Role in Serene | Never |
| --- | --- | --- |
| Hermes | reasoning, tools, Telegram gateway, browser, model routing behind ports | evidence truth, promotion, safety, approval, memory authority |
| Supabase / Postgres | canonical ledger + disposable projections | business decisions (kept in kernel code) |
| neatlogs | runtime traces with opaque ids | receiving child narratives or raw reports |
| Entire | development provenance: architecture checkpoints on commits | storing secrets; auto-pushing transcripts of a public repo |
| cfo.ai | unit-economics model; later the cost table behind `CostModel` | overriding safety or evidence quality (cost is a tie-breaker only) |
| Inspect AI | frozen, deterministic evaluation harness | LLM-as-judge where a deterministic scorer exists |
