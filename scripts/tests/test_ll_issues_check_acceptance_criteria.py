"""Subprocess-level tests for ll-issues check-acceptance-criteria (ENH-3031).

Mirrors test_ll_issues_check_open_questions.py's exact structure: subprocess
invocation with the CLI binary, exit-code contract (0 = all criteria
machine-checkable / 1 = MANUAL_CRITERIA_REMAIN), side-effect-free, deterministic.
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


def _feature(id: str, ac_body: str) -> str:
    return (
        f"---\n"
        f"id: {id}\n"
        f"title: Test feature {id}\n"
        f"type: feature\n"
        f"status: open\n"
        f"priority: P3\n"
        f"---\n\n"
        f"# {id}: Test feature\n\n"
        f"## Summary\n\nTest.\n\n"
        f"## Acceptance Criteria\n\n{ac_body}\n"
        f"---\n\n## Status\n**Open** | Created: 2026-07-08 | Priority: P3\n"
    )


class TestCheckAcceptanceCriteriaHappyPath:
    """All checkbox items are machine-checkable → exit 0."""

    def test_clean_issue_exits_zero(self, temp_project_dir: Path) -> None:
        body = _feature(
            "FEAT-9101",
            "- [ ] `pytest scripts/tests/` exits 0.\n- [ ] `ll-loop validate my-loop` passes.\n",
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-acceptance-criteria", "FEAT-9101")
        assert result.returncode == 0, (
            f"Clean issue must exit 0, got {result.returncode}: "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "FEAT-9101" in result.stdout

    def test_no_acceptance_criteria_section_exits_zero(self, temp_project_dir: Path) -> None:
        body = (
            "---\nid: FEAT-9102\ntitle: Test\ntype: feature\nstatus: open\npriority: P3\n"
            "---\n\n## Summary\n\nNo AC section.\n"
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-acceptance-criteria", "FEAT-9102")
        assert result.returncode == 0


class TestCheckAcceptanceCriteriaManual:
    """A manual-verification checkbox item exits 1 with the token."""

    def test_verify_by_temporarily_exits_one(self, temp_project_dir: Path) -> None:
        body = _feature(
            "FEAT-9103",
            "- [ ] The negative assertion fails — verify by temporarily removing "
            "the `isatty()` guard.\n",
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-acceptance-criteria", "FEAT-9103")
        assert result.returncode == 1, (
            f"Manual criterion must exit 1, got {result.returncode}: "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "MANUAL_CRITERIA_REMAIN" in result.stderr
        assert "FEAT-9103" in result.stderr

    def test_manually_verb_exits_one(self, temp_project_dir: Path) -> None:
        body = _feature("FEAT-9104", "- [ ] Confirm the output manually.\n")
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-acceptance-criteria", "FEAT-9104")
        assert result.returncode == 1

    def test_visually_confirm_exits_one(self, temp_project_dir: Path) -> None:
        body = _feature("FEAT-9105", "- [ ] Visually confirm the banner renders.\n")
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-acceptance-criteria", "FEAT-9105")
        assert result.returncode == 1


class TestCheckAcceptanceCriteriaScoping:
    """Only checkbox items are scanned — non-criterion prose under the heading is ignored."""

    def test_non_checkbox_prose_not_flagged(self, temp_project_dir: Path) -> None:
        """Regression: FEAT-1236/FEAT-1238 measured false positives from unscoped
        prose scanning ('Can be run manually on any issue...')."""
        body = _feature(
            "FEAT-9106",
            "- [ ] `pytest scripts/tests/` exits 0.\n"
            "\n"
            "Can be run manually on any issue even without the `decision_needed` flag.\n",
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-acceptance-criteria", "FEAT-9106")
        assert result.returncode == 0

    def test_bare_looks_token_not_flagged(self, temp_project_dir: Path) -> None:
        """The bare 'looks' token was dropped — only the full 'check that ... looks' phrase fires."""
        body = _feature("FEAT-9107", "- [ ] The output looks correct in the diff viewer.\n")
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-acceptance-criteria", "FEAT-9107")
        assert result.returncode == 0


class TestCheckAcceptanceCriteriaBug3025Fixtures:
    """Regression fixtures pinned to BUG-3025's git history (ENH-3031)."""

    def test_pre_review_fixture_has_manual_criterion(self) -> None:
        from little_loops.cli.issues.check_acceptance_criteria import _find_manual_criteria

        fixture = Path(__file__).parent / "fixtures" / "issues" / "BUG-3025-pre-review-original.md"
        assert _find_manual_criteria(fixture.read_text())

    def test_reviewed_fixture_has_no_manual_criterion(self) -> None:
        from little_loops.cli.issues.check_acceptance_criteria import _find_manual_criteria

        fixture = Path(__file__).parent / "fixtures" / "issues" / "BUG-3025-reviewed-uncorrected.md"
        assert not _find_manual_criteria(fixture.read_text())


class TestCheckAcceptanceCriteriaErrorHandling:
    """The probe distinguishes an unresolvable issue (exit 2) from a genuine
    negative verdict (exit 1) — BUG-3294."""

    def test_missing_issue_exits_two(self, temp_project_dir: Path) -> None:
        result = _invoke(temp_project_dir, "check-acceptance-criteria", "FEAT-9999")
        assert result.returncode == 2
        assert "FEAT-9999" in result.stderr
        assert "not found" in result.stderr.lower() or "Error" in result.stderr


class TestCliRegistration:
    """The check-acceptance-criteria subcommand is registered in ll-issues __main__."""

    def test_subcommand_in_help(self, temp_project_dir: Path) -> None:
        result = _invoke(temp_project_dir, "--help")
        assert result.returncode == 0
        assert "check-acceptance-criteria" in result.stdout
