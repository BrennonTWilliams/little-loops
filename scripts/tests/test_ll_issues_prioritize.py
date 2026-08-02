"""Tests for ll-issues prioritize sub-command (ENH-2953)."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from little_loops.cli.issues.prioritize import apply_priorities, scan_prioritize
from little_loops.config import BRConfig

_PRIORITIZE_CONFIG: dict[str, Any] = {
    "project": {"name": "test-project"},
    "issues": {
        "base_dir": ".issues",
        "categories": {
            "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
            "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
            "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
            "epics": {"prefix": "EPIC", "dir": "epics", "action": "coordinate"},
        },
        "priorities": ["P0", "P1", "P2", "P3", "P4", "P5"],
    },
}


@pytest.fixture
def prioritize_dir(temp_project_dir: Path) -> Path:
    """Temp project with config and all four category directories."""
    config_path = temp_project_dir / ".ll" / "ll-config.json"
    config_path.write_text(json.dumps(_PRIORITIZE_CONFIG))
    issues_base = temp_project_dir / ".issues"
    for cat in ("bugs", "features", "enhancements", "epics"):
        (issues_base / cat).mkdir(parents=True, exist_ok=True)
    return issues_base


@pytest.fixture
def git_prioritize_dir(prioritize_dir: Path, temp_project_dir: Path) -> Path:
    """Same as prioritize_dir, but the project root is a real git repo."""
    subprocess.run(["git", "init", "-q"], cwd=temp_project_dir, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=temp_project_dir, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=temp_project_dir, check=True)
    return prioritize_dir


def _config(temp_project_dir: Path) -> BRConfig:
    return BRConfig(temp_project_dir)


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _issue_body(*, id_: str, status: str = "open", title: str = "Test issue") -> str:
    return f"""---
id: {id_}
status: {status}
---

