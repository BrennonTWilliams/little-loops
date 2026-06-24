"""Tests for ll-issues set-status sub-command (ENH-1725)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


class TestIssuesCLISetStatus:
    """Tests for ll-issues set-status sub-command."""

    def test_set_status_writes_new_status(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """set-status updates the status field and prints the transition."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        issue_file.write_text(
            "---\nid: BUG-001\nstatus: open\n---\n# BUG-001: Critical crash on startup\n"
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "set-status",
                "BUG-001",
                "in_progress",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        content = issue_file.read_text()
        assert "status: in_progress" in content

    def test_set_status_prints_transition(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """set-status prints 'old → new' to stdout on success."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        issue_file.write_text("---\nid: BUG-001\nstatus: open\n---\n# BUG-001: Critical crash\n")

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "set-status", "BUG-001", "done", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "open" in captured.out
        assert "done" in captured.out

    def test_set_status_preserves_unrelated_fields(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """set-status only updates status; other frontmatter fields are unchanged."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        issue_file = issues_dir / "bugs" / "P0-BUG-001-critical-crash.md"
        issue_file.write_text(
            "---\n"
            "id: BUG-001\n"
            "status: open\n"
            "captured_at: '2026-01-01T00:00:00Z'\n"
            "confidence_score: 88\n"
            "---\n"
            "# BUG-001: Critical crash\n"
        )

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "set-status", "BUG-001", "blocked", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        content = issue_file.read_text()
        assert "status: blocked" in content
        assert "captured_at" in content
        assert "confidence_score: 88" in content

    def test_set_status_nonexistent_issue_returns_1(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """set-status returns exit code 1 when the issue ID does not exist."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "set-status", "BUG-999", "done", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1

    def test_set_status_invalid_value_rejected(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """set-status with an invalid status value causes argparse to exit with code 2."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "set-status", "BUG-001", "wip", "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            with pytest.raises(SystemExit) as exc_info:
                main_issues()

        assert exc_info.value.code == 2

    # ── Cascade tests ──────────────────────────────────────────────

    def test_cascade_no_children_noop(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--cascade with an EPIC that has no children is a no-op (exit 0)."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        epics_dir = issues_dir / "epics"
        (epics_dir / "P2-EPIC-001-solo-epic.md").write_text(
            "---\nid: EPIC-001\nstatus: open\n---\n# EPIC-001: Solo EPIC\n"
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "set-status",
                "EPIC-001",
                "cancelled",
                "--cascade",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "open" in captured.out
        assert "cancelled" in captured.out
        assert "Cascading to 0" in captured.out

    def test_cascade_active_children_get_deferred_by_default(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--cascade defaults to --cascade-to deferred for active children."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        epics_dir = issues_dir / "epics"
        (epics_dir / "P2-EPIC-001-test-epic.md").write_text(
            "---\nid: EPIC-001\nstatus: open\n---\n# EPIC-001: Test EPIC\n"
        )

        enhancements_dir = issues_dir / "enhancements"
        enhancements_dir.mkdir(parents=True, exist_ok=True)
        (enhancements_dir / "P3-ENH-001-child-a.md").write_text(
            "---\nid: ENH-001\nstatus: open\nparent: EPIC-001\n---\n# ENH-001: Child A\n"
        )
        (enhancements_dir / "P3-ENH-002-child-b.md").write_text(
            "---\nid: ENH-002\nstatus: in_progress\nparent: EPIC-001\n---\n# ENH-002: Child B\n"
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "set-status",
                "EPIC-001",
                "cancelled",
                "--cascade",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "EPIC-001" in captured.out
        assert "Cascading to 2" in captured.out
        assert "deferred" in captured.out

        # Verify children got deferred
        assert "status: deferred" in (enhancements_dir / "P3-ENH-001-child-a.md").read_text()
        assert "status: deferred" in (enhancements_dir / "P3-ENH-002-child-b.md").read_text()

    def test_cascade_to_done_closes_all_open_children(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """--cascade --cascade-to done closes all open children."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        epics_dir = issues_dir / "epics"
        (epics_dir / "P2-EPIC-001-test-epic.md").write_text(
            "---\nid: EPIC-001\nstatus: open\n---\n# EPIC-001: Test EPIC\n"
        )

        enhancements_dir = issues_dir / "enhancements"
        enhancements_dir.mkdir(parents=True, exist_ok=True)
        (enhancements_dir / "P3-ENH-001-child-a.md").write_text(
            "---\nid: ENH-001\nstatus: open\nparent: EPIC-001\n---\n# ENH-001: Child A\n"
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "set-status",
                "EPIC-001",
                "done",
                "--cascade",
                "--cascade-to",
                "done",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        assert "status: done" in (enhancements_dir / "P3-ENH-001-child-a.md").read_text()

    def test_cascade_mixed_active_and_terminal_children(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Only active children change; already terminal children are skipped."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        epics_dir = issues_dir / "epics"
        (epics_dir / "P2-EPIC-001-test-epic.md").write_text(
            "---\nid: EPIC-001\nstatus: open\n---\n# EPIC-001: Test EPIC\n"
        )

        enhancements_dir = issues_dir / "enhancements"
        enhancements_dir.mkdir(parents=True, exist_ok=True)
        (enhancements_dir / "P3-ENH-001-active.md").write_text(
            "---\nid: ENH-001\nstatus: open\nparent: EPIC-001\n---\n# ENH-001: Active child\n"
        )
        (enhancements_dir / "P3-ENH-002-already-done.md").write_text(
            "---\nid: ENH-002\nstatus: done\nparent: EPIC-001\n---\n# ENH-002: Already done\n"
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "set-status",
                "EPIC-001",
                "cancelled",
                "--cascade",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "Cascading to 1" in captured.out
        assert "1" in captured.out  # one skipped (already terminal)
        # Active child changed
        assert "status: deferred" in (enhancements_dir / "P3-ENH-001-active.md").read_text()
        # Already-done child unchanged
        assert "status: done" in (enhancements_dir / "P3-ENH-002-already-done.md").read_text()

    def test_cascade_rejected_for_non_closing_status(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--cascade is rejected when target status is not done/cancelled."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        epics_dir = issues_dir / "epics"
        (epics_dir / "P2-EPIC-001-test-epic.md").write_text(
            "---\nid: EPIC-001\nstatus: open\n---\n# EPIC-001: Test EPIC\n"
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "set-status",
                "EPIC-001",
                "in_progress",
                "--cascade",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 1
        captured = capsys.readouterr()
        assert "only valid" in captured.err.lower() or "cascade" in captured.err.lower()

    def test_cascade_does_not_follow_relates_to(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """relates_to: links must NOT be cascaded (BUG-2265).

        Cascading through association edges silently mutated unrelated issues.
        Only parent: edges may trigger a status change.
        """
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        epics_dir = issues_dir / "epics"
        (epics_dir / "P2-EPIC-001-test-epic.md").write_text(
            "---\n"
            "id: EPIC-001\n"
            "status: open\n"
            "relates_to:\n"
            "  - ENH-001\n"
            "---\n"
            "# EPIC-001: Test EPIC\n"
        )

        enhancements_dir = issues_dir / "enhancements"
        enhancements_dir.mkdir(parents=True, exist_ok=True)
        (enhancements_dir / "P3-ENH-001-related.md").write_text(
            "---\nid: ENH-001\nstatus: open\n---\n# ENH-001: Related (not a child)\n"
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "set-status",
                "EPIC-001",
                "done",
                "--cascade",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        # Related-only issue must be left untouched.
        assert "status: open" in (enhancements_dir / "P3-ENH-001-related.md").read_text()

    def test_cascade_does_not_touch_sibling_epic_via_relates_to(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """BUG-2265 regression: cancelling an epic with relates_to → another epic
        leaves the related epic (and its children) untouched."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        epics_dir = issues_dir / "epics"
        # EPIC-001 relates to sibling EPIC-002 and owns one real child.
        (epics_dir / "P2-EPIC-001-being-cancelled.md").write_text(
            "---\n"
            "id: EPIC-001\n"
            "status: open\n"
            "relates_to:\n"
            "  - EPIC-002\n"
            "---\n"
            "# EPIC-001: Being cancelled\n"
        )
        (epics_dir / "P2-EPIC-002-sibling.md").write_text(
            "---\nid: EPIC-002\nstatus: open\n---\n# EPIC-002: Sibling (related-only)\n"
        )

        features_dir = issues_dir / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        # Real child of EPIC-001 (should cascade).
        (features_dir / "P3-FEAT-001-real-child.md").write_text(
            "---\nid: FEAT-001\nstatus: open\nparent: EPIC-001\n---\n# FEAT-001: Real child\n"
        )
        # Child of the sibling epic (must NOT cascade — one hop away via relates_to).
        (features_dir / "P3-FEAT-002-sibling-child.md").write_text(
            "---\nid: FEAT-002\nstatus: open\nparent: EPIC-002\n---\n# FEAT-002: Sibling child\n"
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "set-status",
                "EPIC-001",
                "cancelled",
                "--cascade",
                "--cascade-to",
                "cancelled",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        # Real child cascaded.
        assert "status: cancelled" in (features_dir / "P3-FEAT-001-real-child.md").read_text()
        # Sibling epic and its child left untouched.
        assert "status: open" in (epics_dir / "P2-EPIC-002-sibling.md").read_text()
        assert "status: open" in (features_dir / "P3-FEAT-002-sibling-child.md").read_text()

    def test_cascade_is_transitive_over_parent_edges(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
    ) -> None:
        """BUG-2265 AC#1: cascade follows parent: edges transitively (grandchildren)."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        epics_dir = issues_dir / "epics"
        (epics_dir / "P2-EPIC-001-root.md").write_text(
            "---\nid: EPIC-001\nstatus: open\n---\n# EPIC-001: Root epic\n"
        )
        # Sub-epic is a child of the root epic.
        (epics_dir / "P2-EPIC-002-sub.md").write_text(
            "---\nid: EPIC-002\nstatus: open\nparent: EPIC-001\n---\n# EPIC-002: Sub epic\n"
        )

        features_dir = issues_dir / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        # Grandchild: child of the sub-epic.
        (features_dir / "P3-FEAT-001-grandchild.md").write_text(
            "---\nid: FEAT-001\nstatus: open\nparent: EPIC-002\n---\n# FEAT-001: Grandchild\n"
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "set-status",
                "EPIC-001",
                "cancelled",
                "--cascade",
                "--cascade-to",
                "cancelled",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        assert "status: cancelled" in (epics_dir / "P2-EPIC-002-sub.md").read_text()
        assert "status: cancelled" in (features_dir / "P3-FEAT-001-grandchild.md").read_text()

    def test_cascade_continues_on_individual_failure(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """If one child update fails, the rest continue; exit code is 1."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        epics_dir = issues_dir / "epics"
        (epics_dir / "P2-EPIC-001-test-epic.md").write_text(
            "---\nid: EPIC-001\nstatus: open\n---\n# EPIC-001: Test EPIC\n"
        )

        enhancements_dir = issues_dir / "enhancements"
        enhancements_dir.mkdir(parents=True, exist_ok=True)
        (enhancements_dir / "P3-ENH-001-good.md").write_text(
            "---\nid: ENH-001\nstatus: open\nparent: EPIC-001\n---\n# ENH-001: Good child\n"
        )
        bad_path = enhancements_dir / "P3-ENH-002-bad.md"
        bad_path.write_text(
            "---\nid: ENH-002\nstatus: open\nparent: EPIC-001\n---\n# ENH-002: Bad child\n"
        )

        # Patch update_frontmatter at its source module so the local import
        # inside cmd_set_status picks up the patched version.
        import little_loops.frontmatter as _fm

        _orig_update = _fm.update_frontmatter

        def _failing_update(content: str, updates: dict) -> str:
            if "ENH-002" in content and updates.get("status") == "deferred":
                raise OSError("simulated disk error")
            return _orig_update(content, updates)

        with patch.object(_fm, "update_frontmatter", _failing_update):
            with patch.object(
                sys,
                "argv",
                [
                    "ll-issues",
                    "set-status",
                    "EPIC-001",
                    "cancelled",
                    "--cascade",
                    "--config",
                    str(temp_project_dir),
                ],
            ):
                from little_loops.cli import main_issues

                result = main_issues()

        assert result == 1  # exit 1 because one child failed
        captured = capsys.readouterr()
        assert "ENH-002" in captured.err or "ENH-002" in captured.out
        # Good child should still have been updated
        assert "status: deferred" in (enhancements_dir / "P3-ENH-001-good.md").read_text()

    def test_cascade_non_epic_noop(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--cascade on a non-EPIC finds no children and is effectively a no-op."""
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        # BUG-001 already exists from issues_dir fixture

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "set-status",
                "BUG-001",
                "done",
                "--cascade",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0
        captured = capsys.readouterr()
        assert "Cascading to 0" in captured.out
