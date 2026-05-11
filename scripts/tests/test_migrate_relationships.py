"""Tests for ll-migrate-relationships: rename parent_issue:/related: frontmatter keys."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

from little_loops.cli.migrate_relationships import main_migrate_relationships
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
    for d in ("bugs", "features", "enhancements"):
        (issues / d).mkdir(parents=True, exist_ok=True)

    return tmp_path


def _run_migrate_relationships(project: Path, *extra_args: str) -> int:
    """Invoke main_migrate_relationships with --config pointing to project and optional extra args."""
    argv = ["ll-migrate-relationships", "--config", str(project)] + list(extra_args)
    with patch.object(sys, "argv", argv):
        return main_migrate_relationships()


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestMigrateRelationshipsParentIssue:
    """Tests for renaming parent_issue: -> parent:."""

    def test_renames_parent_issue_to_parent(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        issue = project / ".issues" / "enhancements" / "P2-ENH-100-child.md"
        issue.write_text(
            "---\nid: ENH-100\ntype: ENH\npriority: P2\nparent_issue: ENH-050\nstatus: open\n---\n\n# Child\n"
        )

        rc = _run_migrate_relationships(project)

        assert rc == 0
        fm = parse_frontmatter(issue.read_text())
        assert fm["parent"] == "ENH-050"
        assert "parent_issue" not in fm

    def test_parent_value_preserved_exactly(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        issue = project / ".issues" / "bugs" / "P1-BUG-042-nested.md"
        issue.write_text("---\nid: BUG-042\nparent_issue: EPIC-001\n---\n\n# Bug\n")

        rc = _run_migrate_relationships(project)

        assert rc == 0
        fm = parse_frontmatter(issue.read_text())
        assert fm["parent"] == "EPIC-001"

    def test_file_without_parent_issue_is_unchanged(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        issue = project / ".issues" / "bugs" / "P0-BUG-001-standalone.md"
        original = "---\nid: BUG-001\ntype: BUG\nstatus: open\n---\n\n# Standalone\n"
        issue.write_text(original)

        rc = _run_migrate_relationships(project)

        assert rc == 0
        assert issue.read_text() == original

    def test_renames_across_multiple_files(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        enh_dir = project / ".issues" / "enhancements"
        f1 = enh_dir / "P2-ENH-200-a.md"
        f2 = enh_dir / "P2-ENH-201-b.md"
        f1.write_text("---\nid: ENH-200\nparent_issue: ENH-100\n---\n")
        f2.write_text("---\nid: ENH-201\nparent_issue: ENH-100\n---\n")

        rc = _run_migrate_relationships(project)

        assert rc == 0
        assert parse_frontmatter(f1.read_text())["parent"] == "ENH-100"
        assert parse_frontmatter(f2.read_text())["parent"] == "ENH-100"
        assert "parent_issue" not in parse_frontmatter(f1.read_text())
        assert "parent_issue" not in parse_frontmatter(f2.read_text())


class TestMigrateRelationshipsRelated:
    """Tests for renaming related: -> relates_to:."""

    def test_renames_related_to_relates_to(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        issue = project / ".issues" / "features" / "P2-FEAT-010-linked.md"
        issue.write_text(
            "---\nid: FEAT-010\ntype: FEAT\nrelated: BUG-005\nstatus: open\n---\n\n# Feature\n"
        )

        rc = _run_migrate_relationships(project)

        assert rc == 0
        fm = parse_frontmatter(issue.read_text())
        assert fm["relates_to"] == "BUG-005"
        assert "related" not in fm

    def test_file_without_related_is_unchanged(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        issue = project / ".issues" / "bugs" / "P1-BUG-099-solo.md"
        original = "---\nid: BUG-099\nstatus: open\n---\n\n# Solo\n"
        issue.write_text(original)

        rc = _run_migrate_relationships(project)

        assert rc == 0
        assert issue.read_text() == original


class TestMigrateRelationshipsDryRun:
    """Tests for dry-run mode."""

    def test_dry_run_makes_no_file_changes(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        issue = project / ".issues" / "enhancements" / "P2-ENH-300-child.md"
        original = "---\nid: ENH-300\nparent_issue: ENH-200\nstatus: open\n---\n\n# Child\n"
        issue.write_text(original)

        rc = _run_migrate_relationships(project, "--dry-run")

        assert rc == 0
        assert issue.read_text() == original

    def test_dry_run_still_reports_zero_on_clean(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        issue = project / ".issues" / "bugs" / "P0-BUG-001-clean.md"
        issue.write_text("---\nid: BUG-001\nstatus: open\n---\n\n# No relationship keys\n")

        rc = _run_migrate_relationships(project, "--dry-run")

        assert rc == 0


class TestMigrateRelationshipsEdgeCases:
    """Tests for edge cases."""

    def test_both_keys_in_same_file(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        issue = project / ".issues" / "enhancements" / "P2-ENH-500-both.md"
        issue.write_text(
            "---\nid: ENH-500\nparent_issue: ENH-400\nrelated: BUG-001\nstatus: open\n---\n\n# Both\n"
        )

        rc = _run_migrate_relationships(project)

        assert rc == 0
        fm = parse_frontmatter(issue.read_text())
        assert fm["parent"] == "ENH-400"
        assert fm["relates_to"] == "BUG-001"
        assert "parent_issue" not in fm
        assert "related" not in fm

    def test_no_issues_dir_returns_error(self, tmp_path: Path) -> None:
        # No .issues directory
        rc = _run_migrate_relationships(tmp_path)

        assert rc == 1

    def test_already_migrated_file_is_unchanged(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        issue = project / ".issues" / "enhancements" / "P2-ENH-600-migrated.md"
        original = "---\nid: ENH-600\nparent: ENH-500\nstatus: open\n---\n\n# Already migrated\n"
        issue.write_text(original)

        rc = _run_migrate_relationships(project)

        assert rc == 0
        assert issue.read_text() == original
