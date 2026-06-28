"""Pytest fixtures for little-loops tests."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pytest

# =============================================================================
# Snapshot Testing Helpers
# =============================================================================


@pytest.fixture
def stable_snapshot_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin determinism controls for snapshot tests.

    Disables ANSI color and fixes terminal width to 80 so golden files are
    stable across environments. Apply explicitly to snapshot test classes via
    ``@pytest.mark.usefixtures("stable_snapshot_env")`` rather than autouse
    to avoid interfering with tests that assert both color-on and color-off.
    """
    monkeypatch.setattr("little_loops.cli.output._USE_COLOR", False)
    monkeypatch.setattr("little_loops.cli.output.terminal_width", lambda **_kw: 80)
    try:
        monkeypatch.setattr("little_loops.cli.loop.layout._USE_COLOR", False)
    except AttributeError:
        pass


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
# Doc-Wiring Helpers
# =============================================================================


def doc_wiring_frontmatter(path: Path) -> str:
    """Extract YAML frontmatter block from a markdown file.

    Returns everything between the first ``---`` and the closing ``---``.
    Used by doc-wiring tests to assert on frontmatter fields without false
    positives from body text.

    Args:
        path: Path to a markdown file with YAML frontmatter.

    Returns:
        The frontmatter string including the ``---`` delimiters.
    """
    content = path.read_text()
    end = content.index("---", 3)
    return content[: end + 3]


def doc_wiring_section(content: str, heading: str) -> str:
    """Extract the content under a markdown heading up to the next same-level heading.

    Args:
        content: Full markdown document text.
        heading: The heading text to find (without leading ``## `` markers).

    Returns:
        The content from the heading line to the next heading of the same level,
        or to end of content if it's the last section.
    """
    # Determine heading level from the heading string
    prefix = "## "
    marker = prefix + heading
    start = content.index(marker)
    # Find next heading at the same level after start
    end = content.find("\n" + prefix, start + len(marker))
    if end == -1:
        return content[start:]
    return content[start:end]


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Repository root path (session-scoped, computed once)."""
    return Path(__file__).parent.parent.parent


# =============================================================================
# Project Directory Fixtures
# =============================================================================


@pytest.fixture
def temp_project_dir() -> Generator[Path, None, None]:
    """Create a temporary project directory with .ll folder."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        ll_dir = project_root / ".ll"
        ll_dir.mkdir(exist_ok=True)
        yield project_root


@pytest.fixture
def make_project(
    tmp_path: Path,
) -> Callable[[dict[str, Any] | None, list[str] | None], tuple[Path, Path]]:
    """Factory fixture for creating temporary project directories with custom configs.

    Each call creates a numbered subdirectory under pytest's ``tmp_path`` so the
    factory can be invoked multiple times in a single test without collisions.
    Cleanup is handled automatically by pytest's ``tmp_path`` teardown.

    Args:
        config: Full config dict written to ``.ll/ll-config.json``.  When
            omitted a minimal ``{"project": {"name": "test-project"}}`` is used.
        extra_dirs: Additional directories to create, given as paths relative to
            the project root (e.g. ``[".issues/completed", ".worktrees"]``).

    Returns:
        ``(project_root, issues_base)`` — project root and the resolved
        ``issues.base_dir`` directory (default ``.issues``).
    """
    _counter = [0]

    def _factory(
        config: dict[str, Any] | None = None,
        extra_dirs: list[str] | None = None,
    ) -> tuple[Path, Path]:
        _counter[0] += 1
        project = tmp_path / f"project_{_counter[0]}"
        project.mkdir()
        ll_dir = project / ".ll"
        ll_dir.mkdir()

        cfg: dict[str, Any] = config or {"project": {"name": "test-project"}}
        (ll_dir / "ll-config.json").write_text(json.dumps(cfg))

        base_dir = cfg.get("issues", {}).get("base_dir", ".issues")
        issues_base = project / base_dir
        categories: dict[str, Any] = cfg.get("issues", {}).get("categories", {})
        for cat_key, cat_val in categories.items():
            cat_dir_name = cat_val.get("dir", cat_key) if isinstance(cat_val, dict) else cat_key
            (issues_base / cat_dir_name).mkdir(parents=True, exist_ok=True)

        for d in extra_dirs or []:
            (project / d).mkdir(parents=True, exist_ok=True)

        return project, issues_base

    return _factory


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
            "run_cmd": None,
        },
        "issues": {
            "base_dir": ".issues",
            "categories": {
                "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
                "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
                "epics": {"prefix": "EPIC", "dir": "epics", "action": "implement"},
            },
            "completed_dir": "completed",
            "deferred_dir": "deferred",
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
            "ready_command": "ready-issue {{issue_id}}",
            "manage_command": "manage-issue {{issue_type}} {{action}} {{issue_id}}",
            "use_feature_branches": True,
        },
        "sprints": {
            "sprints_dir": ".sprints",
            "default_timeout": 3600,
            "default_max_workers": 4,
        },
        "orchestration": {},
    }


