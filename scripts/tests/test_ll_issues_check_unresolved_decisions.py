"""Subprocess-level tests for ll-issues check-unresolved-decisions (BUG-3278).

Mirrors the test_ll_issues_check_open_questions.py pattern: subprocess
invocation with the CLI binary, exit-code contract (0 = clean / 1 =
UNRESOLVED_DECISIONS_REMAIN / 2 = unresolvable ID), side-effect-free,
deterministic.
"""

from __future__ import annotations

import json
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


def _issue_body(id_: str, proposed_solution: str) -> str:
    return (
        f"---\n"
        f"id: {id_}\n"
        f"title: Test feature {id_}\n"
        f"type: feature\n"
        f"status: open\n"
        f"priority: P3\n"
        f"decision_needed: true\n"
        f"---\n\n"
        f"# {id_}: Test feature\n\n"
        f"## Summary\n\nTest.\n\n"
        f"## Proposed Solution\n\n{proposed_solution}\n"
        f"---\n\n## Status\n**Open** | Created: 2026-08-23 | Priority: P3\n"
    )


class TestCheckUnresolvedDecisionsHappyPath:
    """No unresolved decision group -> exit 0."""

    def test_single_decided_group_exits_zero(self, temp_project_dir: Path) -> None:
        body = _issue_body(
            "FEAT-9101",
            "**Option A**: Do X.\n> **Selected:** Option A\n\n**Option B**: Do Y.\n",
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-unresolved-decisions", "FEAT-9101")
        assert result.returncode == 0, (
            f"got {result.returncode}: stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "FEAT-9101" in result.stdout

    def test_no_decision_surface_exits_zero(self, temp_project_dir: Path) -> None:
        body = _issue_body("FEAT-9102", "No enumerable options here, just prose.\n")
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-unresolved-decisions", "FEAT-9102")
        assert result.returncode == 0


class TestCheckUnresolvedDecisionsResidual:
    """A residual decision group -> exit 1 with the group named."""

    def test_undecided_group_exits_one(self, temp_project_dir: Path) -> None:
        body = _issue_body(
            "FEAT-9103",
            "**Option A**: Do X.\n\n**Option B**: Do Y.\n",
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-unresolved-decisions", "FEAT-9103")
        assert result.returncode == 1, (
            f"got {result.returncode}: stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "UNRESOLVED_DECISIONS_REMAIN" in result.stderr
        assert "FEAT-9103" in result.stderr
        assert "Proposed Solution" in result.stderr

    def test_second_lower_precedence_group_exits_one_even_when_first_is_decided(
        self, temp_project_dir: Path
    ) -> None:
        """The exact BUG-3278 shape: a bold_label group decided, a co-located
        bullet-tier group left unmarked — the residual bullet group must
        still surface as exit 1."""
        body = _issue_body(
            "FEAT-9104",
            (
                "**Option A**: Do X.\n"
                "> **Selected:** Option A\n\n"
                "**Option B**: Do Y.\n\n"
                "- **(a) approach one**\n"
                "- **(b) approach two**\n"
            ),
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-unresolved-decisions", "FEAT-9104")
        assert result.returncode == 1
        assert "UNRESOLVED_DECISIONS_REMAIN" in result.stderr

    def test_json_output_shape(self, temp_project_dir: Path) -> None:
        body = _issue_body(
            "FEAT-9105",
            "**Option A**: Do X.\n\n**Option B**: Do Y.\n",
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-unresolved-decisions", "FEAT-9105", "--json")
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert payload["id"] == "FEAT-9105"
        assert len(payload["unresolved"]) == 1
        group = payload["unresolved"][0]
        assert group["heading"] == "Proposed Solution"
        assert group["tier"] == "bold_label"
        assert len(group["options"]) == 2

    def test_json_output_clean_issue(self, temp_project_dir: Path) -> None:
        body = _issue_body(
            "FEAT-9106",
            "**Option A**: Do X.\n> **Selected:** Option A\n\n**Option B**: Do Y.\n",
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-unresolved-decisions", "FEAT-9106", "--json")
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["unresolved"] == []


class TestCheckUnresolvedDecisionsErrorHandling:
    """The probe distinguishes an unresolvable issue (exit 2) from a genuine
    residual (exit 1) — matches the check-open-questions/check-decidable
    house convention (BUG-3294)."""

    def test_missing_issue_exits_two(self, temp_project_dir: Path) -> None:
        result = _invoke(temp_project_dir, "check-unresolved-decisions", "FEAT-9999")
        assert result.returncode == 2
        assert "FEAT-9999" in result.stderr
        assert "not found" in result.stderr.lower() or "Error" in result.stderr


class TestCliRegistration:
    """The check-unresolved-decisions subcommand is registered in ll-issues __main__."""

    def test_subcommand_in_help(self, temp_project_dir: Path) -> None:
        result = _invoke(temp_project_dir, "--help")
        assert result.returncode == 0
        assert "check-unresolved-decisions" in result.stdout
