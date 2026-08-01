"""Tests for ll-migrate-relationships: rename parent_issue:/related: frontmatter keys."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

from little_loops.cli.migrate_relationships import main_migrate_relationships
from little_loops.frontmatter import _iter_frontmatter_blocks, parse_frontmatter

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

    def test_renames_target_branch_to_base_branch(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        issue = project / ".issues" / "bugs" / "P2-BUG-700-branch.md"
        issue.write_text("---\nid: BUG-700\ntarget_branch: develop\n---\n\n# Branch\n")

        rc = _run_migrate_relationships(project)

        assert rc == 0
        fm = parse_frontmatter(issue.read_text())
        assert fm["base_branch"] == "develop"
        assert "target_branch" not in fm


class TestMigrateRelationshipsCanonicalBlock:
    """Renames must land in the canonical id:-bearing block (BUG-2955)."""

    def test_double_frontmatter_writes_into_canonical_block(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        issue = project / ".issues" / "features" / "P2-FEAT-800-double.md"
        issue.write_text(
            "---\n"
            "status: done\n"
            "completed_at: 2026-04-21T00:00:00Z\n"
            "---\n"
            "> **Status: Won't Do**\n"
            "\n"
            "---\n"
            "id: FEAT-800\n"
            "parent_issue: FEAT-799\n"
            "confidence_score: 80\n"
            "---\n"
            "\n"
            "# Double\n"
        )

        rc = _run_migrate_relationships(project)

        assert rc == 0
        blocks = _iter_frontmatter_blocks(issue.read_text())
        assert len(blocks) == 2, "fold is a separate concern; block count must not change"
        outer, canonical = blocks
        assert canonical.is_canonical
        assert canonical.data["parent"] == "FEAT-799"
        assert "parent_issue" not in canonical.data
        # The non-canonical block must be left exactly as it was.
        assert outer.data == {"status": "done", "completed_at": "2026-04-21T00:00:00Z"}
        assert "parent" not in outer.data

    def test_deprecated_key_in_non_canonical_block_is_removed(self, tmp_path: Path) -> None:
        """parent_issue: living in the outer block still migrates to canonical."""
        project = _make_project(tmp_path)
        issue = project / ".issues" / "features" / "P2-FEAT-801-split.md"
        issue.write_text(
            "---\nstatus: done\nparent_issue: FEAT-799\n---\n"
            "---\nid: FEAT-801\npriority: P2\n---\n\n# Split\n"
        )

        rc = _run_migrate_relationships(project)

        assert rc == 0
        text = issue.read_text()
        fm = parse_frontmatter(text)
        assert fm["parent"] == "FEAT-799"
        assert "parent_issue" not in fm
        canonical = next(b for b in _iter_frontmatter_blocks(text) if b.is_canonical)
        assert canonical.data["parent"] == "FEAT-799"


class TestMigrateRelationshipsNoClobber:
    """A canonical key already present must win over the deprecated alias."""

    def test_canonical_parent_not_clobbered_by_deprecated_alias(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        issue = project / ".issues" / "enhancements" / "P2-ENH-900-both.md"
        issue.write_text(
            "---\nid: ENH-900\nparent: ENH-800\nparent_issue: ENH-700\nstatus: open\n---\n\n# Both\n"
        )

        rc = _run_migrate_relationships(project)

        assert rc == 0
        fm = parse_frontmatter(issue.read_text())
        # Matches IssueParser.parse_file's `if parent is None` precedence.
        assert fm["parent"] == "ENH-800"
        assert "parent_issue" not in fm


class TestMigrateRelationshipsBodySafety:
    """Deprecated keys outside frontmatter must never be rewritten."""

    def test_body_line_starting_with_deprecated_key_is_untouched(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        issue = project / ".issues" / "bugs" / "P2-BUG-950-prose.md"
        body = (
            "\n# Prose\n\n"
            "The old shape looked like this:\n\n"
            "```yaml\n"
            "parent_issue: FEAT-001\n"
            "related: BUG-002\n"
            "```\n\n"
            "parent_issue: FEAT-001 was the deprecated spelling.\n"
        )
        issue.write_text(f"---\nid: BUG-950\nparent_issue: BUG-900\n---\n{body}")

        rc = _run_migrate_relationships(project)

        assert rc == 0
        text = issue.read_text()
        fm = parse_frontmatter(text)
        assert fm["parent"] == "BUG-900"
        assert "parent_issue" not in fm
        # Every body occurrence survives verbatim.
        assert text.endswith(body)

    def test_multiline_list_value_is_fully_removed(self, tmp_path: Path) -> None:
        """A block-sequence `related:` must not leave orphaned `- item` lines."""
        project = _make_project(tmp_path)
        issue = project / ".issues" / "bugs" / "P2-BUG-960-list.md"
        issue.write_text(
            "---\nid: BUG-960\nrelated:\n  - BUG-001\n  - BUG-002\nstatus: open\n---\n\n# List\n"
        )

        rc = _run_migrate_relationships(project)

        assert rc == 0
        fm = parse_frontmatter(issue.read_text())
        assert fm["relates_to"] == ["BUG-001", "BUG-002"]
        assert "related" not in fm
        assert fm["status"] == "open"
        # The items moved under relates_to rather than being left orphaned:
        # exactly one copy each, and the block still parses as valid YAML.
        text = issue.read_text()
        assert text.count("- BUG-001") == 1
        assert text.count("- BUG-002") == 1
