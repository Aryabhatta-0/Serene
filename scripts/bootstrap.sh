#!/usr/bin/env bash
# One-time Serene developer bootstrap (Linux / macOS / WSL2). Idempotent.
# Installs the Python toolchain and verifies external tools; never writes secrets.
# Hermes is only installed when --install-hermes is passed (it modifies ~/.hermes and PATH).
set -euo pipefail

HERMES_COMMIT="${HERMES_PINNED_COMMIT:-f97608f178d1ffeca59860195ab7da295f7c8e5f}"  # tag v2026.9.24
ENTIRE_VERSION="v0.11.4"
INSTALL_HERMES=0
[[ "${1:-}" == "--install-hermes" ]] && INSTALL_HERMES=1

cd "$(dirname "$0")/.."

need() { command -v "$1" >/dev/null 2>&1; }

echo "== Python (uv, locked) =="
need uv || { echo "uv missing: https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }
uv sync --locked --all-extras --group dev

echo "== Supabase CLI =="
if need supabase; then supabase --version; else
  echo "supabase CLI missing: https://supabase.com/docs/guides/local-development/cli/getting-started"
fi

echo "== Entire CLI (${ENTIRE_VERSION}) =="
if need entire; then entire version | head -1; else
  echo "Entire missing. Official installer: curl -fsSL https://entire.io/install.sh | bash"
  echo "or download ${ENTIRE_VERSION} from https://github.com/entireio/cli/releases and verify checksums.txt"
fi

echo "== Hermes Agent (pinned ${HERMES_COMMIT}) =="
if need hermes; then hermes --version || true
elif [[ $INSTALL_HERMES -eq 1 ]]; then
  # Official installer, pinned to a release commit, without the interactive wizard.
  curl -fsSL https://hermes-agent.nousresearch.com/install.sh -o /tmp/hermes-install.sh
  bash /tmp/hermes-install.sh --commit "${HERMES_COMMIT}" --non-interactive --skip-computer-use
else
  echo "Hermes not installed. Re-run with --install-hermes, or see docs/setup.md."
fi

echo "== Local checks =="
uv run python scripts/ledger_selfcheck.py
uv run python scripts/secret_scan.py

cat <<'EOF'

Manual steps that need a human (never automated, never committed):
  1. cp .env.example .env            # fill locally
  2. hermes setup                    # model provider + keys live in HERMES_HOME/.env
  3. hermes gateway setup            # Telegram bot token (branch A)
  4. entire login                    # optional: Entire cloud features
  5. Claude Code: /mcp -> cfoai -> Authenticate   (browser sign-in to cfo.ai)
  6. supabase login && supabase link # only when a hosted project exists
EOF
