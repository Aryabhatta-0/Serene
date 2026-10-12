"""Rebuild serene.projection_state from the ledger (issue #87). Read-only on the ledger.

    uv run python scripts/rebuild_projections.py            # every child, monotonic
    uv run python scripts/rebuild_projections.py --child chd_...
    uv run python scripts/rebuild_projections.py --replace  # after a projection change

Uses SUPABASE_DB_URL (the service-role connection). Each child's stream is
replayed and its hash chain verified first; a child whose chain does not
verify is refused and its rows are left alone. The default publish is
monotonic, so it is safe to run while the kernel is appending and safe to run
twice. `--replace` deletes and rewrites each child's rows: run it with the
kernel quiet. Prints counts only, never child ids.
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", action="append", default=None, help="limit to this child id")
    parser.add_argument("--replace", action="store_true", help="delete and rewrite each child")
    args = parser.parse_args()

    conninfo = os.environ.get("SUPABASE_DB_URL", "")
    if not conninfo:
        print("refusing to run; missing: SUPABASE_DB_URL", file=sys.stderr)
        return 2

    from serene.adapters.postgres import backfill_projections

    result = backfill_projections(conninfo, args.child, replace=args.replace)
    print(f"written: {result.written}")
    print(f"empty: {result.empty}")
    print(f"refused (chain did not verify): {result.refused}")
    return 1 if result.refused else 0


if __name__ == "__main__":
    sys.exit(main())