@pytest.fixture
def config_file(temp_project_dir: Path, sample_config: dict[str, Any]) -> Path:
    """Create a config file in the temp project."""
    config_path = temp_project_dir / ".ll" / "ll-config.json"
    config_path.write_text(json.dumps(sample_config, indent=2))
    return config_path


@pytest.fixture
def issues_dir(temp_project_dir: Path) -> Path:
    """Create issue type directories with sample issues.

    Post-ENH-1418: status lives in frontmatter, not in directory location, so
    no ``completed/`` or ``deferred/`` sibling dirs are created here.
    """
    issues_base = temp_project_dir / ".issues"
    bugs_dir = issues_base / "bugs"
    features_dir = issues_base / "features"
    epics_dir = issues_base / "epics"

    bugs_dir.mkdir(parents=True, exist_ok=True)
    features_dir.mkdir(parents=True, exist_ok=True)
    epics_dir.mkdir(parents=True, exist_ok=True)

    # Create sample bug issues
    (bugs_dir / "P0-BUG-001-critical-crash.md").write_text(
        "---\nstatus: open\n---\n# BUG-001: Critical crash on startup\n\n## Summary\nApp crashes on launch."
    )
    (bugs_dir / "P1-BUG-002-slow-query.md").write_text(
        "---\nstatus: open\n---\n# BUG-002: Slow database query\n\n## Summary\nQuery takes too long."
    )
    (bugs_dir / "P2-BUG-003-ui-glitch.md").write_text(
        "---\nstatus: open\n---\n# BUG-003: UI glitch in sidebar\n\n## Summary\nSidebar flickers."
    )

    # Create sample feature issues
    (features_dir / "P1-FEAT-001-dark-mode.md").write_text(
        "---\nstatus: open\n---\n# FEAT-001: Add dark mode\n\n## Summary\nImplement dark theme."
    )
    (features_dir / "P2-FEAT-002-export-csv.md").write_text(
        "---\nstatus: open\n---\n# FEAT-002: Export to CSV\n\n## Summary\nAdd CSV export functionality."
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
    project_dir.mkdir(exist_ok=True)
    (project_dir / ".loops").mkdir(exist_ok=True)
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
    on_yes: done
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
    on_yes: done
  done:
    terminal: true
"""
    loop_file.write_text(loop_content)
    return loop_file


@pytest.fixture
def loops_dir(tmp_path: Path) -> Path:
    """Create a .loops directory with test loop files."""
    loops_dir = tmp_path / ".loops"
    loops_dir.mkdir(exist_ok=True)
    (loops_dir / "loop1.yaml").write_text(
        "name: loop1\ninitial: start\nstates:\n  start:\n    terminal: true"
    )
    (loops_dir / "loop2.yaml").write_text(
        "name: loop2\ninitial: start\nstates:\n  start:\n    terminal: true"
    )
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
    events = [
        f'{{"timestamp": "2025-01-01T00:0{i}:00", "state": "state{i}", "action": "action{i}"}}'
        for i in range(10)
    ]
    events_path.write_text("\n".join(events))
    return events_path


# =============================================================================
# DB Isolation Fixtures (BUG-1995)
# =============================================================================


@pytest.fixture(scope="session", autouse=True)
def _isolate_history_db_session(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[None, None, None]:
    """Set LL_HISTORY_DB for the entire session so no module-level or session-scoped
    code accidentally opens the real .ll/history.db before function-scoped fixtures run.
    """
    session_db_dir = tmp_path_factory.mktemp("session_db") / ".ll"
    session_db_dir.mkdir(exist_ok=True)
    os.environ["LL_HISTORY_DB"] = str(session_db_dir / "history.db")
    yield
    os.environ.pop("LL_HISTORY_DB", None)


@pytest.fixture(autouse=True)
def _isolate_history_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[None, None, None]:
    """Redirect all session-store DB opens to a per-test temp directory.

    Sets LL_HISTORY_DB so cli_event_context and resolve_history_db route
    writes to tmp_path instead of the real .ll/history.db.
    """
    # Use a .ll/ subdirectory so ensure_db's legacy migration (session.db →
    # history.db) never sees a session.db sibling left by other fixtures.
    # Do NOT pre-create the directory here; tests that assert ".ll/" is absent
    # on entry would fail. ensure_db() creates the parent on first open.
    db = tmp_path / ".ll" / "history.db"
    monkeypatch.setenv("LL_HISTORY_DB", str(db))
    yield


@pytest.fixture(scope="session", autouse=True)
def _guard_real_history_db() -> Generator[None, None, None]:
    """Fail fast if any test opens the real .ll/history.db without isolation.

    Intercepts the single choke point every DB open routes through —
    ``little_loops.session_store.sqlite3.connect`` (used by ``ensure_db``,
    ``connect``, ``SessionStore._connect``, and vacuum) — and raises if a test
    targets the production database. Unlike the previous mtime/size snapshot,
    this is immune to concurrent external writers (live ``ll-auto`` / ``ll-loop``
    runs touch ``.ll/history.db`` continuously) and attributes a genuine leak to
    the actual offending test rather than the last test in the session.

    ``LL_HISTORY_DB`` is set per-test by ``_isolate_history_db``, so legitimate
    DB opens resolve to ``tmp_path/.ll/history.db`` and pass straight through.
    """
    import sqlite3

    from little_loops import session_store

    real_db = (Path(__file__).parent.parent.parent / ".ll" / "history.db").resolve()
    real_connect = sqlite3.connect

    def guarded_connect(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        try:
            resolved = Path(database).resolve()
        except TypeError:
            # Non-path targets (e.g. ":memory:") never alias the real DB.
            return real_connect(database, *args, **kwargs)
        assert resolved != real_db, (
            f"A test opened the production database without isolation: {resolved}. "
            f"Route the open through LL_HISTORY_DB / resolve_history_db() so it "
            f"lands in the per-test tmp_path instead of {real_db}."
        )
        return real_connect(database, *args, **kwargs)

    mp = pytest.MonkeyPatch()
    mp.setattr(session_store.sqlite3, "connect", guarded_connect)
    try:
        yield
    finally:
        mp.undo()


# =============================================================================
# cmd_run env-var isolation (BUG-2011 follow-up)
# =============================================================================

# Env vars that cmd_run() writes directly via os.environ (not monkeypatch).
# Without this fixture a test that calls cmd_run() with --handoff-threshold,
# --context-limit, or --worktree will leak the written value into subsequent
# tests.  The setenv("") + delenv() pattern registers a teardown for the var
# even when it was absent before the test, so cmd_run's direct write is
# always undone at test cleanup.
_CMD_RUN_ENV_VARS = (
    "LL_HANDOFF_THRESHOLD",
    "LL_CONTEXT_LIMIT",
    "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR",
)


@pytest.fixture(autouse=True)
def _restore_cmd_run_env_vars(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Restore env vars that cmd_run writes directly to os.environ."""
    for var in _CMD_RUN_ENV_VARS:
        monkeypatch.setenv(var, "")
        monkeypatch.delenv(var)
    yield
