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


class TestPromptOptimizationRender:
    """BUG-2275: prompt optimization renders from in-package template, not module constant."""

    def _write_opt_config(self, project_dir: Path) -> None:
        ll_dir = project_dir / ".ll"
        ll_dir.mkdir(parents=True, exist_ok=True)
        config = {
            "prompt_optimization": {
                "enabled": True,
                "mode": "quick",
                "confirm": "false",
                "bypass_prefix": "*",
            }
        }
        (ll_dir / "ll-config.json").write_text(json.dumps(config), encoding="utf-8")

    def test_renders_from_package_without_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """In-package fallback: render fires even with CLAUDE_PLUGIN_ROOT unset."""
        self._write_opt_config(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)

        result = handle(_event({"prompt": "implement authentication flow"}))
        assert result.exit_code == 0
        assert result.stdout, "prompt optimization must render template, not return empty stdout"
        assert "{{USER_PROMPT}}" not in result.stdout, "template placeholders must be substituted"
        assert "implement authentication flow" in result.stdout

    def test_env_var_override_uses_custom_template(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CLAUDE_PLUGIN_ROOT env var overrides the in-package template path."""
        self._write_opt_config(tmp_path)

        plugin_root = tmp_path / "custom_plugin"
        prompts_dir = plugin_root / "hooks" / "prompts"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "optimize-prompt-hook.md").write_text(
            "CUSTOM: {{USER_PROMPT}}", encoding="utf-8"
        )

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))

        result = handle(_event({"prompt": "implement authentication flow"}))
        assert result.exit_code == 0
        assert result.stdout.startswith("CUSTOM: "), (
            "CLAUDE_PLUGIN_ROOT must redirect to custom template"
        )

    def test_silent_noop_when_prompt_too_short(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Prompts below _MIN_PROMPT_LENGTH bypass optimization silently."""
        self._write_opt_config(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)

        result = handle(_event({"prompt": "short"}))
        assert result.exit_code == 0
        assert not result.stdout

    def _write_empty_config(self, project_dir: Path) -> None:
        ll_dir = project_dir / ".ll"
        ll_dir.mkdir(parents=True, exist_ok=True)
        (ll_dir / "ll-config.json").write_text(json.dumps({}), encoding="utf-8")

    def test_absent_block_defaults_on(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BUG-2321: absent prompt_optimization block must default to enabled=True."""
        self._write_empty_config(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)

        result = handle(_event({"prompt": "implement authentication flow"}))
        assert result.exit_code == 0
        assert result.stdout, "absent block must be treated as enabled; template should render"
        assert "implement authentication flow" in result.stdout

    def test_explicit_disabled_suppresses_injection(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BUG-2321: explicit enabled=false must still suppress injection."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(parents=True, exist_ok=True)
        config = {"prompt_optimization": {"enabled": False}}
        (ll_dir / "ll-config.json").write_text(json.dumps(config), encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)

        result = handle(_event({"prompt": "implement authentication flow"}))
        assert result.exit_code == 0
        assert not result.stdout

    def test_bypass_guards_fire_before_enabled_check(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BUG-2321: bypass guards (slash, short) short-circuit even with absent block (default-on)."""
        self._write_empty_config(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)

        slash_result = handle(_event({"prompt": "/ll:manage-issue ENH-123"}))
        assert slash_result.exit_code == 0
        assert not slash_result.stdout

        short_result = handle(_event({"prompt": "short"}))
        assert short_result.exit_code == 0
        assert not short_result.stdout
