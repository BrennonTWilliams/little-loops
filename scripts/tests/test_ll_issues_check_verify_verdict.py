"""Subprocess-level tests for ll-issues check-verify-verdict (ENH-3031).

Mirrors test_ll_issues_check_open_questions.py's exact structure: subprocess
invocation with the CLI binary, exit-code contract (0 = VALID or absent /
1 = NON_VALID), side-effect-free, deterministic.
"""

from __future__ import annotations

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


def _feature(id: str, extra_frontmatter: str = "") -> str:
    return (
        f"---\n"
        f"id: {id}\n"
        f"title: Test feature {id}\n"
        f"type: feature\n"
        f"status: open\n"
        f"priority: P3\n"
        f"{extra_frontmatter}"
        f"---\n\n"
        f"# {id}: Test feature\n\n"
        f"## Summary\n\nTest.\n"
    )


class TestCheckVerifyVerdictValid:
    def test_valid_verdict_exits_zero(self, temp_project_dir: Path) -> None:
        body = _feature("FEAT-9201", "verify_verdict: VALID\n")
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-verify-verdict", "FEAT-9201")
        assert result.returncode == 0, (
            f"VALID verdict must exit 0, got {result.returncode}: "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )

    def test_absent_field_exits_zero_fail_open(self, temp_project_dir: Path) -> None:
        body = _feature("FEAT-9202")
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-verify-verdict", "FEAT-9202")
        assert result.returncode == 0, (
            f"Absent verify_verdict must fail-open (exit 0), got {result.returncode}: "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )


class TestCheckVerifyVerdictNonValid:
    def test_non_valid_verdict_exits_one(self, temp_project_dir: Path) -> None:
        body = _feature("FEAT-9203", "verify_verdict: NON_VALID\n")
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-verify-verdict", "FEAT-9203")
        assert result.returncode == 1, (
            f"NON_VALID verdict must exit 1, got {result.returncode}: "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "VERIFY_VERDICT_NON_VALID" in result.stderr
        assert "FEAT-9203" in result.stderr


class TestCheckVerifyVerdictErrorHandling:
    def test_missing_issue_exits_one(self, temp_project_dir: Path) -> None:
        result = _invoke(temp_project_dir, "check-verify-verdict", "FEAT-9999")
        assert result.returncode == 1
        assert "FEAT-9999" in result.stderr
        assert "not found" in result.stderr.lower() or "Error" in result.stderr


class TestCliRegistration:
    def test_subcommand_in_help(self, temp_project_dir: Path) -> None:
        result = _invoke(temp_project_dir, "--help")
        assert result.returncode == 0
        assert "check-verify-verdict" in result.stdout
