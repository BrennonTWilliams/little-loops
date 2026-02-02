"""Pytest fixtures for little-loops tests."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

# =============================================================================
# Fixture File Helpers
# =============================================================================


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def issue_fixtures(fixtures_dir: Path) -> Path:
    """Path to issue fixture files."""
    return fixtures_dir / "issues"


@pytest.fixture
def fsm_fixtures(fixtures_dir: Path) -> Path:
    """Path to FSM fixture files."""
    return fixtures_dir / "fsm"


def load_fixture(fixtures_dir: Path, *path_parts: str) -> str:
    """Load fixture file content by path parts.

    Args:
        fixtures_dir: Base fixtures directory path.
        path_parts: Path components relative to fixtures_dir.

    Returns:
        Content of the fixture file as a string.
    """
    fixture_path = fixtures_dir.joinpath(*path_parts)
    return fixture_path.read_text()


# =============================================================================
# Project Directory Fixtures
# =============================================================================


@pytest.fixture
def temp_project_dir() -> Generator[Path, None, None]:
    """Create a temporary project directory with .claude folder."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        claude_dir = project_root / ".claude"
        claude_dir.mkdir()
        yield project_root


@pytest.fixture
def sample_config() -> dict[str, Any]:
    """Sample configuration dictionary."""
    return {
        "project": {
            "name": "test-project",
            "src_dir": "src/",
            "test_cmd": "pytest tests/",
            "lint_cmd": "ruff check .",
            "type_cmd": "mypy src/",
            "format_cmd": "ruff format .",
            "build_cmd": None,
        },
        "issues": {
            "base_dir": ".issues",
            "categories": {
                "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
            },
            "completed_dir": "completed",
            "priorities": ["P0", "P1", "P2", "P3"],
        },
        "automation": {
            "timeout_seconds": 1800,
            "state_file": ".test-state.json",
            "worktree_base": ".worktrees",
            "max_workers": 2,
            "stream_output": False,
        },
        "parallel": {
            "max_workers": 3,
            "p0_sequential": True,
            "worktree_base": ".worktrees",
            "state_file": ".parallel-state.json",
            "timeout_seconds": 1800,
            "max_merge_retries": 2,
            "stream_output": False,
            "command_prefix": "/ll:",
            "ready_command": "ready_issue {{issue_id}}",
            "manage_command": "manage_issue {{issue_type}} {{action}} {{issue_id}}",
        },
        "sprints": {
            "sprints_dir": ".sprints",
            "default_mode": "auto",
            "default_timeout": 3600,
            "default_max_workers": 4,
        },
    }


@pytest.fixture
def config_file(temp_project_dir: Path, sample_config: dict[str, Any]) -> Path:
    """Create a config file in the temp project."""
    config_path = temp_project_dir / ".claude" / "ll-config.json"
    config_path.write_text(json.dumps(sample_config, indent=2))
    return config_path


@pytest.fixture
def issues_dir(temp_project_dir: Path) -> Path:
    """Create issue directories with sample issues."""
    issues_base = temp_project_dir / ".issues"
    bugs_dir = issues_base / "bugs"
    features_dir = issues_base / "features"
    completed_dir = issues_base / "completed"

    bugs_dir.mkdir(parents=True)
    features_dir.mkdir(parents=True)
    completed_dir.mkdir(parents=True)

    # Create sample bug issues
    (bugs_dir / "P0-BUG-001-critical-crash.md").write_text(
        "# BUG-001: Critical crash on startup\n\n## Summary\nApp crashes on launch."
    )
    (bugs_dir / "P1-BUG-002-slow-query.md").write_text(
        "# BUG-002: Slow database query\n\n## Summary\nQuery takes too long."
    )
    (bugs_dir / "P2-BUG-003-ui-glitch.md").write_text(
        "# BUG-003: UI glitch in sidebar\n\n## Summary\nSidebar flickers."
    )

    # Create sample feature issues
    (features_dir / "P1-FEAT-001-dark-mode.md").write_text(
        "# FEAT-001: Add dark mode\n\n## Summary\nImplement dark theme."
    )
    (features_dir / "P2-FEAT-002-export-csv.md").write_text(
        "# FEAT-002: Export to CSV\n\n## Summary\nAdd CSV export functionality."
    )

    return issues_base


