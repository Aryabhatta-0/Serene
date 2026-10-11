"""Reset → identical reset → successful complete Maya demo (#57)."""

import json
from pathlib import Path
from typing import Any

import pytest

from serene.demo.maya import SEED, MayaDemo
from serene.demo.report import verify_report
from serene.demo.reset import baseline, demo_directory, load_seed, reset_demo


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in demo_directory(root).iterdir() if p.is_file()}


def test_reset_twice_is_identical_and_demo_succeeds(tmp_path: Path, monkeypatch: Any) -> None:
    # A production-looking environment cannot influence this reset: it is never read.
    monkeypatch.setenv("SUPABASE_DB_URL", "production-must-not-be-used")
    monkeypatch.setenv("SERENE_MEMORY_REPO_PATH", str(tmp_path / "production-memory"))
    reset_demo(tmp_path)
    first = snapshot(tmp_path)
    assert json.loads(first["seed.json"]) == baseline()
    reset_demo(tmp_path)
    assert snapshot(tmp_path) == first
    report = MayaDemo(tmp_path / "temporary-memory", seed=load_seed(tmp_path)).run()
    assert len(verify_report(report)) == 18
    output = demo_directory(tmp_path)
    (output / "report.json").write_text(json.dumps(report))
    (output / "report.html").write_text("generated demo evidence")
    reset_demo(tmp_path)
    assert snapshot(tmp_path) == first  # reset after a run also restores the exact state
    assert not (tmp_path / "production-memory").exists()


def test_reset_preserves_unrelated_files_and_refuses_modified_seed(tmp_path: Path) -> None:
    reset_demo(tmp_path)
    output = demo_directory(tmp_path)
    keep = output / "recording-not-owned-by-reset.txt"
    keep.write_text("preserve")
    (output / "seed.json").write_text(json.dumps({**baseline(), "synthetic": False}))
    with pytest.raises(ValueError, match="canonical fixture"):
        load_seed(tmp_path)
    reset_demo(tmp_path)
    assert load_seed(tmp_path) == SEED and keep.read_text() == "preserve"


def test_reset_refuses_linked_workspace_before_writing(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "report.json").write_text("preserve outside data")
    repo = tmp_path / "repo"
    repo.mkdir()
    try:
        (repo / ".demo").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("host does not permit symlink creation; exercised on Linux CI")
    with pytest.raises(ValueError, match="symlink or junction"):
        reset_demo(repo)
    assert (outside / "report.json").read_text() == "preserve outside data"
