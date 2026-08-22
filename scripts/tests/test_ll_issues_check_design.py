"""Subprocess-level tests for ll-issues check-design (ENH-2967).

Mirrors test_ll_issues_check_decidable.py's pattern: subprocess invocation with
the CLI binary, exit-code contract (0 = Program Design gate passes / 1 =
gate failed / 2 = issue not found — BUG-3294), side-effect-free, deterministic.

check-design replaces the three inline `python3 -c "..."` DESIGN_FAIL blocks
in autodev.yaml with a single owned predicate
(`little_loops.issue_parser.design_gate_failed`).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_VALID_SECTION = """
### Types

- `sha: str`

### Signatures

- `design_gate_failed(gaps: FormatGaps) -> bool`

### Call Path

`cmd_check_design` -> `check_format_gaps` -> `design_gate_failed`
"""


def _cli() -> list[str]:
    """Return the ll-issues CLI invocation. Uses the installed binary if available,
    otherwise falls back to ``python -m little_loops.cli`` (which has the same
    ``main_issues`` entry point).
    """
    if shutil.which("ll-issues") is not None:
        return ["ll-issues"]
    import sys

    return [sys.executable, "-m", "little_loops.cli"]


def _clean_bug_body(*, program_design: str | None) -> str:
    """A structurally complete BUG issue body, optionally with a Program Design section."""
    sections = [
        "---",
        "id: BUG-9600",
        "status: open",
        "discovered_date: 2026-07-20",
        "---",
        "",
        "# BUG-9600: Something broke",
        "",
        "## Summary",
        "The widget explodes when the input is empty.",
        "",
        "## Steps to Reproduce",
        "1. Open the widget\n2. Submit an empty form",
        "",
        "## Current Behavior",
        "It explodes.",
        "",
        "## Expected Behavior",
        "It should not break.",
        "",
        "## Actual Behavior",
        "It breaks loudly.",
        "",
        "## Impact",
        "- **Priority**: P3 - Minor annoyance for a rare input.",
        "",
        "## Status",
        "**Open** | Created: 2026-07-20 | Priority: P3",
    ]
    if program_design is not None:
        sections.insert(-3, "## Program Design")
        sections.insert(-3, program_design.strip())
        sections.insert(-3, "")
    return "\n".join(sections) + "\n"


@pytest.fixture
def temp_project_dir(tmp_path: Path) -> Path:
    """Project root with .issues/ tree matching project layout."""
    issues = tmp_path / ".issues"
    for kind in ("bugs", "features", "enhancements", "epics"):
        (issues / kind).mkdir(parents=True, exist_ok=True)
    return tmp_path


def _stamp_gate(project_root: Path, stamp_date: str = "2026-07-01") -> None:
    """Arm the Program Design specificity gate (opt-in per project)."""
    ll_dir = project_root / ".ll"
    ll_dir.mkdir(exist_ok=True)
    (ll_dir / "program-design-cutover.json").write_text(
        json.dumps({"sha": "0" * 40, "date": stamp_date}), encoding="utf-8"
    )


def _write_issue(project_root: Path, body: str, filename: str) -> Path:
    issue_path = project_root / ".issues" / "bugs" / filename
    issue_path.write_text(body, encoding="utf-8")
    return issue_path


def _init_git_repo_with_resolvable_anchor(project_root: Path) -> None:
    """Init a real git repo with a `design_gate_failed` def, so the Program Design
    section's `### Call Path` anchor resolves via git grep (ENH-2852 specificity check).
    """
    subprocess.run(["git", "init", "-q"], cwd=project_root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=project_root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=project_root, check=True)
    (project_root / "mod.py").write_text(
        "def design_gate_failed(gaps):\n    return False\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=project_root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=project_root, check=True)


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


class TestCheckDesignGatePasses:
    """A specific, non-boilerplate Program Design section exits 0."""

    def test_valid_section_exits_zero(self, temp_project_dir: Path) -> None:
        _stamp_gate(temp_project_dir)
        _write_issue(
            temp_project_dir,
            _clean_bug_body(program_design=_VALID_SECTION),
            "P3-BUG-9600-test-bug.md",
        )
        _init_git_repo_with_resolvable_anchor(temp_project_dir)
        result = _invoke(temp_project_dir, "check-design", "BUG-9600")
        assert result.returncode == 0, (
            f"A specific Program Design section must pass, got {result.returncode}: "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )

    def test_unstamped_project_exits_zero(self, temp_project_dir: Path) -> None:
        """Gate is opt-in: no cutover stamp means the gate is inert (fail open)."""
        _write_issue(
            temp_project_dir,
            _clean_bug_body(program_design=None),
            "P3-BUG-9600-test-bug.md",
        )
        result = _invoke(temp_project_dir, "check-design", "BUG-9600")
        assert result.returncode == 0


class TestCheckDesignGateFails:
    """A missing Program Design section (once the gate is armed) exits 1."""

    def test_missing_section_exits_one(self, temp_project_dir: Path) -> None:
        _stamp_gate(temp_project_dir)
        _write_issue(
            temp_project_dir,
            _clean_bug_body(program_design=None),
            "P3-BUG-9600-test-bug.md",
        )
        result = _invoke(temp_project_dir, "check-design", "BUG-9600")
        assert result.returncode == 1


class TestCheckDesignErrorHandling:
    """The check distinguishes an unresolvable issue (exit 2) from a genuine
    gate failure (exit 1) — BUG-3294."""

    def test_missing_issue_exits_two(self, temp_project_dir: Path) -> None:
        result = _invoke(temp_project_dir, "check-design", "BUG-9999")
        assert result.returncode == 2
        assert "BUG-9999" in result.stderr
        assert "not found" in result.stderr.lower() or "Error" in result.stderr


class TestCliRegistration:
    """The check-design subcommand is registered in ll-issues __main__."""

    def test_subcommand_in_help(self, temp_project_dir: Path) -> None:
        result = _invoke(temp_project_dir, "--help")
        assert result.returncode == 0
        assert "check-design" in result.stdout
