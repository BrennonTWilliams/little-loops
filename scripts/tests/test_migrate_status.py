"""Tests for ll-migrate-status: normalize non-canonical status: frontmatter values."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

from little_loops.cli.migrate_status import _migrate_content, main_migrate_status
from little_loops.frontmatter import STATUS_SYNONYMS, parse_frontmatter

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
    ll_dir.mkdir(exist_ok=True)
    (ll_dir / "ll-config.json").write_text(json.dumps(_SAMPLE_CONFIG))

    issues = tmp_path / ".issues"
    for d in ("bugs", "features", "enhancements"):
        (issues / d).mkdir(parents=True, exist_ok=True)

    return tmp_path


def _run_migrate(project: Path, *extra_args: str) -> int:
    """Invoke main_migrate_status with --config pointing to project and optional extra args."""
    argv = ["ll-migrate-status", "--config", str(project)] + list(extra_args)
    with patch.object(sys, "argv", argv):
        return main_migrate_status()


# ---------------------------------------------------------------------------
# Unit tests for _migrate_content
# ---------------------------------------------------------------------------


class TestMigrateStatusNormalization:
    """Tests for core normalization logic."""

    def test_renames_completed_to_done(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        issue = project / ".issues" / "enhancements" / "P3-ENH-100-old.md"
        issue.write_text("---\nid: ENH-100\nstatus: completed\n---\n\n# Old\n")

        rc = _run_migrate(project)

        assert rc == 0
        fm = parse_frontmatter(issue.read_text())
        assert fm["status"] == "done"

    def test_renames_complete_to_done(self) -> None:
        content = "---\nid: BUG-001\nstatus: complete\n---\n"
        updated, changes = _migrate_content(content)
        assert "status: done" in updated
        assert len(changes) == 1

    def test_renames_wip_to_in_progress(self) -> None:
        content = "---\nid: FEAT-010\nstatus: wip\n---\n"
        updated, changes = _migrate_content(content)
        assert "status: in_progress" in updated
        assert len(changes) == 1

    def test_canonical_status_is_unchanged(self) -> None:
        for canonical in ("open", "in_progress", "blocked", "deferred", "done", "cancelled"):
            content = f"---\nid: ENH-001\nstatus: {canonical}\n---\n"
            updated, changes = _migrate_content(content)
            assert updated == content
            assert changes == []

    def test_file_without_status_is_unchanged(self) -> None:
        content = "---\nid: BUG-999\npriority: P2\n---\n\n# No status\n"
        updated, changes = _migrate_content(content)
        assert updated == content
        assert changes == []

    def test_status_in_body_text_is_not_modified(self) -> None:
        content = (
            "---\nid: ENH-001\nstatus: done\n---\n\nThe status: completed value was normalized.\n"
        )
        updated, changes = _migrate_content(content)
        assert updated == content
        assert changes == []

    def test_all_synonyms_are_normalized(self) -> None:
        for synonym, canonical in STATUS_SYNONYMS.items():
            content = f"---\nid: ENH-001\nstatus: {synonym}\n---\n"
            updated, changes = _migrate_content(content)
            assert f"status: {canonical}" in updated, f"Expected {synonym!r} → {canonical!r}"
            assert len(changes) == 1


class TestMigrateStatusDryRun:
    """Tests for --dry-run mode."""

    def test_dry_run_makes_no_file_changes(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        issue = project / ".issues" / "enhancements" / "P3-ENH-200-wip.md"
        original = "---\nid: ENH-200\nstatus: completed\n---\n\n# WIP\n"
        issue.write_text(original)

        rc = _run_migrate(project, "--dry-run")

        assert rc == 0
        assert issue.read_text() == original

    def test_dry_run_still_exits_zero(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        issue = project / ".issues" / "bugs" / "P0-BUG-001-clean.md"
        issue.write_text("---\nid: BUG-001\nstatus: open\n---\n\n# Clean\n")

        rc = _run_migrate(project, "--dry-run")

        assert rc == 0


class TestMigrateStatusEdgeCases:
    """Tests for edge cases."""

    def test_no_issues_dir_returns_error(self, tmp_path: Path) -> None:
        rc = _run_migrate(tmp_path)
        assert rc == 1

    def test_already_canonical_file_is_unchanged(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        issue = project / ".issues" / "enhancements" / "P2-ENH-300-done.md"
        original = "---\nid: ENH-300\nstatus: done\n---\n\n# Already done\n"
        issue.write_text(original)

        rc = _run_migrate(project)

        assert rc == 0
        assert issue.read_text() == original

    def test_multiple_files_updated(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        enh_dir = project / ".issues" / "enhancements"
        f1 = enh_dir / "P3-ENH-400-a.md"
        f2 = enh_dir / "P3-ENH-401-b.md"
        f1.write_text("---\nid: ENH-400\nstatus: completed\n---\n")
        f2.write_text("---\nid: ENH-401\nstatus: completed\n---\n")

        rc = _run_migrate(project)

        assert rc == 0
        assert parse_frontmatter(f1.read_text())["status"] == "done"
        assert parse_frontmatter(f2.read_text())["status"] == "done"
