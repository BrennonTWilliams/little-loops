"""AC tests for the BUG-3629 run/state-scoped stall keying spike."""

from __future__ import annotations

import ast
from pathlib import Path

from .run_scoped_stall import check_stall

TRACK = ["action"]


def _check(tmp_path: Path, run_dir: Path | None, state: str, h: str = "h", max_repeat: int = 1):
    return check_stall(
        h, state_dir=run_dir, state_name=state, track=TRACK, max_repeat=max_repeat, cwd=tmp_path
    )


def test_sequential_runs_do_not_share_state(tmp_path: Path) -> None:
    run1, run2 = tmp_path / "run1", tmp_path / "run2"
    assert _check(tmp_path, run1, "s") == ("yes", 0)
    assert _check(tmp_path, run1, "s") == ("no", 1)
    assert _check(tmp_path, run2, "s") == ("yes", 0)


def test_same_track_states_in_one_run_isolated(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _check(tmp_path, run, "a")
    assert _check(tmp_path, run, "a") == ("no", 1)
    assert _check(tmp_path, run, "b") == ("yes", 0)


def test_parent_child_sharing_run_dir_isolated(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _check(tmp_path, run, "parent_state")
    _check(tmp_path, run, "parent_state")
    assert _check(tmp_path, run, "child_state") == ("yes", 0)


def test_missing_run_dir_falls_back_to_cwd_loops_tmp(tmp_path: Path) -> None:
    assert _check(tmp_path, None, "s") == ("yes", 0)
    assert list((tmp_path / ".loops" / "tmp").glob("ll-action-stall-*.txt"))


def test_stall_semantics_preserved(tmp_path: Path) -> None:
    run = tmp_path / "run"
    seq = [_check(tmp_path, run, "s", max_repeat=2) for _ in range(3)]
    assert seq == [("yes", 0), ("yes", 1), ("no", 2)]
    assert _check(tmp_path, run, "s", h="other", max_repeat=2) == ("yes", 0)


def test_guard_no_cwd_writes_when_state_dir_set(tmp_path: Path) -> None:
    _check(tmp_path, tmp_path / "run", "s")
    assert not (tmp_path / ".loops").exists()


def test_guard_spike_does_not_import_production_evaluators() -> None:
    src = (Path(__file__).parent / "run_scoped_stall.py").read_text()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("little_loops")
        elif isinstance(node, ast.Import):
            assert not any(a.name.startswith("little_loops") for a in node.names)
