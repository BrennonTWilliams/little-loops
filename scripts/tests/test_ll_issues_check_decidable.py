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


class TestCheckDecidableWidenedOptions:
    """Options deposited outside the originally-scanned sections are now reachable (ENH-2821)."""

    def test_options_under_open_questions_exit_zero(self, temp_project_dir: Path) -> None:
        """Regression fixture for BUG-2820/ENH-2821: options nested under an H3 inside
        ## Open Questions are now found by the whole-document fallback scan."""
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
        assert result.returncode == 0, (
            f"Options nested under any H2 must now be found, got {result.returncode}: "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "Decidable" in result.stdout
        assert "Open Questions" in result.stdout
        assert "FEAT-9102" in result.stdout

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


class TestCheckDecidablePatternEDirective:
    """Un-preferenced decision directive shape (ENH-2936): an imperative decide-marker
    co-occurring with 2+ named alternatives and no stated preference is decidable."""

    def test_scope_boundaries_directive_exit_zero(self, temp_project_dir: Path) -> None:
        body = (
            "---\n"
            "id: FEAT-9104\n"
            "title: Test\n"
            "type: feature\n"
            "status: open\n"
            "priority: P3\n"
            "decision_needed: true\n"
            "---\n\n"
            "# FEAT-9104\n\n"
            "## Summary\n\nTest.\n\n"
            "## Proposed Solution\n\nNo options here.\n\n"
            "## Scope Boundaries\n\n"
            "- stamp it or move it to Out of scope with a stated reason — do not "
            "leave it unaddressed\n\n"
            "## Labels\n\n`feature`\n\n"
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-decidable", "FEAT-9104")
        assert result.returncode == 0, (
            f"Un-preferenced decision directive must be decidable, got "
            f"{result.returncode}: stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "Scope Boundaries" in result.stdout

    def test_bare_or_prose_without_imperative_marker_exit_one(self, temp_project_dir: Path) -> None:
        """Guardrail: bare 'X or Y' prose with no imperative decide-marker must NOT
        be treated as decidable — that is the settled-informal-list case automation
        must not re-litigate."""
        body = (
            "---\n"
            "id: FEAT-9105\n"
            "title: Test\n"
            "type: feature\n"
            "status: open\n"
            "priority: P3\n"
            "decision_needed: true\n"
            "---\n\n"
            "# FEAT-9105\n\n"
            "## Summary\n\nTest.\n\n"
            "## Proposed Solution\n\nNo options here.\n\n"
            "## Scope Boundaries\n\n"
            "- stamp it or move it to Out of scope with a stated reason\n\n"
            "## Labels\n\n`feature`\n\n"
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-decidable", "FEAT-9105")
        assert result.returncode == 1
        assert "OPTIONS_MISSING" in result.stderr


class TestCheckDecidableDecisionRulesNumbered:
    """BUG-3293: bold-numbered decision items under Program Design -> Decision
    Rules are decidable; an ordinary bold-led numbered step list elsewhere is not."""

    def test_decision_rules_bold_numbered_exit_zero(self, temp_project_dir: Path) -> None:
        body = (
            "---\n"
            "id: FEAT-9106\n"
            "title: Test\n"
            "type: feature\n"
            "status: open\n"
            "priority: P3\n"
            "decision_needed: true\n"
            "---\n\n"
            "# FEAT-9106\n\n"
            "## Summary\n\nTest.\n\n"
            "## Proposed Solution\n\nNo options here.\n\n"
            "## Program Design\n\n"
            "### Decision Rules\n\n"
            "1. **Identifier shape.** The identifier is not `[A-Za-z0-9]+` alone.\n"
            "2. **Title extent.** Whether a title may span more than one line.\n\n"
            "## Labels\n\n`feature`\n\n"
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-decidable", "FEAT-9106")
        assert result.returncode == 0, (
            f"Bold-numbered Decision Rules items must be decidable, got "
            f"{result.returncode}: stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "Program Design" in result.stdout

    def test_implementation_steps_bold_numbered_list_exit_one(self, temp_project_dir: Path) -> None:
        """Guardrail: an ordinary bold-led numbered step list — this repo's dominant
        list convention — must NOT be treated as a decision block."""
        body = (
            "---\n"
            "id: FEAT-9107\n"
            "title: Test\n"
            "type: feature\n"
            "status: open\n"
            "priority: P3\n"
            "decision_needed: true\n"
            "---\n\n"
            "# FEAT-9107\n\n"
            "## Summary\n\nTest.\n\n"
            "## Proposed Solution\n\nNo options here.\n\n"
            "## Implementation Steps\n\n"
            "1. **Measure both routes before choosing.** Apply each candidate independently.\n"
            "2. **Land the corpus differential test first.** Before either change.\n\n"
            "## Labels\n\n`feature`\n\n"
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-decidable", "FEAT-9107")
        assert result.returncode == 1
        assert "OPTIONS_MISSING" in result.stderr


class TestCheckDecidableOptionsMissingDiagnosis:
    """BUG-3293 Part 3: the OPTIONS_MISSING message names both candidate causes
    (nothing written vs. an unrecognized shape) instead of asserting the
    document "genuinely has none"."""

    def test_options_missing_names_both_candidate_causes(self, temp_project_dir: Path) -> None:
        body = (
            "---\n"
            "id: FEAT-9108\n"
            "title: Test\n"
            "type: feature\n"
            "status: open\n"
            "priority: P3\n"
            "decision_needed: true\n"
            "---\n\n"
            "# FEAT-9108\n\n"
            "## Summary\n\nTest.\n\n"
            "## Proposed Solution\n\nNo enumerable options here.\n\n"
            "## Labels\n\n`feature`\n\n"
        )
        _write_issue(temp_project_dir, body)
        result = _invoke(temp_project_dir, "check-decidable", "FEAT-9108")
        assert result.returncode == 1
        assert "OPTIONS_MISSING" in result.stderr
        assert "none are written" in result.stderr
        assert "shape the locator does not recognize" in result.stderr
        assert "genuinely has none" not in result.stderr
        # remedy stays present but conditional on the "nothing written" cause
        assert "/ll:refine-issue" in result.stderr


class TestCheckDecidableErrorHandling:
    """The probe distinguishes an unresolvable issue (exit 2) from a genuine
    negative verdict (exit 1) — BUG-3294."""

    def test_missing_issue_exits_two(self, temp_project_dir: Path) -> None:
        result = _invoke(temp_project_dir, "check-decidable", "FEAT-9999")
        assert result.returncode == 2
        assert "FEAT-9999" in result.stderr
        assert "not found" in result.stderr.lower() or "Error" in result.stderr


class TestCliRegistration:
    """The check-decidable subcommand is registered in ll-issues __main__."""

    def test_subcommand_in_help(self, temp_project_dir: Path) -> None:
        result = _invoke(temp_project_dir, "--help")
        assert result.returncode == 0
        assert "check-decidable" in result.stdout
