"""Tests for ll-migrate-labels: ## Labels body → labels: frontmatter migration."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

_SAMPLE_CONFIG = {
    "project": {"name": "test-project", "src_dir": "scripts/"},
    "issues": {
        "base_dir": ".issues",
        "categories": {
            "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
            "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
        },
        "completed_dir": "completed",
    },
}


def _make_project(tmp_path: Path) -> Path:
    """Set up a minimal project with config and issue directories."""
    ll_dir = tmp_path / ".ll"
    ll_dir.mkdir(exist_ok=True)
    (ll_dir / "ll-config.json").write_text(json.dumps(_SAMPLE_CONFIG))

    issues = tmp_path / ".issues"
    for d in ("bugs", "enhancements"):
        (issues / d).mkdir(parents=True, exist_ok=True)

    return tmp_path


def _run_migrate(project: Path, *extra_args: str) -> int:
    """Invoke main_migrate_labels with --config pointing to project and optional extra args."""
    from little_loops.cli import main_migrate_labels

    argv = ["ll-migrate-labels", "--config", str(project)] + list(extra_args)
    with patch.object(sys, "argv", argv):
        return main_migrate_labels()


class TestMigrateLabelsBodyToFrontmatter:
    """Tests for migrating ## Labels body sections to labels: frontmatter."""

    def test_labels_section_migrated_to_frontmatter(self, tmp_path: Path) -> None:
        """## Labels body section is moved to labels: frontmatter."""
        project = _make_project(tmp_path)
        issue = project / ".issues" / "bugs" / "P1-BUG-001-test.md"
        issue.write_text(
            "---\nstatus: open\n---\n# BUG-001: Test\n\n## Summary\nSome text.\n\n"
            "## Labels\n`fsm`, `quick-win`\n"
        )

        rc = _run_migrate(project)
        assert rc == 0

        result = issue.read_text()
        assert "labels:" in result
        assert "- fsm" in result
        assert "- quick-win" in result
        assert "## Labels" not in result

    def test_already_has_frontmatter_labels_merges(self, tmp_path: Path) -> None:
        """When labels: already in frontmatter, body labels are merged (not duplicated)."""
        project = _make_project(tmp_path)
        issue = project / ".issues" / "bugs" / "P1-BUG-002-merge.md"
        issue.write_text(
            "---\nstatus: open\nlabels:\n  - existing\n---\n# BUG-002: Merge\n\n"
            "## Labels\n`fsm`, `existing`\n"
        )

        rc = _run_migrate(project)
        assert rc == 0

        result = issue.read_text()
        assert "- existing" in result
        assert "- fsm" in result
        # 'existing' should appear only once in labels list
        label_count = result.count("- existing")
        assert label_count == 1

    def test_no_labels_section_untouched(self, tmp_path: Path) -> None:
        """Issues without ## Labels section are not modified."""
        project = _make_project(tmp_path)
        original = "---\nstatus: open\n---\n# BUG-003: No labels\n\n## Summary\nText.\n"
        issue = project / ".issues" / "bugs" / "P2-BUG-003-no-labels.md"
        issue.write_text(original)

        rc = _run_migrate(project)
        assert rc == 0

        assert issue.read_text() == original

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        """--dry-run previews changes without modifying files."""
        project = _make_project(tmp_path)
        original = "---\nstatus: open\n---\n# BUG-004: Dry run\n\n## Labels\n`cli`\n"
        issue = project / ".issues" / "bugs" / "P1-BUG-004-dry.md"
        issue.write_text(original)

        rc = _run_migrate(project, "--dry-run")
        assert rc == 0
        assert issue.read_text() == original

    def test_no_issues_dir_returns_error(self, tmp_path: Path) -> None:
        """Returns exit code 1 when .issues/ does not exist."""
        from little_loops.cli import main_migrate_labels

        argv = ["ll-migrate-labels", "--config", str(tmp_path)]
        with patch.object(sys, "argv", argv):
            rc = main_migrate_labels()
        assert rc == 1

    def test_backtick_format_parsed(self, tmp_path: Path) -> None:
        """Labels enclosed in backticks are extracted correctly."""
        project = _make_project(tmp_path)
        issue = project / ".issues" / "enhancements" / "P3-ENH-001-backtick.md"
        issue.write_text(
            "---\nstatus: open\n---\n# ENH-001: Backtick\n\n## Labels\n`issue-model`, `sync-compatibility`\n"
        )

        rc = _run_migrate(project)
        assert rc == 0

        result = issue.read_text()
        assert "- issue-model" in result
        assert "- sync-compatibility" in result
