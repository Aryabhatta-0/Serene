# One-time Serene developer bootstrap (Windows PowerShell). Idempotent.
# Installs the Python toolchain and verifies external tools; never writes secrets.
# Hermes is only installed with -InstallHermes (it writes %LOCALAPPDATA%\hermes and the user PATH).
param([switch]$InstallHermes)
$ErrorActionPreference = "Stop"

$HermesCommit = if ($env:HERMES_PINNED_COMMIT) { $env:HERMES_PINNED_COMMIT } else { "f97608f178d1ffeca59860195ab7da295f7c8e5f" }  # tag v2026.9.24
$EntireVersion = "v0.11.4"
Set-Location (Join-Path $PSScriptRoot "..")

function Test-Cmd($name) { $null -ne (Get-Command $name -ErrorAction SilentlyContinue) }

Write-Host "== Python (uv, locked) =="
if (-not (Test-Cmd uv)) { throw "uv missing: https://docs.astral.sh/uv/getting-started/installation/" }
uv sync --locked --all-extras --group dev

Write-Host "== Supabase CLI =="
if (Test-Cmd supabase) { supabase --version } else { Write-Host "supabase CLI missing: https://supabase.com/docs/guides/local-development/cli/getting-started" }

Write-Host "== Entire CLI ($EntireVersion) =="
if (Test-Cmd entire) { entire version | Select-Object -First 1 } else {
  Write-Host "Entire missing: download entire_windows_amd64.zip ($EntireVersion) from https://github.com/entireio/cli/releases,"
  Write-Host "verify it against checksums.txt, and put entire.exe on PATH (see docs/setup.md)."
}

Write-Host "== Hermes Agent (pinned $HermesCommit) =="
if (Test-Cmd hermes) { hermes --version }
elseif ($InstallHermes) {
  $dir = Join-Path $env:TEMP "hermes-installer"
  New-Item -ItemType Directory -Force $dir | Out-Null
  Invoke-WebRequest -UseBasicParsing https://hermes-agent.nousresearch.com/install.ps1 -OutFile "$dir\install.ps1"
  & "$dir\install.ps1" -Commit $HermesCommit -NonInteractive -SkipComputerUse
} else { Write-Host "Hermes not installed. Re-run with -InstallHermes, or see docs/setup.md." }

Write-Host "== Local checks =="
uv run python scripts/ledger_selfcheck.py
uv run python scripts/secret_scan.py

Write-Host @"

Manual steps that need a human (never automated, never committed):
  1. Copy-Item .env.example .env     # fill locally
  2. hermes setup                    # model provider + keys live in HERMES_HOME\.env
  3. hermes gateway setup            # Telegram bot token (branch A)
  4. entire login                    # optional: Entire cloud features
  5. Claude Code: /mcp -> cfoai -> Authenticate   (browser sign-in to cfo.ai)
  6. supabase login; supabase link   # only when a hosted project exists
"@
