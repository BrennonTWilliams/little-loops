"""Subprocess-level tests for ll-issues locate-options (ENH-2950).

Mirrors test_ll_issues_check_decidable.py's pattern: subprocess invocation with
the CLI binary, JSON dict-shape assertions on --json output, side-effect-free,
deterministic. locate-options widens check-decidable's boolean gate into a full
data frontend so decide-issue Phase 3/3b can read spans instead of
re-implementing the same precedence chain in prose.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


def _cli() -> list[str]:
    if shutil.which("ll-issues") is not None:
        return ["ll-issues"]
    import sys

    return [sys.executable, "-m", "little_loops.cli"]


@pytest.fixture
def temp_project_dir(tmp_path: Path) -> Path:
    """Project root with .issues/ tree matching project layout."""
    issues = tmp_path / ".issues"
    for kind in ("bugs", "features", "enhancements", "epics"):
        (issues / kind).mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_issue(project_root: Path, body: str, issue_id: str = "") -> Path:
    if not issue_id:
        for line in body.splitlines()[:10]:
            if line.startswith("id:"):
                issue_id = line.split(":", 1)[1].strip()
                break
    if not issue_id:
        issue_id = "FEAT-9000"
    numeric = issue_id.split("-")[-1]
    fname = f"P3-{issue_id}-test-{numeric}.md"
    issue_path = project_root / ".issues" / "features" / fname
    issue_path.write_text(body)
    return issue_path


def _invoke(project_root: Path, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    return subprocess.run(
        [*_cli(), *args],
        cwd=str(project_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestLocateOptionsJsonFlag:
    """--json returns {id, count, pattern, heading, options: [...]}."""

    def test_bold_label_options_json_shape(self, temp_project_dir: Path) -> None:
        body = (
            "---\n"
            "id: FEAT-9201\n"
            "title: Test\n"
            "type: feature\n"
            "status: open\n"
            "priority: P3\n"
            "---\n\n"
            "# FEAT-9201\n\n"
            "## Summary\n\nTest.\n\n"
            "## Proposed Solution\n\n"
            "**Option A**: Do X.\n\n"
            "**Option B**: Do Y.\n\n"
            "## Labels\n\n`feature`\n\n"
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "locate-options", "FEAT-9201", "--json")
        assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
        data = json.loads(result.stdout)
        assert data["id"] == "FEAT-9201"
        assert data["count"] == 2
        assert data["pattern"] == "bold_label"
        assert data["heading"] == "Proposed Solution"
        assert len(data["options"]) == 2
        for option in data["options"]:
            assert set(option) == {"label", "text", "start_line", "end_line"}
        assert data["options"][0]["label"] == "Option A"

    def test_pattern_e_directive_json_shape(self, temp_project_dir: Path) -> None:
        body = (
            "---\n"
            "id: FEAT-9202\n"
            "title: Test\n"
            "type: feature\n"
            "status: open\n"
            "priority: P3\n"
            "---\n\n"
            "# FEAT-9202\n\n"
            "## Summary\n\nTest.\n\n"
            "## Proposed Solution\n\nNo options here.\n\n"
            "## Scope Boundaries\n\n"
            "- stamp it or move it to Out of scope with a stated reason — do not "
            "leave it unaddressed\n\n"
            "## Labels\n\n`feature`\n\n"
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "locate-options", "FEAT-9202", "--json")
        assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
        data = json.loads(result.stdout)
        assert data["count"] == 2
        assert data["pattern"] == "provisional_e"
        assert data["heading"] == "Scope Boundaries"
        assert len(data["options"]) == 1

    def test_no_options_json_shape(self, temp_project_dir: Path) -> None:
        body = (
            "---\n"
            "id: FEAT-9203\n"
            "title: Test\n"
            "type: feature\n"
            "status: open\n"
            "priority: P3\n"
            "---\n\n"
            "# FEAT-9203\n\n"
            "## Summary\n\nTest.\n\n"
            "## Proposed Solution\n\nNo enumerable options here.\n\n"
            "## Labels\n\n`feature`\n\n"
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "locate-options", "FEAT-9203", "--json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["count"] == 0
        assert data["pattern"] is None
        assert data["heading"] is None
        assert data["options"] == []

    def test_last_option_excludes_trailing_subsection(self, temp_project_dir: Path) -> None:
        """BUG-3279: mirrors the live ENH-3277 shape -- a refined issue where
        analysis subsections follow the last option in the same section. The
        last option's `text` must exclude that trailing prose, and its
        `end_line` must land before the next heading, not at the section end."""
        body = (
            "---\n"
            "id: FEAT-9204\n"
            "title: Test\n"
            "type: feature\n"
            "status: open\n"
            "priority: P3\n"
            "---\n\n"
            "# FEAT-9204\n\n"
            "## Summary\n\nTest.\n\n"
            "## Proposed Solution\n\n"
            "### Option A\nDo X.\n\n"
            "### Option B\nDo Y.\n\n"
            "### Codebase Research Findings\n\n"
            "Unrelated analysis prose that belongs to no option.\n\n"
            "## Labels\n\n`feature`\n\n"
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "locate-options", "FEAT-9204", "--json")
        assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
        data = json.loads(result.stdout)
        assert data["count"] == 2
        last_option = data["options"][-1]
        assert "Codebase Research Findings" not in last_option["text"]
        assert "Unrelated analysis prose" not in last_option["text"]
        heading_line = body.splitlines().index("### Codebase Research Findings") + 1
        assert last_option["end_line"] < heading_line


class TestLocateOptionsErrorHandling:
    """Missing issues exit 1 with an error token, matching check-decidable's contract."""

    def test_missing_issue_exits_one(self, temp_project_dir: Path) -> None:
        result = _invoke(temp_project_dir, "locate-options", "FEAT-9999")
        assert result.returncode == 1
        assert "FEAT-9999" in result.stderr
        assert "not found" in result.stderr.lower() or "Error" in result.stderr


class TestCliRegistration:
    """The locate-options subcommand is registered in ll-issues __main__."""

    def test_subcommand_in_help(self, temp_project_dir: Path) -> None:
        result = _invoke(temp_project_dir, "--help")
        assert result.returncode == 0
        assert "locate-options" in result.stdout
