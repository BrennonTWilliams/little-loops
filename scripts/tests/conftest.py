"""Pytest fixtures for little-loops tests."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest


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
