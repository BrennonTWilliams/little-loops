"""Subprocess-level tests for ll-issues check-flag (BUG-3294).

Highest-traffic probe in the check-* family (18 gate sites) with no prior
dedicated test file. Mirrors the sibling quartet shape (`_cli()` /
`temp_project_dir` / `_write_issue()` / `_invoke()`) used by
test_ll_issues_check_decidable.py and friends.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


def _cli() -> list[str]:
    """Return the ll-issues CLI invocation. Uses the installed binary if available,
    otherwise falls back to ``python -m little_loops.cli`` (which has the same
    ``main_issues`` entry point).
    """
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
    """Write an issue into .issues/features/ and return its path.

    The filename pattern matches ``_resolve_issue_id``'s glob (``*-{id}-*.md``),
    so the file must contain the numeric ID in its name.
    """
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
    """Run the CLI in *project_root* and return the completed process."""
    env = os.environ.copy()
    return subprocess.run(
        [*_cli(), *args],
        cwd=str(project_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _body(issue_id: str, extra_frontmatter: str) -> str:
    return (
        "---\n"
        f"id: {issue_id}\n"
        "title: Test\n"
        "type: feature\n"
        "status: open\n"
        "priority: P3\n"
        f"{extra_frontmatter}"
        "---\n\n"
        f"# {issue_id}\n\n"
        "## Summary\n\nTest.\n\n"
        "## Labels\n\n`feature`\n\n"
    )


class TestCheckFlagHappyPath:
    """A boolean frontmatter field set to true exits 0."""

    def test_field_true_exits_zero(self, temp_project_dir: Path) -> None:
        body = _body("FEAT-9201", "decision_needed: true\n")
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-flag", "FEAT-9201", "decision_needed")
        assert result.returncode == 0, (
            f"true field must exit 0, got {result.returncode}: "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )


class TestCheckFlagFalseOrAbsent:
    """A false or absent boolean frontmatter field exits 1 (genuine negative)."""

    def test_field_false_exits_one(self, temp_project_dir: Path) -> None:
        body = _body("FEAT-9202", "decision_needed: false\n")
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-flag", "FEAT-9202", "decision_needed")
        assert result.returncode == 1

    def test_field_absent_exits_one(self, temp_project_dir: Path) -> None:
        body = _body("FEAT-9203", "")
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-flag", "FEAT-9203", "decision_needed")
        assert result.returncode == 1


class TestCheckFlagErrorHandling:
    """The probe reports missing issues via stderr (exit code updated in BUG-3294 Phase B)."""

    def test_missing_issue_exits_one(self, temp_project_dir: Path) -> None:
        result = _invoke(temp_project_dir, "check-flag", "FEAT-9999", "decision_needed")
        assert result.returncode == 1
        assert "FEAT-9999" in result.stderr
        assert "not found" in result.stderr.lower() or "Error" in result.stderr


class TestCliRegistration:
    """The check-flag subcommand is registered in ll-issues __main__."""

    def test_subcommand_in_help(self, temp_project_dir: Path) -> None:
        result = _invoke(temp_project_dir, "--help")
        assert result.returncode == 0
        assert "check-flag" in result.stdout
