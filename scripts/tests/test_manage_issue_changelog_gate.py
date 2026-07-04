"""Tests for the manage-issue .issues/-only commit changelog gate (ENH-2467).

The gate lives in prose+bash inside skills/manage-issue/SKILL.md; the matching
exclusion lives in commands/manage-release.md. These tests pin the contract in
both files and exercise the gate's shell logic against a real git repo.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
SKILL_FILE = REPO_ROOT / "skills" / "manage-issue" / "SKILL.md"
RELEASE_CMD_FILE = REPO_ROOT / "commands" / "manage-release.md"

# The gate snippet exactly as documented in SKILL.md § 3 (Commit All Changes).
GATE_SNIPPET = """\
CHANGED=$(git diff --cached --name-only)
NON_ISSUES=$(printf '%s\\n' "$CHANGED" | grep -v '^\\.issues/' || true)
"""


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "--initial-branch", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    (path / "README.md").write_text("x\n")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "initial commit")
    return path


class TestSkillGateContract:
    """SKILL.md must document the .issues/-only demotion gate."""

    def test_skill_contains_staged_diff_check(self) -> None:
        text = SKILL_FILE.read_text()
        assert "git diff --cached --name-only" in text, (
            "manage-issue SKILL.md must gate the commit on the staged file set (ENH-2467)"
        )

    def test_skill_demotes_to_chore_issues_prefix(self) -> None:
        text = SKILL_FILE.read_text()
        assert "chore(issues):" in text, (
            "manage-issue SKILL.md must demote .issues/-only commits to chore(issues): (ENH-2467)"
        )

    def test_skill_gate_snippet_matches_documented_form(self) -> None:
        text = SKILL_FILE.read_text()
        for line in GATE_SNIPPET.strip().splitlines():
            assert line in text, f"SKILL.md gate snippet drifted; missing line: {line}"


class TestReleaseAggregatorExclusion:
    """manage-release.md must exclude chore(issues): commits from the changelog."""

    def test_release_command_excludes_chore_issues(self) -> None:
        text = RELEASE_CMD_FILE.read_text()
        assert "chore(issues):" in text, (
            "manage-release.md must document the chore(issues): changelog exclusion (ENH-2467)"
        )

    def test_release_command_has_name_only_defense(self) -> None:
        text = RELEASE_CMD_FILE.read_text()
        assert "git diff-tree --no-commit-id --name-only" in text, (
            "manage-release.md must document the .issues/-only path-based skip (ENH-2467)"
        )


class TestGateShellLogic:
    """The documented gate snippet correctly classifies staged file sets."""

    def _run_gate(self, repo: Path) -> str:
        """Run the gate snippet against the repo's staged set; return $NON_ISSUES."""
        script = GATE_SNIPPET + 'printf "%s" "$NON_ISSUES"\n'
        result = subprocess.run(
            ["bash", "-c", script], cwd=repo, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    def test_issues_only_staged_set_yields_empty_non_issues(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        issue = repo / ".issues" / "bugs" / "P2-BUG-001-test.md"
        issue.parent.mkdir(parents=True)
        issue.write_text("---\nstatus: done\n---\n")
        _git(repo, "add", ".issues/")

        assert self._run_gate(repo) == "", (
            ".issues/-only staged set must yield empty $NON_ISSUES (demote to chore(issues):)"
        )

    def test_mixed_staged_set_yields_non_issues_paths(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        issue = repo / ".issues" / "bugs" / "P2-BUG-001-test.md"
        issue.parent.mkdir(parents=True)
        issue.write_text("---\nstatus: done\n---\n")
        src = repo / "src" / "module.py"
        src.parent.mkdir(parents=True)
        src.write_text("x = 1\n")
        _git(repo, "add", ".")

        non_issues = self._run_gate(repo)
        assert "src/module.py" in non_issues, (
            "mixed staged set must keep the standard conventional-commit subject"
        )
        assert ".issues/" not in non_issues

    def test_source_only_staged_set_yields_non_issues_paths(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        src = repo / "src" / "module.py"
        src.parent.mkdir(parents=True)
        src.write_text("x = 1\n")
        _git(repo, "add", ".")

        assert self._run_gate(repo) == "src/module.py"
