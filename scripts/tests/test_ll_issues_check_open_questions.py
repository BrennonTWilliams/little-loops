"""Subprocess-level tests for ll-issues check-open-questions (ENH-2446).

Mirrors the test_ll_issues_format_check.py pattern: subprocess invocation with
the CLI binary, exit-code contract (0 = clean / 1 = OPEN_QUESTIONS_REMAIN),
side-effect-free, deterministic. Establishes a new pattern; the sibling
ll-issues check-decidable has no equivalent subprocess test file (per the
issue's Codebase Research Findings).
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
        # Try to extract id from frontmatter.
        for line in body.splitlines()[:10]:
            if line.startswith("id:"):
                issue_id = line.split(":", 1)[1].strip()
                break
    if not issue_id:
        issue_id = "FEAT-9000"
    # Strip type prefix for the filename glob.
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


def _clean_feature(id: str, decision_needed: bool, body_extras: str = "") -> str:
    """Build a clean issue body with arbitrary extras appended."""
    flag = "true" if decision_needed else "false"
    return (
        f"---\n"
        f"id: {id}\n"
        f"title: Test feature {id}\n"
        f"type: feature\n"
        f"status: open\n"
        f"priority: P3\n"
        f"decision_needed: {flag}\n"
        f"---\n\n"
        f"# {id}: Test feature\n\n"
        f"## Summary\n\nTest.\n\n"
        f"## Proposed Solution\n\n### Option A\nDo X.\n\n> **Selected:** A\n\n"
        f"## Edge Cases\n\n- All handled.\n\n"
        f"## Confidence Check Notes\n\n- All clear.\n\n"
        f"## Implementation Status\n\nNone.\n\n"
        f"## Labels\n\n`feature`, `test`\n\n"
        f"---\n\n## Status\n**Open** | Created: 2026-07-08 | Priority: P3\n"
    )


class TestCheckOpenQuestionsHappyPath:
    """Clean issue (resolved options, no open questions) exits 0."""

    def test_clean_issue_exits_zero(self, temp_project_dir: Path) -> None:
        _write_issue(temp_project_dir, _clean_feature("FEAT-9001", decision_needed=True))
        result = _invoke(temp_project_dir, "check-open-questions", "FEAT-9001")
        assert result.returncode == 0, (
            f"Clean issue must exit 0, got {result.returncode}: "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "FEAT-9001" in result.stdout

    def test_decision_not_needed_still_exits_zero(self, temp_project_dir: Path) -> None:
        """The probe is purely structural — decision_needed doesn't gate it."""
        _write_issue(temp_project_dir, _clean_feature("FEAT-9002", decision_needed=False))
        result = _invoke(temp_project_dir, "check-open-questions", "FEAT-9002")
        assert result.returncode == 0


class TestCheckOpenQuestionsUnresolved:
    """Issue with open questions / unresolved options exits 1 with token."""

    def test_unresolved_options_exit_one(self, temp_project_dir: Path) -> None:
        body = (
            "---\n"
            "id: FEAT-9003\n"
            "title: Test\n"
            "type: feature\n"
            "status: open\n"
            "priority: P3\n"
            "decision_needed: true\n"
            "---\n\n"
            "# FEAT-9003\n\n"
            "## Summary\n\nTest.\n\n"
            "## Proposed Solution\n\n"
            "### Option A\nDo X.\n\n"
            "### Option B\nDo Y.\n\n"
            "## Edge Cases\n\n- All handled.\n\n"
            "## Confidence Check Notes\n\n- All clear.\n\n"
            "## Implementation Status\n\nNone.\n\n"
            "## Labels\n\n`feature`\n\n"
            "---\n\n## Status\n**Open** | Created: 2026-07-08 | Priority: P3\n"
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-open-questions", "FEAT-9003")
        assert result.returncode == 1, (
            f"Unresolved options must exit 1, got {result.returncode}: "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "OPEN_QUESTIONS_REMAIN" in result.stderr
        assert "FEAT-9003" in result.stderr
        assert "2 unresolved option" in result.stderr

    def test_open_questions_in_edge_cases_exit_one(self, temp_project_dir: Path) -> None:
        body = (
            "---\n"
            "id: FEAT-9004\n"
            "title: Test\n"
            "type: feature\n"
            "status: open\n"
            "priority: P3\n"
            "decision_needed: true\n"
            "---\n\n"
            "# FEAT-9004\n\n"
            "## Summary\n\nTest.\n\n"
            "## Proposed Solution\n\n### Option A\nDo X.\n\n> **Selected:** A\n\n"
            "## Edge Cases\n\n"
            "- Q: How to handle malformed JSON? Open question.\n"
            "- Q: What if upstream is down? Needs decision.\n"
            "\n"
            "## Confidence Check Notes\n\n- All clear.\n\n"
            "## Implementation Status\n\nNone.\n\n"
            "## Labels\n\n`feature`\n\n"
            "---\n\n## Status\n**Open** | Created: 2026-07-08 | Priority: P3\n"
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-open-questions", "FEAT-9004")
        assert result.returncode == 1
        assert "OPEN_QUESTIONS_REMAIN" in result.stderr
        assert "FEAT-9004" in result.stderr
        assert "2 open question" in result.stderr

    def test_mixed_unresolved_and_open(self, temp_project_dir: Path) -> None:
        """Mixed surface: 1 unresolved option + 1 open question = both counts in stderr."""
        body = (
            "---\n"
            "id: FEAT-9005\n"
            "title: Test\n"
            "type: feature\n"
            "status: open\n"
            "priority: P3\n"
            "decision_needed: true\n"
            "---\n\n"
            "# FEAT-9005\n\n"
            "## Summary\n\nTest.\n\n"
            "## Proposed Solution\n\n"
            "### Option A\nDo X.\n\n> **Selected:** A\n\n"
            "### Option B\nDo Y.\n\n"
            "## Edge Cases\n\n- Q: Why? Open question.\n\n"
            "## Confidence Check Notes\n\n- All clear.\n\n"
            "## Implementation Status\n\nNone.\n\n"
            "## Labels\n\n`feature`\n\n"
            "---\n\n## Status\n**Open** | Created: 2026-07-08 | Priority: P3\n"
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-open-questions", "FEAT-9005")
        assert result.returncode == 1
        assert "1 unresolved option" in result.stderr
        assert "1 open question" in result.stderr


class TestCheckOpenQuestionsErrorHandling:
    """The probe handles missing issues gracefully (exit 1 with error token)."""

    def test_missing_issue_exits_one(self, temp_project_dir: Path) -> None:
        result = _invoke(temp_project_dir, "check-open-questions", "FEAT-9999")
        assert result.returncode == 1
        assert "FEAT-9999" in result.stderr
        assert "not found" in result.stderr.lower() or "Error" in result.stderr


class TestCliRegistration:
    """The check-open-questions subcommand is registered in ll-issues __main__."""

    def test_subcommand_in_help(self, temp_project_dir: Path) -> None:
        result = _invoke(temp_project_dir, "--help")
        assert result.returncode == 0
        assert "check-open-questions" in result.stdout