# {title}
"""


def _invoke(argv: list[str], stdin: str | None = None) -> tuple[int, str]:
    from little_loops.cli import main_issues

    with patch.object(sys, "argv", argv):
        buf = io.StringIO()
        patches = [contextlib.redirect_stdout(buf)]
        if stdin is not None:
            patches.append(patch.object(sys, "stdin", io.StringIO(stdin)))
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            result = main_issues()
        return result, buf.getvalue()


def _git_commit(project_dir: Path, path: Path, message: str) -> None:
    subprocess.run(["git", "add", str(path)], cwd=project_dir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=project_dir, check=True)


# ---------------------------------------------------------------------------
# scan_prioritize
# ---------------------------------------------------------------------------


class TestScanPrioritize:
    def test_unprioritized_issue_detected(
        self, temp_project_dir: Path, prioritize_dir: Path
    ) -> None:
        _write(prioritize_dir / "bugs" / "BUG-001-fix-login.md", _issue_body(id_="BUG-001"))
        config = _config(temp_project_dir)

        findings = scan_prioritize(config)

        assert len(findings) == 1
        assert findings[0].id == "BUG-001"
        assert findings[0].current_priority is None

    def test_prioritized_issue_excluded_by_default(
        self, temp_project_dir: Path, prioritize_dir: Path
    ) -> None:
        _write(prioritize_dir / "bugs" / "P2-BUG-001-fix-login.md", _issue_body(id_="BUG-001"))
        config = _config(temp_project_dir)

        findings = scan_prioritize(config)

        assert findings == []

    def test_all_flag_lists_every_active_issue_with_priority(
        self, temp_project_dir: Path, prioritize_dir: Path
    ) -> None:
        _write(prioritize_dir / "bugs" / "P2-BUG-001-fix-login.md", _issue_body(id_="BUG-001"))
        _write(prioritize_dir / "bugs" / "unprioritized-bug.md", _issue_body(id_="BUG-002"))
        config = _config(temp_project_dir)

        findings = scan_prioritize(config, include_prioritized=True)

        by_id = {f.id: f.current_priority for f in findings}
        assert by_id == {"BUG-001": "P2", "BUG-002": None}

    def test_terminal_status_issues_excluded(
        self, temp_project_dir: Path, prioritize_dir: Path
    ) -> None:
        _write(prioritize_dir / "bugs" / "done-bug.md", _issue_body(id_="BUG-001", status="done"))
        _write(
            prioritize_dir / "bugs" / "cancelled-bug.md",
            _issue_body(id_="BUG-002", status="cancelled"),
        )
        _write(
            prioritize_dir / "bugs" / "deferred-bug.md",
            _issue_body(id_="BUG-003", status="deferred"),
        )
        config = _config(temp_project_dir)

        findings = scan_prioritize(config, include_prioritized=True)

        assert findings == []


# ---------------------------------------------------------------------------
# apply_priorities
# ---------------------------------------------------------------------------


class TestApplyPriorities:
    def test_prepend_on_unprioritized_file(
        self, temp_project_dir: Path, prioritize_dir: Path
    ) -> None:
        _write(prioritize_dir / "bugs" / "BUG-001-fix-login.md", _issue_body(id_="BUG-001"))
        config = _config(temp_project_dir)

        results = apply_priorities(config, {"BUG-001": "P2"})

        assert len(results) == 1
        assert results[0].old_priority is None
        assert results[0].new_path.name == "P2-BUG-001-fix-login.md"
        assert results[0].new_path.exists()
        assert not results[0].old_path.exists()

    def test_replace_on_already_prioritized_file(
        self, temp_project_dir: Path, prioritize_dir: Path
    ) -> None:
        _write(prioritize_dir / "bugs" / "P3-BUG-001-fix-login.md", _issue_body(id_="BUG-001"))
        config = _config(temp_project_dir)

        results = apply_priorities(config, {"BUG-001": "P1"})

        assert len(results) == 1
        assert results[0].old_priority == "P3"
        assert results[0].new_path.name == "P1-BUG-001-fix-login.md"
        assert results[0].new_path.exists()

    def test_already_at_target_priority_is_noop(
        self, temp_project_dir: Path, prioritize_dir: Path
    ) -> None:
        path = _write(
            prioritize_dir / "bugs" / "P2-BUG-001-fix-login.md", _issue_body(id_="BUG-001")
        )
        config = _config(temp_project_dir)

        results = apply_priorities(config, {"BUG-001": "P2"})

        assert len(results) == 1
        assert results[0].old_path.resolve() == results[0].new_path.resolve() == path.resolve()
        assert path.exists()

    def test_apply_is_idempotent(self, temp_project_dir: Path, prioritize_dir: Path) -> None:
        _write(prioritize_dir / "bugs" / "BUG-001-fix-login.md", _issue_body(id_="BUG-001"))
        config = _config(temp_project_dir)

        first = apply_priorities(config, {"BUG-001": "P2"})
        content_after_first = first[0].new_path.read_text()

        second = apply_priorities(config, {"BUG-001": "P2"})

        assert second[0].old_path == second[0].new_path == first[0].new_path
        assert second[0].new_path.read_text() == content_after_first

    def test_unresolvable_id_skipped(self, temp_project_dir: Path, prioritize_dir: Path) -> None:
        config = _config(temp_project_dir)

        results = apply_priorities(config, {"BUG-999": "P2"})

        assert results == []

    def test_git_history_preserved_across_rename(
        self, temp_project_dir: Path, git_prioritize_dir: Path
    ) -> None:
        path = _write(
            git_prioritize_dir / "bugs" / "BUG-001-fix-login.md", _issue_body(id_="BUG-001")
        )
        _git_commit(temp_project_dir, path, "add BUG-001-fix-login.md")
        config = _config(temp_project_dir)

        results = apply_priorities(config, {"BUG-001": "P2"})
        new_path = results[0].new_path
        _git_commit(temp_project_dir, git_prioritize_dir, "rename to P2-BUG-001-fix-login.md")

        log = subprocess.run(
            ["git", "log", "--format=%s", "--follow", "--", str(new_path)],
            cwd=temp_project_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        messages = log.stdout.strip().splitlines()
        assert "add BUG-001-fix-login.md" in messages

    def test_untracked_file_falls_back_without_raising(
        self, temp_project_dir: Path, git_prioritize_dir: Path
    ) -> None:
        # git_prioritize_dir is a git repo, but the file itself is never
        # `git add`-ed, so git mv must fall back to atomic_write + rename.
        _write(git_prioritize_dir / "bugs" / "BUG-001-fix-login.md", _issue_body(id_="BUG-001"))
        config = _config(temp_project_dir)

        results = apply_priorities(config, {"BUG-001": "P2"})

        assert len(results) == 1
        assert results[0].new_path.exists()


# ---------------------------------------------------------------------------
# CLI: --check
# ---------------------------------------------------------------------------


class TestCheckMode:
    def test_check_fails_when_unprioritized_issue_exists(
        self, temp_project_dir: Path, prioritize_dir: Path
    ) -> None:
        _write(prioritize_dir / "bugs" / "BUG-001-fix-login.md", _issue_body(id_="BUG-001"))

        result, out = _invoke(
            ["ll-issues", "prioritize", "--check", "--config", str(temp_project_dir)]
        )

        assert result == 1
        assert "unprioritized" in out

    def test_check_passes_when_all_prioritized(
        self, temp_project_dir: Path, prioritize_dir: Path
    ) -> None:
        _write(prioritize_dir / "bugs" / "P2-BUG-001-fix-login.md", _issue_body(id_="BUG-001"))

        result, out = _invoke(
            ["ll-issues", "prioritize", "--check", "--config", str(temp_project_dir)]
        )

        assert result == 0

    def test_check_ignores_all_flag(self, temp_project_dir: Path, prioritize_dir: Path) -> None:
        _write(prioritize_dir / "bugs" / "P2-BUG-001-fix-login.md", _issue_body(id_="BUG-001"))

        result, _ = _invoke(
            [
                "ll-issues",
                "prioritize",
                "--check",
                "--all",
                "--config",
                str(temp_project_dir),
            ]
        )

        assert result == 0


# ---------------------------------------------------------------------------
# CLI: --json / --apply -
# ---------------------------------------------------------------------------


class TestJsonOutput:
    def test_json_shape(self, temp_project_dir: Path, prioritize_dir: Path) -> None:
        _write(prioritize_dir / "bugs" / "BUG-001-fix-login.md", _issue_body(id_="BUG-001"))

        result, out = _invoke(
            ["ll-issues", "prioritize", "--json", "--config", str(temp_project_dir)]
        )

        assert result == 0
        data = json.loads(out)
        assert set(data) == {"findings", "applied"}
        assert data["applied"] == []
        assert len(data["findings"]) == 1
        assert data["findings"][0]["id"] == "BUG-001"

    def test_apply_via_stdin_json(self, temp_project_dir: Path, prioritize_dir: Path) -> None:
        _write(prioritize_dir / "bugs" / "BUG-001-fix-login.md", _issue_body(id_="BUG-001"))

        result, out = _invoke(
            [
                "ll-issues",
                "prioritize",
                "--json",
                "--apply",
                "-",
                "--config",
                str(temp_project_dir),
            ],
            stdin=json.dumps({"BUG-001": "P2"}),
        )

        assert result == 0
        data = json.loads(out)
        assert len(data["applied"]) == 1
        assert data["applied"][0]["id"] == "BUG-001"
        assert (prioritize_dir / "bugs" / "P2-BUG-001-fix-login.md").exists()

    def test_apply_invalid_json_reports_error_without_raising(
        self, temp_project_dir: Path, prioritize_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result, _ = _invoke(
            ["ll-issues", "prioritize", "--apply", "-", "--config", str(temp_project_dir)],
            stdin="not json",
        )

        assert result == 1
