"""Tests for ll-migrate: one-time migration of completed/deferred to type dirs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

from little_loops.cli.migrate import main_migrate
from little_loops.frontmatter import parse_frontmatter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_CONFIG: dict[str, Any] = {
    "project": {"name": "test", "src_dir": "src/", "test_cmd": None, "lint_cmd": None},
    "issues": {
        "base_dir": ".issues",
        "categories": {
            "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
            "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
            "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
        },
        "completed_dir": "completed",
        "deferred_dir": "deferred",
        "priorities": ["P0", "P1", "P2"],
    },
}


def _make_project(tmp_path: Path) -> Path:
    """Set up a minimal project with config and issue directories."""
    ll_dir = tmp_path / ".ll"
    ll_dir.mkdir()
    (ll_dir / "ll-config.json").write_text(json.dumps(_SAMPLE_CONFIG))

    issues = tmp_path / ".issues"
    for d in ("completed", "deferred", "bugs", "features", "enhancements"):
        (issues / d).mkdir(parents=True, exist_ok=True)

    return tmp_path


def _run_migrate(project: Path, *extra_args: str) -> int:
    """Invoke main_migrate with --config pointing to project and optional extra args."""
    argv = ["ll-migrate", "--config", str(project)] + list(extra_args)
    with patch.object(sys, "argv", argv):
        return main_migrate()


def _make_mock_run(
    *,
    git_tracked: bool = True,
    git_log_date: str = "2024-01-15",
    git_mv_ok: bool = True,
) -> Any:
    """Return a subprocess.run mock function."""

    def mock_run(
        cmd: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        _ = kwargs
        if "ls-files" in cmd:
            stdout = cmd[-1] if git_tracked else ""
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
        if "--format=%as" in cmd:
            stdout = git_log_date if git_log_date else ""
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
        if "mv" in cmd:
            if git_mv_ok:
                # Actually perform the rename so the file exists at new path
                src, dst = Path(cmd[-2]), Path(cmd[-1])
                src.rename(dst)
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="error")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    return mock_run


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestMigrateCompleted:
    """Tests for migrating files from completed/ to type directories."""

    def test_moves_completed_bug_to_bugs_dir(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        src = project / ".issues" / "completed" / "P1-BUG-042-some-bug.md"
        src.write_text(
            "---\nid: BUG-042\ntype: BUG\npriority: P1\nstatus: done\ncompleted_at: 2024-01-01T00:00:00Z\n---\n\n# Bug\n"
        )

        with patch("subprocess.run", side_effect=_make_mock_run()):
            rc = _run_migrate(project)

        assert rc == 0
        dst = project / ".issues" / "bugs" / "P1-BUG-042-some-bug.md"
        assert dst.exists()
        assert not src.exists()
        fm = parse_frontmatter(dst.read_text())
        assert fm["status"] == "done"

    def test_backfills_completed_at_from_git_log(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        src = project / ".issues" / "completed" / "P2-ENH-100-thing.md"
        src.write_text(
            "---\nid: ENH-100\ntype: ENH\npriority: P2\nstatus: done\n---\n\n# Enh\n"
        )

        with patch("subprocess.run", side_effect=_make_mock_run(git_log_date="2023-06-15")):
            rc = _run_migrate(project)

        assert rc == 0
        dst = project / ".issues" / "enhancements" / "P2-ENH-100-thing.md"
        assert dst.exists()
        fm = parse_frontmatter(dst.read_text())
        assert fm["completed_at"] == "2023-06-15T00:00:00Z"
        assert fm["status"] == "done"

    def test_file_without_frontmatter_gets_frontmatter_prepended(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        src = project / ".issues" / "completed" / "P0-BUG-001-old-bug.md"
        # No frontmatter at all — just markdown content
        src.write_text("# BUG-001: Old Bug\n\nSome description.\n")

        with patch("subprocess.run", side_effect=_make_mock_run(git_log_date="2022-03-10")):
            rc = _run_migrate(project)

        assert rc == 0
        dst = project / ".issues" / "bugs" / "P0-BUG-001-old-bug.md"
        assert dst.exists()
        content = dst.read_text()
        assert content.startswith("---\n")
        fm = parse_frontmatter(content)
        assert fm["status"] == "done"
        assert fm["completed_at"] == "2022-03-10T00:00:00Z"

    def test_type_from_frontmatter_takes_precedence(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        # Filename says BUG but frontmatter says FEAT
        src = project / ".issues" / "completed" / "P1-BUG-999-misnamed.md"
        src.write_text(
            "---\nid: FEAT-999\ntype: FEAT\npriority: P1\nstatus: done\ncompleted_at: 2024-02-01T00:00:00Z\n---\n\n# Feature\n"
        )

        with patch("subprocess.run", side_effect=_make_mock_run()):
            rc = _run_migrate(project)

        assert rc == 0
        # Should land in features/ because frontmatter says FEAT
        assert (project / ".issues" / "features" / "P1-BUG-999-misnamed.md").exists()
        assert not (project / ".issues" / "bugs" / "P1-BUG-999-misnamed.md").exists()

    def test_preserves_existing_completed_at(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        src = project / ".issues" / "completed" / "P1-BUG-010-keep-date.md"
        src.write_text(
            "---\nid: BUG-010\ntype: BUG\nstatus: done\ncompleted_at: 2021-11-30T12:00:00Z\n---\n\n# Bug\n"
        )

        with patch("subprocess.run", side_effect=_make_mock_run(git_log_date="2020-01-01")):
            rc = _run_migrate(project)

        assert rc == 0
        dst = project / ".issues" / "bugs" / "P1-BUG-010-keep-date.md"
        fm = parse_frontmatter(dst.read_text())
        # Original date must NOT be overwritten
        assert fm["completed_at"] == "2021-11-30T12:00:00Z"


class TestMigrateDeferred:
    """Tests for migrating files from deferred/ to type directories."""

    def test_moves_deferred_feature_with_status_deferred(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        src = project / ".issues" / "deferred" / "P3-FEAT-200-future-idea.md"
        src.write_text(
            "---\nid: FEAT-200\ntype: FEAT\npriority: P3\nstatus: open\n---\n\n# Feature\n"
        )

        with patch("subprocess.run", side_effect=_make_mock_run()):
            rc = _run_migrate(project)

        assert rc == 0
        dst = project / ".issues" / "features" / "P3-FEAT-200-future-idea.md"
        assert dst.exists()
        fm = parse_frontmatter(dst.read_text())
        assert fm["status"] == "deferred"

    def test_deferred_does_not_backfill_completed_at(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        src = project / ".issues" / "deferred" / "P2-ENH-300-parked.md"
        src.write_text("---\nid: ENH-300\ntype: ENH\nstatus: open\n---\n\n# Parked\n")

        with patch("subprocess.run", side_effect=_make_mock_run()):
            rc = _run_migrate(project)

        assert rc == 0
        dst = project / ".issues" / "enhancements" / "P2-ENH-300-parked.md"
        fm = parse_frontmatter(dst.read_text())
        assert "completed_at" not in fm


class TestMigrateDryRun:
    """Tests for dry-run mode."""

    def test_dry_run_makes_no_file_changes(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        src = project / ".issues" / "completed" / "P0-BUG-005-test.md"
        src.write_text(
            "---\nid: BUG-005\ntype: BUG\nstatus: done\ncompleted_at: 2024-01-01T00:00:00Z\n---\n\n# Bug\n"
        )
        original_content = src.read_text()

        # subprocess.run should NOT be called for git mv in dry-run
        git_mv_called = []

        def mock_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            _ = kwargs
            if "mv" in cmd:
                git_mv_called.append(cmd)
            if "ls-files" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout=cmd[-1], stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=mock_run):
            rc = _run_migrate(project, "--dry-run")

        assert rc == 0
        # Source must still exist with unchanged content
        assert src.exists()
        assert src.read_text() == original_content
        # Target must NOT exist
        assert not (project / ".issues" / "bugs" / "P0-BUG-005-test.md").exists()
        # git mv must not have been called
        assert not git_mv_called


class TestMigrateEdgeCases:
    """Tests for edge cases and error handling."""

    def test_untyped_file_is_reported_and_skipped(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        src = project / ".issues" / "completed" / "no-prefix-here.md"
        src.write_text("# Unknown\n\nNo frontmatter, no prefix.\n")

        with patch("subprocess.run", side_effect=_make_mock_run()):
            _run_migrate(project)

        # Untyped files are not moved
        assert src.exists()

    def test_target_already_exists_skips_and_errors(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        src = project / ".issues" / "completed" / "P1-BUG-042-dup.md"
        src.write_text(
            "---\nid: BUG-042\ntype: BUG\nstatus: done\ncompleted_at: 2024-01-01T00:00:00Z\n---\n"
        )
        dst = project / ".issues" / "bugs" / "P1-BUG-042-dup.md"
        dst.write_text("---\nid: BUG-042\ntype: BUG\nstatus: done\n---\n# existing\n")

        with patch("subprocess.run", side_effect=_make_mock_run()):
            rc = _run_migrate(project)

        assert rc == 1  # error exit because of collision
        assert src.exists()  # original untouched

    def test_untracked_file_uses_rename_fallback(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        src = project / ".issues" / "completed" / "P2-ENH-500-untracked.md"
        src.write_text(
            "---\nid: ENH-500\ntype: ENH\nstatus: done\ncompleted_at: 2024-03-01T00:00:00Z\n---\n"
        )

        with patch("subprocess.run", side_effect=_make_mock_run(git_tracked=False)):
            rc = _run_migrate(project)

        assert rc == 0
        dst = project / ".issues" / "enhancements" / "P2-ENH-500-untracked.md"
        assert dst.exists()
        assert not src.exists()

    def test_empty_dirs_produce_zero_exit(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)

        with patch("subprocess.run", side_effect=_make_mock_run()):
            rc = _run_migrate(project)

        assert rc == 0

    def test_filename_prefix_fallback_when_no_frontmatter_type(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        src = project / ".issues" / "completed" / "P1-BUG-077-no-type-field.md"
        # frontmatter exists but no 'type' key
        src.write_text("---\nid: BUG-077\nstatus: done\ncompleted_at: 2024-01-01T00:00:00Z\n---\n")

        with patch("subprocess.run", side_effect=_make_mock_run()):
            rc = _run_migrate(project)

        assert rc == 0
        assert (project / ".issues" / "bugs" / "P1-BUG-077-no-type-field.md").exists()
