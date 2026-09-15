"""Tests for ENH-2943: ll-loop rename and ll-loop cleanup subcommands."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.loop.cleanup import (
    CleanupEntry,
    CleanupThresholds,
    RunClass,
    _classify,
    cleanup,
)
from little_loops.cli.loop.rename import (
    RenameReport,
    _KO_RE,
    _resolve_loop,
    rename_loop,
)


# ---------- _classify (pure function) ----------


class TestClassifyRun:
    """Pure-function classification: status × pid × age."""

    def test_running_alive_fresh_is_healthy(self) -> None:
        cls = _classify("running", pid_alive_v=True, age_minutes_v=1.0, t=CleanupThresholds())
        assert cls is RunClass.HEALTHY

    def test_running_dead_pid_is_stuck(self) -> None:
        cls = _classify("running", pid_alive_v=False, age_minutes_v=1.0, t=CleanupThresholds())
        assert cls is RunClass.STUCK_RUNNING

    def test_running_alive_but_aged_is_stuck(self) -> None:
        cls = _classify("running", pid_alive_v=True, age_minutes_v=100.0, t=CleanupThresholds())
        assert cls is RunClass.STUCK_RUNNING

    def test_interrupted_no_pid_aged_is_stale_interrupted_aged(self) -> None:
        cls = _classify(
            "interrupted", pid_alive_v=False, age_minutes_v=25 * 60, t=CleanupThresholds()
        )
        assert cls is RunClass.STALE_INTERRUPTED_AGED

    def test_interrupted_no_pid_recent_is_healthy(self) -> None:
        cls = _classify(
            "interrupted", pid_alive_v=False, age_minutes_v=10, t=CleanupThresholds()
        )
        assert cls is RunClass.HEALTHY

    def test_interrupted_alive_pid_is_stale_interrupted(self) -> None:
        cls = _classify("interrupted", pid_alive_v=True, age_minutes_v=10, t=CleanupThresholds())
        assert cls is RunClass.STALE_INTERRUPTED

    def test_failed_is_terminal(self) -> None:
        cls = _classify("failed", pid_alive_v=False, age_minutes_v=10, t=CleanupThresholds())
        assert cls is RunClass.TERMINAL

    def test_timed_out_is_terminal(self) -> None:
        cls = _classify(
            "timed_out", pid_alive_v=False, age_minutes_v=10, t=CleanupThresholds()
        )
        assert cls is RunClass.TERMINAL

    def test_awaiting_continuation_fresh_is_healthy(self) -> None:
        cls = _classify(
            "awaiting_continuation", pid_alive_v=True, age_minutes_v=10, t=CleanupThresholds()
        )
        assert cls is RunClass.HEALTHY

    def test_awaiting_continuation_aged_is_abandoned(self) -> None:
        cls = _classify(
            "awaiting_continuation",
            pid_alive_v=True,
            age_minutes_v=100.0,
            t=CleanupThresholds(),
        )
        assert cls is RunClass.ABANDONED_HANDOFF


# ---------- rename_loop ----------


def _setup_loops_dir(tmp_path: Path) -> Path:
    """Create the standard `.loops/` layout under `tmp_path` and return loops_dir."""
    loops_dir = tmp_path / ".loops"
    loops_dir.mkdir()
    return loops_dir


class TestRenameLoopValidation:
    """Pre-flight validations reject bad inputs before touching the filesystem."""

    def test_invalid_new_name_rejected(self, tmp_path: Path) -> None:
        loops_dir = _setup_loops_dir(tmp_path)
        (loops_dir / "old.yaml").write_text("name: old\n")
        with pytest.raises(ValueError, match="Invalid loop name"):
            rename_loop("old", "Bad Name", dry_run=True, loops_dir=loops_dir)

    def test_same_name_rejected(self, tmp_path: Path) -> None:
        loops_dir = _setup_loops_dir(tmp_path)
        (loops_dir / "loop.yaml").write_text("name: loop\n")
        with pytest.raises(ValueError, match="identical"):
            rename_loop("loop", "loop", dry_run=True, loops_dir=loops_dir)

    def test_nonexistent_loop_rejected(self, tmp_path: Path) -> None:
        loops_dir = _setup_loops_dir(tmp_path)
        with pytest.raises(FileNotFoundError, match="Loop not found"):
            rename_loop("nope", "new", dry_run=True, loops_dir=loops_dir)

    def test_destination_exists_rejected(self, tmp_path: Path) -> None:
        loops_dir = _setup_loops_dir(tmp_path)
        (loops_dir / "old.yaml").write_text("name: old\n")
        (loops_dir / "new.yaml").write_text("name: new\n")
        with pytest.raises(FileExistsError, match="already exists"):
            rename_loop("old", "new", dry_run=True, loops_dir=loops_dir)

    def test_running_loop_rejected(self, tmp_path: Path) -> None:
        loops_dir = _setup_loops_dir(tmp_path)
        running = loops_dir / ".running"
        running.mkdir()
        (loops_dir / "old.yaml").write_text("name: old\n")
        (running / "old-20260101T000000.pid").write_text("99999")
        with pytest.raises(RuntimeError, match="running"):
            rename_loop("old", "new", dry_run=True, loops_dir=loops_dir)


class TestRenameLoopHappyPath:
    """Dry-run preview and apply behaviors."""

    def test_dry_run_does_not_move_files(self, tmp_path: Path) -> None:
        loops_dir = _setup_loops_dir(tmp_path)
        src = loops_dir / "old.yaml"
        src.write_text('name: old\ninitial: done\nstates:\n  done:\n    terminal: true\n')
        report = rename_loop("old", "new", dry_run=True, loops_dir=loops_dir)
        assert report.yaml_moved is True
        assert src.exists()  # not moved
        assert not (loops_dir / "new.yaml").exists()

    def test_apply_moves_yaml_and_updates_name(self, tmp_path: Path) -> None:
        loops_dir = _setup_loops_dir(tmp_path)
        src = loops_dir / "old.yaml"
        src.write_text(
            'name: "old"\ninitial: done\nstates:\n  done:\n    terminal: true\n'
        )
        rename_loop("old", "new", dry_run=False, loops_dir=loops_dir)
        assert not src.exists()
        dest = loops_dir / "new.yaml"
        assert dest.exists()
        # name: field updated to 'new'
        assert 'name: "new"' in dest.read_text()


class TestRenameLoopRefRewrite:
    """loop: <old> -> loop: <new> rewrites across loop YAMLs."""

    def test_rewrites_subloop_refs_in_project_scope(self, tmp_path: Path) -> None:
        loops_dir = _setup_loops_dir(tmp_path)
        (loops_dir / "parent.yaml").write_text(
            "name: parent\ninitial: done\nstates:\n  done:\n    loop: child\n    terminal: true\n"
        )
        (loops_dir / "child.yaml").write_text(
            "name: child\ninitial: done\nstates:\n  done:\n    terminal: true\n"
        )
        report = rename_loop("child", "renamed", dry_run=False, loops_dir=loops_dir)
        assert any("parent.yaml" in r for r, _ in report.refs_rewritten)
        assert "loop: renamed" in (loops_dir / "parent.yaml").read_text()


class TestResolveLoop:
    """Project scope wins over builtin when both exist."""

    def test_project_wins_when_both_exist(self, tmp_path: Path, monkeypatch) -> None:
        from little_loops.fsm import loop_paths

        builtin_loop = tmp_path / "builtin.yaml"
        builtin_loop.write_text("name: myloop\n")
        monkeypatch.setattr(loop_paths, "get_builtin_loops_dir", lambda: tmp_path)

        loops_dir = _setup_loops_dir(tmp_path)
        project_loop = loops_dir / "myloop.yaml"
        project_loop.write_text("name: myloop\n")

        result = _resolve_loop("myloop", loops_dir)
        assert result is not None
        assert result[0] == project_loop
        assert result[1] == "project"


# ---------- cleanup() integration ----------


class TestCleanupIntegration:
    """cleanup() walks .running/ and classifies each loop state file."""

    def test_cleanup_on_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        loops_dir = _setup_loops_dir(tmp_path)
        entries = cleanup(dry_run=True, loops_dir=loops_dir)
        assert entries == []

    def test_cleanup_classifies_running_loop(self, tmp_path: Path) -> None:
        loops_dir = _setup_loops_dir(tmp_path)
        running = loops_dir / ".running"
        running.mkdir()
        # State file says running but no PID file → reconcile flips to interrupted
        # (per BUG-3317 6h fallback); with no pid and recent age, classifies as healthy.
        # The test asserts that classification lands in the expected class for this setup.
        state_file = running / "myloop-20260101T000000.state.json"
        state_file.write_text(
            json.dumps(
                {
                    "loop_name": "myloop",
                    "status": "running",
                    "current_state": "init",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                    "iteration": 0,
                    "started_at": "2026-01-01T00:00:00+00:00",
                }
            )
        )
        entries = cleanup(dry_run=True, loops_dir=loops_dir)
        assert len(entries) == 1
        assert entries[0].loop == "myloop"
        # State was reconciled to 'interrupted' (no pid, fresh) → healthy
        assert entries[0].cls in (RunClass.HEALTHY, RunClass.STUCK_RUNNING)


# ---------- kebab-case regex sanity ----------


class TestKebabCaseRegex:
    def test_valid_names(self) -> None:
        for n in ("loop", "my-loop", "a-b-c", "loop-2", "x", "1loop"):
            assert _KO_RE.match(n), n

    def test_invalid_names(self) -> None:
        for n in ("Loop", "my_loop", "-loop", "loop-", "my--loop", "", "loop.yaml"):
            assert not _KO_RE.match(n), n
