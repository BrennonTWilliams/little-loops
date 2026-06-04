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

from little_loops.hooks.types import LLHookEvent
from little_loops.hooks.user_prompt_submit import handle


def _event(payload: dict | None = None, *, cwd: str | None = None) -> LLHookEvent:
    return LLHookEvent(
        host="claude-code",
        intent="user_prompt_submit",
        payload=payload or {},
        cwd=cwd,
    )


def _write_config(
    project_dir: Path, *, analytics_enabled: bool, analytics_capture: dict | None = None
) -> None:
    ll_dir = project_dir / ".ll"
    ll_dir.mkdir(parents=True, exist_ok=True)
    analytics: dict = {"enabled": analytics_enabled}
    if analytics_capture is not None:
        analytics["capture"] = analytics_capture
    (ll_dir / "ll-config.json").write_text(
        json.dumps({"analytics": analytics}),
        encoding="utf-8",
    )


class TestUserPromptSubmitWithSessionStore:
    """ENH-1831: correction-detection write path (gated on analytics.enabled)."""

    def test_correction_detected_writes_db(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, analytics_enabled=True)
        monkeypatch.chdir(tmp_path)

        result = handle(
            _event({"prompt": "no, don't do that", "session_id": "sess-c1"}, cwd=str(tmp_path))
        )
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

    def test_non_correction_writes_no_db_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, analytics_enabled=True)
        monkeypatch.chdir(tmp_path)

        handle(
            _event(
                {"prompt": "implement the login feature", "session_id": "sess-c2"},
                cwd=str(tmp_path),
            )
        )

        db_path = tmp_path / ".ll" / "history.db"
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            try:
                count = conn.execute("SELECT COUNT(*) FROM user_corrections").fetchone()[0]
            finally:
                conn.close()
            assert count == 0, "non-correction prompt must not write to user_corrections"

    def test_remember_prefix_writes_correction_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, analytics_enabled=True)
        monkeypatch.chdir(tmp_path)

        handle(
            _event(
                {"prompt": "!remember always use snake_case", "session_id": "sess-c3"},
                cwd=str(tmp_path),
            )
        )

        db_path = tmp_path / ".ll" / "history.db"
        assert db_path.is_file(), "!remember must create history.db"
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT content, session_id, source FROM user_corrections"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None, "!remember must write a user_corrections row"
        content, session_id, source = row
        assert "always use snake_case" in content
        assert session_id == "sess-c3"
        assert source == "user_prompt_submit"

    def test_skips_write_when_analytics_disabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, analytics_enabled=False)
        monkeypatch.chdir(tmp_path)

        handle(_event({"prompt": "no, stop that"}, cwd=str(tmp_path)))

        assert not (tmp_path / ".ll" / "history.db").exists(), (
            "analytics disabled — DB must not be created"
        )

    def test_graceful_when_store_unwritable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sqlite3 as _sqlite3

        from little_loops import session_store

        _write_config(tmp_path, analytics_enabled=True)
        monkeypatch.chdir(tmp_path)

        def boom(*_a, **_kw):
            raise _sqlite3.OperationalError("disk full")

        monkeypatch.setattr(session_store, "connect", boom)
        result = handle(_event({"prompt": "stop, revert that"}, cwd=str(tmp_path)))
        assert result.exit_code == 0

    def test_corrections_gate_disabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """analytics enabled but capture.corrections: false → no DB write."""
        import sqlite3 as _sqlite3

        _write_config(tmp_path, analytics_enabled=True, analytics_capture={"corrections": False})
        monkeypatch.chdir(tmp_path)

        handle(_event({"prompt": "no, don't do that", "session_id": "sess-g1"}, cwd=str(tmp_path)))

        db_path = tmp_path / ".ll" / "history.db"
        if db_path.exists():
            conn = _sqlite3.connect(str(db_path))
            try:
                count = conn.execute("SELECT COUNT(*) FROM user_corrections").fetchone()[0]
            finally:
                conn.close()
            assert count == 0, "record_correction must not write when capture.corrections is false"

    def test_corrections_gate_enabled_explicitly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """analytics enabled with capture.corrections: true → row written."""
        import sqlite3 as _sqlite3

        _write_config(tmp_path, analytics_enabled=True, analytics_capture={"corrections": True})
        monkeypatch.chdir(tmp_path)

        handle(_event({"prompt": "no, don't do that", "session_id": "sess-g2"}, cwd=str(tmp_path)))

        db_path = tmp_path / ".ll" / "history.db"
        assert db_path.is_file(), "DB must be created when capture.corrections is explicitly true"
        conn = _sqlite3.connect(str(db_path))
        try:
            row = conn.execute("SELECT content FROM user_corrections").fetchone()
        finally:
            conn.close()
        assert row is not None, (
            "record_correction must write when capture.corrections is explicitly true"
        )

    def test_custom_correction_pattern_writes_db(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(
            tmp_path,
            analytics_enabled=True,
            analytics_capture={"corrections": True, "correction_patterns": ["not quite"]},
        )
        monkeypatch.chdir(tmp_path)

        result = handle(
            _event(
                {"prompt": "not quite what I wanted", "session_id": "sess-cp1"},
                cwd=str(tmp_path),
            )
        )
        assert result.exit_code == 0

        db_path = tmp_path / ".ll" / "history.db"
        assert db_path.is_file(), "handler must create history.db on custom pattern match"
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("SELECT content FROM user_corrections").fetchone()
        finally:
            conn.close()
        assert row is not None, "custom correction_patterns phrase must write to user_corrections"
        assert "not quite" in row[0]


class TestUserPromptSubmitSkillWrite:
    """ENH-1833: skill invocation write path (gated on analytics.enabled)."""

    def test_skill_prompt_writes_skill_event(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A /ll: prompt with analytics enabled writes one skill_events row."""
        import sqlite3 as _sqlite3

        _write_config(tmp_path, analytics_enabled=True)
        monkeypatch.chdir(tmp_path)

        result = handle(
            _event(
                {"prompt": "/ll:refine-issue ENH-1833", "session_id": "sess-sk1"}, cwd=str(tmp_path)
            )
        )
        assert result.exit_code == 0

        db_path = tmp_path / ".ll" / "history.db"
        assert db_path.is_file(), "handler must create history.db on skill write"
        conn = _sqlite3.connect(str(db_path))
        try:
            row = conn.execute("SELECT skill_name, args, session_id FROM skill_events").fetchone()
        finally:
            conn.close()
        assert row is not None, "expected one skill_events row"
        skill_name, args, session_id = row
        assert skill_name == "refine-issue"
        assert "ENH-1833" in args
        assert session_id == "sess-sk1"

    def test_non_skill_prompt_writes_no_skill_event(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A regular prompt must not write to skill_events."""
        _write_config(tmp_path, analytics_enabled=True)
        monkeypatch.chdir(tmp_path)

        handle(
            _event(
                {"prompt": "implement the login feature", "session_id": "sess-sk2"},
                cwd=str(tmp_path),
            )
        )

        db_path = tmp_path / ".ll" / "history.db"
        if db_path.exists():
            import sqlite3 as _sqlite3

            conn = _sqlite3.connect(str(db_path))
            try:
                count = conn.execute("SELECT COUNT(*) FROM skill_events").fetchone()[0]
            finally:
                conn.close()
            assert count == 0

    def test_skill_write_skipped_when_analytics_disabled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """analytics disabled → no DB created for skill invocations."""
        _write_config(tmp_path, analytics_enabled=False)
        monkeypatch.chdir(tmp_path)

        handle(_event({"prompt": "/ll:capture-issue add auth"}, cwd=str(tmp_path)))

        assert not (tmp_path / ".ll" / "history.db").exists(), (
            "analytics disabled — DB must not be created for skill writes"
        )

    def test_skill_write_graceful_on_store_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A DB error during skill write must not raise; hook must return exit_code=0."""
        import sqlite3 as _sqlite3

        from little_loops import session_store

        _write_config(tmp_path, analytics_enabled=True)
        monkeypatch.chdir(tmp_path)

        def boom(*_a, **_kw):
            raise _sqlite3.OperationalError("disk full")

        monkeypatch.setattr(session_store, "connect", boom)
        result = handle(_event({"prompt": "/ll:ready-issue ENH-1833"}, cwd=str(tmp_path)))
        assert result.exit_code == 0
