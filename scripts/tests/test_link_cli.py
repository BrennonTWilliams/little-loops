"""Tests for ll-issues link sub-command (FEAT-2842)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch


def _write_issue(issues_dir: Path, filename: str, content: str) -> Path:
    path = issues_dir / "features" / filename
    path.write_text(content)
    return path


class TestIssuesCLILink:
    """Tests for ll-issues link sub-command."""

    def _run(self, temp_project_dir: Path, *cli_args: str) -> int:
        with patch.object(
            sys,
            "argv",
            ["ll-issues", "link", *cli_args, "--config", str(temp_project_dir)],
        ):
            from little_loops.cli import main_issues

            return main_issues()

    def test_link_blocked_by_creates_new_key(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        a = _write_issue(
            issues_dir, "P2-FEAT-110-a.md", "---\nid: FEAT-110\nstatus: open\n---\n# FEAT-110: A\n"
        )
        _write_issue(
            issues_dir, "P2-FEAT-109-b.md", "---\nid: FEAT-109\nstatus: open\n---\n# FEAT-109: B\n"
        )

        result = self._run(temp_project_dir, "FEAT-110", "--blocked-by", "FEAT-109")

        assert result == 0
        content = a.read_text()
        assert "blocked_by" in content
        assert "FEAT-109" in content

    def test_link_is_idempotent_no_duplicate_entry(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        a = _write_issue(
            issues_dir, "P2-FEAT-110-a.md", "---\nid: FEAT-110\nstatus: open\n---\n# FEAT-110: A\n"
        )
        _write_issue(
            issues_dir, "P2-FEAT-109-b.md", "---\nid: FEAT-109\nstatus: open\n---\n# FEAT-109: B\n"
        )

        assert self._run(temp_project_dir, "FEAT-110", "--blocked-by", "FEAT-109") == 0
        assert self._run(temp_project_dir, "FEAT-110", "--blocked-by", "FEAT-109") == 0

        content = a.read_text()
        assert content.count("FEAT-109") == 1
        assert content.count("blocked_by:") == 1

    def test_link_appends_to_existing_list(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        a = _write_issue(
            issues_dir,
            "P2-FEAT-110-a.md",
            "---\nid: FEAT-110\nstatus: open\nblocked_by:\n- FEAT-108\n---\n# FEAT-110: A\n",
        )
        _write_issue(
            issues_dir, "P2-FEAT-109-b.md", "---\nid: FEAT-109\nstatus: open\n---\n# FEAT-109: B\n"
        )

        assert self._run(temp_project_dir, "FEAT-110", "--blocked-by", "FEAT-109") == 0

        content = a.read_text()
        assert "FEAT-108" in content
        assert "FEAT-109" in content

    def test_link_unknown_target_exits_nonzero_without_modifying_file(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        a = _write_issue(
            issues_dir, "P2-FEAT-110-a.md", "---\nid: FEAT-110\nstatus: open\n---\n# FEAT-110: A\n"
        )
        original = a.read_text()

        result = self._run(temp_project_dir, "FEAT-110", "--blocked-by", "FEAT-999")

        assert result != 0
        assert a.read_text() == original

    def test_link_no_unknown_warning_for_done_blocker(
        self,
        temp_project_dir: Path,
        sample_config: dict[str, Any],
        issues_dir: Path,
        caplog: Any,
    ) -> None:
        """A blocked_by edge pointing at a done issue must not warn as unknown.

        `_check_cycle` builds the graph from `find_issues_for_graph`, which
        excludes terminal statuses (done/cancelled) by design (BUG-2897) — so
        a done blocker is legitimately absent from that issue list. Without
        passing `all_known_ids` to `DependencyGraph.from_issues`, that absence
        is indistinguishable from a typo'd/nonexistent ID and gets logged as
        an "unknown issue" warning.
        """
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        _write_issue(
            issues_dir,
            "P2-FEAT-110-a.md",
            "---\nid: FEAT-110\nstatus: open\nblocked_by:\n- FEAT-100\n---\n# FEAT-110: A\n",
        )
        _write_issue(
            issues_dir, "P2-FEAT-100-c.md", "---\nid: FEAT-100\nstatus: done\n---\n# FEAT-100: C\n"
        )
        _write_issue(
            issues_dir, "P2-FEAT-101-d.md", "---\nid: FEAT-101\nstatus: open\n---\n# FEAT-101: D\n"
        )

        import logging

        with caplog.at_level(logging.WARNING):
            result = self._run(temp_project_dir, "FEAT-110", "--depends-on", "FEAT-101")

        assert result == 0
        assert "FEAT-100" not in caplog.text

    def test_link_cycle_refused_nonzero_exit(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        _write_issue(
            issues_dir,
            "P2-FEAT-110-a.md",
            "---\nid: FEAT-110\nstatus: open\nblocked_by:\n- FEAT-109\n---\n# FEAT-110: A\n",
        )
        _write_issue(
            issues_dir, "P2-FEAT-109-b.md", "---\nid: FEAT-109\nstatus: open\n---\n# FEAT-109: B\n"
        )

        # FEAT-109 blocked_by FEAT-110 would create a cycle (110 -> 109 -> 110)
        result = self._run(temp_project_dir, "FEAT-109", "--blocked-by", "FEAT-110")

        assert result != 0

    def test_link_preserves_unrelated_frontmatter_and_body(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        a = _write_issue(
            issues_dir,
            "P2-FEAT-110-a.md",
            "---\nid: FEAT-110\nstatus: open\npriority: P2\n---\n# FEAT-110: A\n\nSome body text.\n",
        )
        _write_issue(
            issues_dir, "P2-FEAT-109-b.md", "---\nid: FEAT-109\nstatus: open\n---\n# FEAT-109: B\n"
        )

        assert self._run(temp_project_dir, "FEAT-110", "--blocked-by", "FEAT-109") == 0

        content = a.read_text()
        assert "priority: P2" in content
        assert "# FEAT-110: A" in content
        assert "Some body text." in content

    def test_link_unlink_removes_entry(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        a = _write_issue(
            issues_dir,
            "P2-FEAT-110-a.md",
            "---\nid: FEAT-110\nstatus: open\nblocked_by:\n- FEAT-109\n---\n# FEAT-110: A\n",
        )
        _write_issue(
            issues_dir, "P2-FEAT-109-b.md", "---\nid: FEAT-109\nstatus: open\n---\n# FEAT-109: B\n"
        )

        result = self._run(temp_project_dir, "FEAT-110", "--blocked-by", "FEAT-109", "--unlink")

        assert result == 0
        content = a.read_text()
        assert "FEAT-109" not in content

    def test_link_json_output(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        _write_issue(
            issues_dir, "P2-FEAT-110-a.md", "---\nid: FEAT-110\nstatus: open\n---\n# FEAT-110: A\n"
        )
        _write_issue(
            issues_dir, "P2-FEAT-109-b.md", "---\nid: FEAT-109\nstatus: open\n---\n# FEAT-109: B\n"
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-issues",
                "link",
                "FEAT-110",
                "--blocked-by",
                "FEAT-109",
                "--json",
                "--config",
                str(temp_project_dir),
            ],
        ):
            from little_loops.cli import main_issues

            result = main_issues()

        assert result == 0

    def test_link_dry_run_does_not_modify_file(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        a = _write_issue(
            issues_dir, "P2-FEAT-110-a.md", "---\nid: FEAT-110\nstatus: open\n---\n# FEAT-110: A\n"
        )
        original = a.read_text()
        _write_issue(
            issues_dir, "P2-FEAT-109-b.md", "---\nid: FEAT-109\nstatus: open\n---\n# FEAT-109: B\n"
        )

        result = self._run(temp_project_dir, "FEAT-110", "--blocked-by", "FEAT-109", "--dry-run")

        assert result == 0
        assert a.read_text() == original

    def test_link_bare_numeric_id_resolves(
        self, temp_project_dir: Path, sample_config: dict[str, Any], issues_dir: Path
    ) -> None:
        config_path = temp_project_dir / ".ll" / "ll-config.json"
        config_path.write_text(json.dumps(sample_config))

        a = _write_issue(
            issues_dir, "P2-FEAT-110-a.md", "---\nid: FEAT-110\nstatus: open\n---\n# FEAT-110: A\n"
        )
        _write_issue(
            issues_dir, "P2-FEAT-109-b.md", "---\nid: FEAT-109\nstatus: open\n---\n# FEAT-109: B\n"
        )

        result = self._run(temp_project_dir, "110", "--blocked-by", "109")

        assert result == 0
        assert "FEAT-109" in a.read_text()
