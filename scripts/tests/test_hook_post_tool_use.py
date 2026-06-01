"""Python-direct tests for ``little_loops.hooks.post_tool_use.handle`` (FEAT-1623).

The handler persists per-tool byte metrics (``bytes_in`` / ``bytes_out`` /
``cache_hit``) to the ``tool_events`` table in ``.ll/history.db`` (FEAT-1112)
on every tool call, gated by the ``analytics.enabled`` config flag. Without a
config or with the flag off, the handler is a no-op (no SQLite write, exit 0).
Adapter round-trip tests live in ``test_codex_adapter.py``; this module
exercises the pure-function handler under unit conditions.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from little_loops.hooks.post_tool_use import handle as post_handle
from little_loops.hooks.pre_tool_use import handle as pre_handle
from little_loops.hooks.types import LLHookEvent

# Alias kept for the existing test class below.
handle = post_handle


def _event(payload: dict | None = None, *, cwd: str | None = None) -> LLHookEvent:
    return LLHookEvent(
        host="codex",
        intent="post_tool_use",
        payload=payload or {},
        cwd=cwd,
    )


class TestPostToolUseBaseline:
    def test_empty_payload_returns_pass(self, tmp_path, monkeypatch) -> None:
        # No config in tmp_path → handler skips the SQLite write and exits 0.
        monkeypatch.chdir(tmp_path)
        result = handle(_event(cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None
        assert result.decision is None

    def test_arbitrary_payload_returns_pass(self, tmp_path, monkeypatch) -> None:
        # The handler must tolerate any payload shape — Codex's PostToolUse and
        # OpenCode's tool.execute.after both pass tool-specific structures. With
        # no analytics config, the handler still returns exit 0 with no side
        # effect.
        monkeypatch.chdir(tmp_path)
        result = handle(
            _event(
                {
                    "tool_name": "Write",
                    "tool_input": {"file_path": "/tmp/foo", "content": "bar"},
                    "tool_response": {"success": True},
                    "session_id": "sess-1",
                },
                cwd=str(tmp_path),
            )
        )
        assert result.exit_code == 0
        assert result.feedback is None

    def test_handler_does_not_mutate_payload(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        payload = {"tool_name": "Bash"}
        handle(_event(payload, cwd=str(tmp_path)))
        assert payload == {"tool_name": "Bash"}

    def test_handler_is_host_agnostic(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        for host in ("claude-code", "codex", "opencode"):
            result = handle(
                LLHookEvent(
                    host=host,
                    intent="post_tool_use",
                    payload={},
                    cwd=str(tmp_path),
                )
            )
            assert result.exit_code == 0, f"non-zero exit for host={host}"


def _write_config(
    project_dir: Path, *, analytics_enabled: bool, analytics_capture: dict | None = None
) -> None:
    """Write a minimal ``.ll/ll-config.json`` toggling ``analytics.enabled``."""
    ll_dir = project_dir / ".ll"
    ll_dir.mkdir(parents=True, exist_ok=True)
    analytics: dict = {"enabled": analytics_enabled}
    if analytics_capture is not None:
        analytics["capture"] = analytics_capture
    (ll_dir / "ll-config.json").write_text(
        json.dumps({"analytics": analytics}),
        encoding="utf-8",
    )


class TestPostToolUseWithSessionStore:
    """FEAT-1623 byte-tracking write path (gated on ``analytics.enabled``)."""

    def test_writes_row_when_analytics_enabled(self, tmp_path, monkeypatch) -> None:
        _write_config(tmp_path, analytics_enabled=True)
        monkeypatch.chdir(tmp_path)
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "tool_response": {"exit_code": 0, "stdout": "total 0"},
            "session_id": "sess-7",
        }

        result = handle(_event(payload, cwd=str(tmp_path)))
        assert result.exit_code == 0

        db_path = tmp_path / ".ll" / "history.db"
        assert db_path.is_file(), "handler must create history.db on first write"
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT tool_name, session_id, bytes_in, bytes_out, cache_hit FROM tool_events"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None, "expected one tool_events row"
        tool_name, session_id, bytes_in, bytes_out, cache_hit = row
        assert tool_name == "Bash"
        assert session_id == "sess-7"
        # Encoded JSON byte counts (not zero, matches len(json.dumps(...))).
        assert bytes_in == len(json.dumps(payload["tool_input"]))
        assert bytes_out == len(json.dumps(payload["tool_response"]))
        assert cache_hit == 0

    def test_skips_write_when_analytics_disabled(self, tmp_path, monkeypatch) -> None:
        _write_config(tmp_path, analytics_enabled=False)
        monkeypatch.chdir(tmp_path)

        result = handle(
            _event(
                {
                    "tool_name": "Read",
                    "tool_input": {"path": "/etc/hostname"},
                    "tool_response": {"content": "hi"},
                },
                cwd=str(tmp_path),
            )
        )
        assert result.exit_code == 0
        # Handler must not have created the database when analytics is off.
        assert not (tmp_path / ".ll" / "history.db").exists()

    def test_skips_write_when_config_missing(self, tmp_path, monkeypatch) -> None:
        # No .ll/ll-config.json at all — handler must no-op.
        monkeypatch.chdir(tmp_path)

        result = handle(
            _event(
                {"tool_name": "Edit", "tool_input": {}, "tool_response": {}},
                cwd=str(tmp_path),
            )
        )
        assert result.exit_code == 0
        assert not (tmp_path / ".ll" / "history.db").exists()

    def test_cache_hit_field_extracted(self, tmp_path, monkeypatch) -> None:
        _write_config(tmp_path, analytics_enabled=True)
        monkeypatch.chdir(tmp_path)
        payload = {
            "tool_name": "Read",
            "tool_input": {"path": "/x"},
            "tool_response": {"content": "y"},
            "cache_hit": True,
        }
        handle(_event(payload, cwd=str(tmp_path)))

        db_path = tmp_path / ".ll" / "history.db"
        conn = sqlite3.connect(str(db_path))
        try:
            (cache_hit,) = conn.execute("SELECT cache_hit FROM tool_events").fetchone()
        finally:
            conn.close()
        assert cache_hit == 1

    def test_graceful_when_store_unwritable(self, tmp_path, monkeypatch) -> None:
        """Handler must not raise when SQLite write fails."""
        _write_config(tmp_path, analytics_enabled=True)
        monkeypatch.chdir(tmp_path)

        # Force ``connect`` to raise OperationalError to simulate a locked /
        # broken store; the handler's contextlib.suppress(Exception) must
        # swallow it and return exit_code=0.
        def boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
            raise sqlite3.OperationalError("database is locked")

        import little_loops.session_store as session_store

        monkeypatch.setattr(session_store, "connect", boom)

        result = handle(
            _event(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "ls"},
                    "tool_response": {"exit_code": 0},
                },
                cwd=str(tmp_path),
            )
        )
        assert result.exit_code == 0

    @pytest.mark.parametrize(
        "payload",
        [
            # Missing tool_input / tool_response fall back to empty dicts;
            # json.dumps({}) length is 2 ("{}").
            {"tool_name": "Bash"},
            {"tool_name": "Edit", "tool_input": None, "tool_response": None},
        ],
    )
    def test_byte_field_extraction_defaults(self, tmp_path, monkeypatch, payload) -> None:
        _write_config(tmp_path, analytics_enabled=True)
        monkeypatch.chdir(tmp_path)

        result = handle(_event(payload, cwd=str(tmp_path)))
        assert result.exit_code == 0

        db_path = tmp_path / ".ll" / "history.db"
        conn = sqlite3.connect(str(db_path))
        try:
            bytes_in, bytes_out = conn.execute(
                "SELECT bytes_in, bytes_out FROM tool_events"
            ).fetchone()
        finally:
            conn.close()
        # Both default to len(json.dumps({})) == 2.
        assert bytes_in == 2
        assert bytes_out == 2


class TestFileEventsWrite:
    """ENH-1832: file_events write path via post_tool_use hook."""

    @pytest.mark.parametrize(
        "payload, expected_path",
        [
            (
                {"tool_name": "Read", "tool_input": {"file_path": "scripts/foo.py"}, "session_id": "s1"},
                "scripts/foo.py",
            ),
            (
                {"tool_name": "Write", "tool_input": {"file_path": "out/bar.txt"}, "session_id": "s1"},
                "out/bar.txt",
            ),
            (
                {"tool_name": "Edit", "tool_input": {"file_path": "src/main.py"}, "session_id": "s1"},
                "src/main.py",
            ),
            (
                {"tool_name": "Glob", "tool_input": {"pattern": "**/*.py"}, "session_id": "s1"},
                "**/*.py",
            ),
            (
                {"tool_name": "Glob", "tool_input": {"path": "scripts/"}, "session_id": "s1"},
                "scripts/",
            ),
            (
                {"tool_name": "Grep", "tool_input": {"path": "scripts/"}, "session_id": "s1"},
                "scripts/",
            ),
            (
                {"tool_name": "Bash", "tool_input": {"command": "cat scripts/foo.py"}, "session_id": "s1"},
                "scripts/foo.py",
            ),
        ],
    )
    def test_per_tool_path_extraction(self, tmp_path, monkeypatch, payload, expected_path) -> None:
        _write_config(tmp_path, analytics_enabled=True)
        monkeypatch.chdir(tmp_path)

        handle(_event(payload, cwd=str(tmp_path)))

        db_path = tmp_path / ".ll" / "history.db"
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("SELECT path, op FROM file_events").fetchone()
        finally:
            conn.close()
        assert row is not None, f"expected file_events row for tool_name={payload['tool_name']!r}"
        assert row[0] == expected_path
        assert row[1] == payload["tool_name"]

    def test_bash_without_file_path_writes_no_file_event(self, tmp_path, monkeypatch) -> None:
        _write_config(tmp_path, analytics_enabled=True)
        monkeypatch.chdir(tmp_path)

        handle(_event({"tool_name": "Bash", "tool_input": {"command": "ls -la"}, "session_id": "s1"}, cwd=str(tmp_path)))

        db_path = tmp_path / ".ll" / "history.db"
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute("SELECT path FROM file_events").fetchall()
        finally:
            conn.close()
        assert rows == [], "ls -la has no detectable file path — expected zero file_events rows"

    def test_issue_id_extracted_from_issues_path(self, tmp_path, monkeypatch) -> None:
        _write_config(tmp_path, analytics_enabled=True)
        monkeypatch.chdir(tmp_path)
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": ".issues/enhancements/P4-ENH-1832-foo.md"},
            "session_id": "s1",
        }

        handle(_event(payload, cwd=str(tmp_path)))

        db_path = tmp_path / ".ll" / "history.db"
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("SELECT issue_id FROM file_events").fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] == "ENH-1832"

    def test_issue_id_null_for_plain_path(self, tmp_path, monkeypatch) -> None:
        _write_config(tmp_path, analytics_enabled=True)
        monkeypatch.chdir(tmp_path)
        payload = {
            "tool_name": "Read",
            "tool_input": {"file_path": "scripts/little_loops/hooks/post_tool_use.py"},
            "session_id": "s1",
        }

        handle(_event(payload, cwd=str(tmp_path)))

        db_path = tmp_path / ".ll" / "history.db"
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("SELECT issue_id FROM file_events").fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] is None

    def test_fts5_search_index_updated(self, tmp_path, monkeypatch) -> None:
        _write_config(tmp_path, analytics_enabled=True)
        monkeypatch.chdir(tmp_path)
        payload = {
            "tool_name": "Read",
            "tool_input": {"file_path": "scripts/little_loops/session_store.py"},
            "session_id": "s1",
        }

        handle(_event(payload, cwd=str(tmp_path)))

        db_path = tmp_path / ".ll" / "history.db"
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT kind FROM search_index WHERE content LIKE ?",
                ("%session_store%",),
            ).fetchone()
        finally:
            conn.close()
        assert row is not None, "expected a search_index row for the file path"
        assert row[0] == "file"

    def test_no_file_event_when_analytics_disabled(self, tmp_path, monkeypatch) -> None:
        _write_config(tmp_path, analytics_enabled=False)
        monkeypatch.chdir(tmp_path)
        payload = {
            "tool_name": "Read",
            "tool_input": {"file_path": "scripts/foo.py"},
            "session_id": "s1",
        }

        result = handle(_event(payload, cwd=str(tmp_path)))

        assert result.exit_code == 0
        assert not (tmp_path / ".ll" / "history.db").exists()

    def test_file_events_gate_disabled(self, tmp_path, monkeypatch) -> None:
        """analytics enabled at top level but capture.file_events: false → write_file_event NOT called."""
        _write_config(tmp_path, analytics_enabled=True, analytics_capture={"file_events": False})
        monkeypatch.chdir(tmp_path)

        import little_loops.session_store as session_store

        write_calls: list = []
        monkeypatch.setattr(session_store, "write_file_event", lambda *a, **kw: write_calls.append(a))

        handle(
            _event(
                {"tool_name": "Read", "tool_input": {"file_path": "scripts/foo.py"}, "session_id": "s1"},
                cwd=str(tmp_path),
            )
        )

        assert len(write_calls) == 0, "write_file_event must not be called when capture.file_events is false"

    def test_file_events_gate_enabled_explicitly(self, tmp_path, monkeypatch) -> None:
        """analytics enabled with capture.file_events: true → write_file_event IS called."""
        _write_config(tmp_path, analytics_enabled=True, analytics_capture={"file_events": True})
        monkeypatch.chdir(tmp_path)

        handle(
            _event(
                {"tool_name": "Read", "tool_input": {"file_path": "scripts/foo.py"}, "session_id": "s1"},
                cwd=str(tmp_path),
            )
        )

        db_path = tmp_path / ".ll" / "history.db"
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("SELECT path FROM file_events").fetchone()
        finally:
            conn.close()
        assert row is not None, "write_file_event must be called when capture.file_events is explicitly true"
        assert row[0] == "scripts/foo.py"


class TestPreToolUseBaseline:
    """Pre-tool-use handler is registered for opt-in dispatch (FEAT-1489)."""

    def test_empty_payload_returns_pass(self) -> None:
        result = pre_handle(LLHookEvent(host="codex", intent="pre_tool_use", payload={}))
        assert result.exit_code == 0
        assert result.feedback is None
        assert result.stdout is None

    def test_arbitrary_payload_returns_pass(self) -> None:
        result = pre_handle(
            LLHookEvent(
                host="opencode",
                intent="pre_tool_use",
                payload={"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}},
            )
        )
        assert result.exit_code == 0


class TestIssueAutoCommitPostToolUse:
    """ENH-1844: auto-commit via Python post_tool_use handler."""

    def _write_issues_config(
        self, project_dir: Path, *, auto_commit: bool, prefix: str = "chore(issues)"
    ) -> None:
        ll_dir = project_dir / ".ll"
        ll_dir.mkdir(parents=True, exist_ok=True)
        (ll_dir / "ll-config.json").write_text(
            json.dumps({"issues": {"auto_commit": auto_commit, "auto_commit_prefix": prefix}}),
            encoding="utf-8",
        )

    def test_gate_off_no_subprocess_calls(self, tmp_path: Path, monkeypatch) -> None:
        """auto_commit: false → no subprocess.run calls for git in the handler."""
        import subprocess as sp

        self._write_issues_config(tmp_path, auto_commit=False)
        monkeypatch.chdir(tmp_path)

        git_calls: list[list[str]] = []

        original_run = sp.run

        def mock_run(args, **kwargs):
            if isinstance(args, (list, tuple)) and args and "git" in str(args[0]):
                git_calls.append(list(args))
            return original_run(["true"], capture_output=True)

        monkeypatch.setattr("little_loops.hooks.post_tool_use.subprocess.run", mock_run)

        issue_path = str(tmp_path / ".issues" / "enhancements" / "P3-ENH-1844-test.md")
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": issue_path, "content": "---\nstatus: open\n---\n"},
            "session_id": "test-sess",
        }
        result = handle(_event(payload, cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert git_calls == [], f"Expected no git calls when auto_commit=false, got: {git_calls}"

    def test_gate_off_no_config_no_calls(self, tmp_path: Path, monkeypatch) -> None:
        """Missing config (default) → no subprocess.run calls for git."""
        import subprocess as sp

        monkeypatch.chdir(tmp_path)

        git_calls: list[list[str]] = []
        original_run = sp.run

        def mock_run(args, **kwargs):
            if isinstance(args, (list, tuple)) and args and "git" in str(args[0]):
                git_calls.append(list(args))
            return original_run(["true"], capture_output=True)

        monkeypatch.setattr("little_loops.hooks.post_tool_use.subprocess.run", mock_run)

        issue_path = str(tmp_path / ".issues" / "enhancements" / "P3-ENH-1844-test.md")
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": issue_path, "content": "---\nstatus: open\n---\n"},
            "session_id": "test-sess",
        }
        result = handle(_event(payload, cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert git_calls == [], f"Expected no git calls with no config, got: {git_calls}"
