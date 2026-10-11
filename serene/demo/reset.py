"""Reset only the offline Maya workspace; there is no database or production mode."""

from __future__ import annotations

import json
from pathlib import Path

from serene.demo.maya import SEED
from serene.domain.canonical import canonical_json
from serene.testing.synthetic import T0


def baseline() -> dict[str, object]:
    return {
        "fixture": SEED,
        "seed": SEED,
        "synthetic": True,
        "mode": "offline-scripted-io",
        "clock": T0.isoformat(),
        "events": [],
        "memory": {},
        "status": "READY",
    }


def demo_directory(repository: Path) -> Path:
    root = repository.resolve()
    target = root / ".demo" / "maya"
    # resolve() follows symlinks and Windows junctions. Never follow either to data elsewhere.
    if target.resolve() != target:
        raise ValueError("Maya workspace must not traverse a symlink or junction")
    for name in ("seed.json", "report.json", "report.html", "seed.tmp"):
        path = target / name
        if path.is_symlink() or path.resolve() != path:
            raise ValueError("Maya artifact must not be a symlink or junction")
    return target


def reset_demo(repository: Path) -> bytes:
    """Restore the canonical empty ledger/seed; remove only generated run reports.

    No recursive deletion, arbitrary target, environment configuration, DB adapter,
    production flag, credential or network operation is available to this command.
    Unknown files are preserved. The next run builds fresh services from this seed.
    """
    target = demo_directory(repository)
    target.mkdir(parents=True, exist_ok=True)
    data = canonical_json(baseline()) + b"\n"
    temporary = target / "seed.tmp"
    temporary.write_bytes(data)
    temporary.replace(target / "seed.json")
    for name in ("report.json", "report.html"):
        (target / name).unlink(missing_ok=True)
    return data


def load_seed(repository: Path) -> str:
    """Only the exact canonical synthetic seed is accepted, including after tampering."""
    path = demo_directory(repository) / "seed.json"
    if path.exists() and json.loads(path.read_bytes()) != baseline():
        raise ValueError("Maya seed differs from the canonical fixture; run demo_reset.py")
    return SEED