@pytest.fixture
def sample_ready_issue_output_ready() -> str:
    """Sample ready_issue output for a READY verdict."""
    return """
## VALIDATION RESULT

| Check | Status | Details |
|-------|--------|---------|
| File references | PASS | All referenced files exist |
| Code accuracy | PASS | Code snippets match current implementation |
| Dependencies | PASS | No blocking dependencies |

## VERDICT: **READY**

The issue is ready for implementation.
"""


@pytest.fixture
def sample_ready_issue_output_not_ready() -> str:
    """Sample ready_issue output for a NOT_READY verdict."""
    return """
## VALIDATION RESULT

| Check | Status | Details |
|-------|--------|---------|
| File references | FAIL | Referenced file does not exist: src/missing.py |
| Code accuracy | PASS | Code snippets match |
| Dependencies | WARN | May conflict with ongoing work |

## VERDICT: **NOT_READY**

The issue has validation failures that must be addressed.

## CONCERNS
- Referenced file src/missing.py does not exist
- Potential conflict with PR #42
"""


@pytest.fixture
def sample_ready_issue_output_close() -> str:
    """Sample ready_issue output for a CLOSE verdict."""
    return """
## VALIDATION RESULT

| Check | Status | Details |
|-------|--------|---------|
| File references | N/A | Issue describes already-fixed behavior |
| Code accuracy | N/A | Current code does not have this bug |

## VERDICT: **CLOSE**

## CLOSE_REASON: already_fixed
## CLOSE_STATUS: Closed - Already Fixed

The reported issue has already been resolved in a previous commit.
"""


# =============================================================================
# FSM Loop Test Fixtures
# =============================================================================


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory for loop tests."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    (project_dir / ".loops").mkdir()
    return project_dir


@pytest.fixture
def valid_loop_file(temp_project: Path) -> Path:
    """Create a valid loop YAML file for testing."""
    loop_file = temp_project / ".loops" / "valid-loop.yaml"
    loop_content = """
name: test-loop
initial: start
states:
  start:
    action: echo "hello"
    on_success: done
  done:
    terminal: true
"""
    loop_file.write_text(loop_content)
    return loop_file


@pytest.fixture
def invalid_loop_file(temp_project: Path) -> Path:
    """Create an invalid loop YAML file for testing."""
    loop_file = temp_project / ".loops" / "invalid-loop.yaml"
    loop_content = """
name: test-loop
initial: nonexistent
states:
  start:
    action: echo "hello"
    on_success: done
  done:
    terminal: true
"""
    loop_file.write_text(loop_content)
    return loop_file


@pytest.fixture
def loops_dir(tmp_path: Path) -> Path:
    """Create a .loops directory with test loop files."""
    loops_dir = tmp_path / ".loops"
    loops_dir.mkdir()
    (loops_dir / "loop1.yaml").write_text("name: loop1\ninitial: start\nstates:\n  start:\n    terminal: true")
    (loops_dir / "loop2.yaml").write_text("name: loop2\ninitial: start\nstates:\n  start:\n    terminal: true")
    return loops_dir


@pytest.fixture
def events_file(tmp_path: Path) -> Path:
    """Create an events JSONL file for history tests."""
    events_path = tmp_path / "events.jsonl"
    events = [
        '{"timestamp": "2025-01-01T00:00:00", "state": "start", "action": "echo test"}',
        '{"timestamp": "2025-01-01T00:01:00", "state": "done", "action": ""}',
    ]
    events_path.write_text("\n".join(events))
    return events_path


@pytest.fixture
def many_events_file(tmp_path: Path) -> Path:
    """Create an events JSONL file with 10 events for tail tests."""
    events_path = tmp_path / "events.jsonl"
    events = [f'{{"timestamp": "2025-01-01T00:0{i}:00", "state": "state{i}", "action": "action{i}"}}' for i in range(10)]
    events_path.write_text("\n".join(events))
    return events_path
