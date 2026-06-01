"""Tests for little_loops.hooks.user_prompt_submit.handle (ENH-1831).

The handler detects user-correction signals and writes them to the
``user_corrections`` table (analytics-gated). Existing prompt-optimization
behavior is covered by adapter round-trip tests; this module focuses on the
correction-write path added by ENH-1831.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from little_loops.hooks.user_prompt_submit import handle
from little_loops.hooks.types import LLHookEvent


def _event(payload: dict | None = None, *, cwd: str | None = None) -> LLHookEvent:
    return LLHookEvent(
        host="claude-code",
        intent="user_prompt_submit",
        payload=payload or {},
        cwd=cwd,
    )


def _write_config(project_dir: Path, *, analytics_enabled: bool) -> None:
    ll_dir = project_dir / ".ll"
    ll_dir.mkdir(parents=True, exist_ok=True)
    (ll_dir / "ll-config.json").write_text(
        json.dumps({"analytics": {"enabled": analytics_enabled}}),
        encoding="utf-8",
    )


class TestUserPromptSubmitWithSessionStore:
    """ENH-1831: correction-detection write path (gated on analytics.enabled)."""

    def test_correction_detected_writes_db(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_config(tmp_path, analytics_enabled=True)
        monkeypatch.chdir(tmp_path)

        result = handle(_event({"prompt": "no, don't do that", "session_id": "sess-c1"}, cwd=str(tmp_path)))
        assert result.exit_code == 0

        db_path = tmp_path / ".ll" / "history.db"
        assert db_path.is_file(), "handler must create history.db on correction write"
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT content, session_id, source FROM user_corrections"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None, "expected one user_corrections row"
        content, session_id, source = row
        assert "don't do that" in content
        assert session_id == "sess-c1"
        assert source == "user_prompt_submit"

    def test_non_correction_writes_no_db_row(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_config(tmp_path, analytics_enabled=True)
        monkeypatch.chdir(tmp_path)

        handle(_event({"prompt": "implement the login feature", "session_id": "sess-c2"}, cwd=str(tmp_path)))

        db_path = tmp_path / ".ll" / "history.db"
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            try:
                count = conn.execute("SELECT COUNT(*) FROM user_corrections").fetchone()[0]
            finally:
                conn.close()
            assert count == 0, "non-correction prompt must not write to user_corrections"

    def test_skips_write_when_analytics_disabled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_config(tmp_path, analytics_enabled=False)
        monkeypatch.chdir(tmp_path)

        handle(_event({"prompt": "no, stop that"}, cwd=str(tmp_path)))

        assert not (tmp_path / ".ll" / "history.db").exists(), (
            "analytics disabled — DB must not be created"
        )

    def test_graceful_when_store_unwritable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import sqlite3 as _sqlite3
        from little_loops import session_store

        _write_config(tmp_path, analytics_enabled=True)
        monkeypatch.chdir(tmp_path)

        def boom(*_a, **_kw):
            raise _sqlite3.OperationalError("disk full")

        monkeypatch.setattr(session_store, "connect", boom)
        result = handle(_event({"prompt": "stop, revert that"}, cwd=str(tmp_path)))
        assert result.exit_code == 0
