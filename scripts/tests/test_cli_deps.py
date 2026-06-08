"""CLI-layer tests for ll-deps subcommands (analyze, validate).

Complements test_deps_cli.py (tree) and test_dependency_mapper.py (fix/apply).
Focuses on format flags (--format json, --graph, --json) and output routing
not already covered in those files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.deps import main_deps as main

# ---------------------------------------------------------------------------
# Shared helpers (same shape as test_deps_cli.py helpers)
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> Path:
    """Create minimal project structure and return issues_dir."""
    issues_dir = tmp_path / ".issues"
    for subdir in ("bugs", "features", "enhancements", "epics"):
        (issues_dir / subdir).mkdir(parents=True, exist_ok=True)
    ll_dir = tmp_path / ".ll"
    ll_dir.mkdir(exist_ok=True)
    (ll_dir / "ll-config.json").write_text('{"issues": {"base_dir": ".issues"}}')
    return issues_dir


def _write_issue(
    directory: Path,
    issue_id: str,
    priority: str = "P2",
    status: str = "open",
    title: str | None = None,
    blocked_by: list[str] | None = None,
) -> Path:
    slug = (title or issue_id).lower().replace(" ", "-")
    filename = f"{priority}-{issue_id}-{slug}.md"
    lines = ["---", f"status: {status}"]
    if blocked_by:
        lines.append("blocked_by:")
        for ref in blocked_by:
            lines.append(f"  - {ref}")
    lines += ["---", "", f"# {issue_id}: {title or 'Test ' + issue_id}"]
    (directory / filename).write_text("\n".join(lines))
    return directory / filename


# ---------------------------------------------------------------------------
# analyze subcommand — format routing
# ---------------------------------------------------------------------------


class TestDepsAnalyzeFormat:
    """Test --format flag routing for ll-deps analyze."""

    def test_analyze_json_output_is_valid_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issues_dir = _setup_project(tmp_path)
        _write_issue(issues_dir / "features", "FEAT-001", title="Alpha")
        with patch.object(
            sys, "argv", ["ll-deps", "-d", str(issues_dir), "analyze", "--format", "json"]
        ):
            result = main()
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "issue_count" in data
        assert "proposals" in data
        assert "validation" in data

    def test_analyze_json_empty_proposals_list(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issues_dir = _setup_project(tmp_path)
        _write_issue(issues_dir / "features", "FEAT-001", title="Solo")
        with patch.object(
            sys, "argv", ["ll-deps", "-d", str(issues_dir), "analyze", "--format", "json"]
        ):
            result = main()
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data["proposals"], list)

    def test_analyze_json_parallel_safe_key_present(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issues_dir = _setup_project(tmp_path)
        _write_issue(issues_dir / "features", "FEAT-001", title="A")
        with patch.object(
            sys, "argv", ["ll-deps", "-d", str(issues_dir), "analyze", "--format", "json"]
        ):
            result = main()
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "parallel_safe" in data

    def test_analyze_text_default_produces_markdown(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issues_dir = _setup_project(tmp_path)
        _write_issue(issues_dir / "features", "FEAT-001", title="Feature A")
        with patch.object(sys, "argv", ["ll-deps", "-d", str(issues_dir), "analyze"]):
            result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_analyze_graph_flag_adds_graph_section(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issues_dir = _setup_project(tmp_path)
        _write_issue(issues_dir / "features", "FEAT-001", title="A")
        _write_issue(issues_dir / "features", "FEAT-002", title="B", blocked_by=["FEAT-001"])
        with patch.object(sys, "argv", ["ll-deps", "-d", str(issues_dir), "analyze", "--graph"]):
            result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert "Dependency Graph" in captured.out


# ---------------------------------------------------------------------------
# validate subcommand — format routing and text output
# ---------------------------------------------------------------------------


class TestDepsValidateOutput:
    """Test validate subcommand output formats."""

    def test_validate_json_empty_is_valid_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issues_dir = _setup_project(tmp_path)
        _write_issue(issues_dir / "features", "FEAT-001", title="Clean")
        with patch.object(sys, "argv", ["ll-deps", "-d", str(issues_dir), "validate", "--json"]):
            result = main()
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "has_issues" in data
        assert "broken_refs" in data
        assert "cycles" in data

    def test_validate_json_clean_project_has_no_issues(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issues_dir = _setup_project(tmp_path)
        # Independent issues with no dependency refs → no validation problems
        _write_issue(issues_dir / "features", "FEAT-001", title="A")
        _write_issue(issues_dir / "features", "FEAT-002", title="B")
        with patch.object(sys, "argv", ["ll-deps", "-d", str(issues_dir), "validate", "--json"]):
            result = main()
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["has_issues"] is False

    def test_validate_text_no_issues_message(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issues_dir = _setup_project(tmp_path)
        _write_issue(issues_dir / "features", "FEAT-001", title="Clean")
        with patch.object(sys, "argv", ["ll-deps", "-d", str(issues_dir), "validate"]):
            result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert "No validation issues found" in captured.out

    def test_validate_text_broken_refs_shows_report(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issues_dir = _setup_project(tmp_path)
        # FEAT-001 blocked by nonexistent FEAT-999
        _write_issue(issues_dir / "features", "FEAT-001", title="A", blocked_by=["FEAT-999"])
        with patch.object(sys, "argv", ["ll-deps", "-d", str(issues_dir), "validate"]):
            result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert "FEAT-999" in captured.out or "Broken" in captured.out

    def test_validate_json_broken_refs_detected(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        issues_dir = _setup_project(tmp_path)
        _write_issue(issues_dir / "features", "FEAT-001", title="A", blocked_by=["FEAT-999"])
        with patch.object(sys, "argv", ["ll-deps", "-d", str(issues_dir), "validate", "--json"]):
            result = main()
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["has_issues"] is True
        assert len(data["broken_refs"]) >= 1
