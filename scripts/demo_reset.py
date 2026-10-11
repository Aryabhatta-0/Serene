"""Restore the exact offline Maya demo baseline: uv run python scripts/demo_reset.py."""

from pathlib import Path

from serene.demo.reset import demo_directory, reset_demo
from serene.domain.canonical import sha256_hex


def main() -> None:
    repository = Path(__file__).resolve().parents[1]
    data = reset_demo(repository)
    print(f"Maya synthetic baseline READY: {demo_directory(repository)}")
    print(f"Baseline SHA-256: {sha256_hex(data)}")
    print("Run: uv run python scripts/maya_demo.py")


if __name__ == "__main__":
    main()
