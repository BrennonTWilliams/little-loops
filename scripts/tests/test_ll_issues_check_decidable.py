"""Subprocess-level tests for ll-issues check-decidable (BUG-2820).

Mirrors test_ll_issues_check_open_questions.py's pattern: subprocess
invocation with the CLI binary, exit-code contract (0 = decidable /
1 = OPTIONS_MISSING), side-effect-free, deterministic. Closes the
subprocess-contract-test gap that file's own docstring flags for the
sibling ``check-decidable`` command.
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


class TestCheckDecidableHappyPath:
    """Options deposited into ## Proposed Solution are decidable (exit 0)."""

    def test_options_in_proposed_solution_exit_zero(self, temp_project_dir: Path) -> None:
        body = (
            "---\n"
            "id: FEAT-9101\n"
            "title: Test\n"
            "type: feature\n"
            "status: open\n"
            "priority: P3\n"
            "decision_needed: true\n"
            "---\n\n"
            "# FEAT-9101\n\n"
            "## Summary\n\nTest.\n\n"
            "## Proposed Solution\n\n"
            "**Option A**: Do X.\n\n"
            "**Option B**: Do Y.\n\n"
            "**Recommended**: Option A\n\n"
            "## Labels\n\n`feature`\n\n"
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-decidable", "FEAT-9101")
        assert result.returncode == 0, (
            f"Options in Proposed Solution must be decidable, got {result.returncode}: "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "FEAT-9101" in result.stdout


class TestCheckDecidableMissingOptions:
    """Options deposited outside the scanned sections are invisible (exit 1)."""

    def test_options_under_open_questions_exit_one(self, temp_project_dir: Path) -> None:
        """Regression fixture for BUG-2820: options nested under an H3 inside
        ## Open Questions are not reachable by count_enumerable_options()."""
        body = (
            "---\n"
            "id: FEAT-9102\n"
            "title: Test\n"
            "type: feature\n"
            "status: open\n"
            "priority: P3\n"
            "decision_needed: true\n"
            "---\n\n"
            "# FEAT-9102\n\n"
            "## Summary\n\nTest.\n\n"
            "## Proposed Solution\n\nSome unrelated prose, no options here.\n\n"
            "## Open Questions\n\n"
            "### Codebase Research Findings — delegation architecture decision\n\n"
            "**Option A**: Do X.\n\n"
            "**Option B**: Do Y.\n\n"
            "**Recommended**: Option A\n\n"
            "## Labels\n\n`feature`\n\n"
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-decidable", "FEAT-9102")
        assert result.returncode == 1, (
            f"Options outside scanned sections must not be decidable, got {result.returncode}: "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "OPTIONS_MISSING" in result.stderr
        assert "FEAT-9102" in result.stderr

    def test_no_options_at_all_exit_one(self, temp_project_dir: Path) -> None:
        body = (
            "---\n"
            "id: FEAT-9103\n"
            "title: Test\n"
            "type: feature\n"
            "status: open\n"
            "priority: P3\n"
            "decision_needed: true\n"
            "---\n\n"
            "# FEAT-9103\n\n"
            "## Summary\n\nTest.\n\n"
            "## Proposed Solution\n\nNo enumerable options here.\n\n"
            "## Labels\n\n`feature`\n\n"
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-decidable", "FEAT-9103")
        assert result.returncode == 1
        assert "OPTIONS_MISSING" in result.stderr


class TestCheckDecidableErrorHandling:
    """The probe handles missing issues gracefully (exit 1 with error token)."""

    def test_missing_issue_exits_one(self, temp_project_dir: Path) -> None:
        result = _invoke(temp_project_dir, "check-decidable", "FEAT-9999")
        assert result.returncode == 1
        assert "FEAT-9999" in result.stderr
        assert "not found" in result.stderr.lower() or "Error" in result.stderr


class TestCliRegistration:
    """The check-decidable subcommand is registered in ll-issues __main__."""

    def test_subcommand_in_help(self, temp_project_dir: Path) -> None:
        result = _invoke(temp_project_dir, "--help")
        assert result.returncode == 0
        assert "check-decidable" in result.stdout
