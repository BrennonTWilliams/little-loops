"""Python-direct tests for ``little_loops.hooks.session_start.handle`` (FEAT-1450).

Adapter round-trip tests live in ``test_hooks_integration.py::TestSessionStartValidation``;
this module exercises the pure-function handler under unit conditions.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest

from little_loops.hooks.session_start import handle
from little_loops.hooks.types import LLHookEvent


@pytest.fixture
def in_tmp(tmp_path: Path):
    """chdir into ``tmp_path`` for the duration of one test, then restore cwd."""
    original = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(original)


def _event() -> LLHookEvent:
    return LLHookEvent(host="claude-code", intent="session_start", payload={})


class TestSessionStartConfigLoad:
    def test_no_config_emits_warning(self, in_tmp: Path) -> None:
        result = handle(_event())
        assert result.exit_code == 0
        assert result.stdout is None
        assert result.feedback is not None
        assert "No config found" in result.feedback

    def test_loads_base_config_when_present(self, in_tmp: Path) -> None:
        (in_tmp / ".ll").mkdir()
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({"a": 1}))

        result = handle(_event())

        assert result.exit_code == 0
        assert result.feedback is not None
        assert "Config loaded:" in result.feedback
        assert result.stdout is not None
        # Stdout should preserve on-disk text when no local overrides.
        assert json.loads(result.stdout) == {"a": 1}

    def test_falls_back_to_root_level_config(self, in_tmp: Path) -> None:
        (in_tmp / "ll-config.json").write_text(json.dumps({"x": 2}))

        result = handle(_event())

        assert result.exit_code == 0
        assert result.stdout is not None
        assert json.loads(result.stdout) == {"x": 2}

    def test_falls_back_to_codex_dir_config(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When LL_HOOK_HOST=codex, ``.codex/ll-config.json`` is probed first (FEAT-957)."""
        monkeypatch.setenv("LL_HOOK_HOST", "codex")
        (in_tmp / ".codex").mkdir()
        (in_tmp / ".codex" / "ll-config.json").write_text(json.dumps({"codex": True}))
        # Also write `.ll/ll-config.json` to confirm `.codex/` wins.
        (in_tmp / ".ll").mkdir()
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({"ll": True}))

        result = handle(LLHookEvent(host="codex", intent="session_start", payload={}))

        assert result.exit_code == 0
        assert result.stdout is not None
        assert json.loads(result.stdout) == {"codex": True}


class TestSessionStartContextStateCleanup:
    def test_removes_prior_session_state(self, in_tmp: Path) -> None:
        (in_tmp / ".ll").mkdir()
        state_file = in_tmp / ".ll" / "ll-context-state.json"
        state_file.write_text("{}")

        handle(_event())

        assert not state_file.exists()

    def test_no_state_file_is_noop(self, in_tmp: Path) -> None:
        # Should not raise when the file isn't there.
        result = handle(_event())
        assert result.exit_code == 0


class TestSessionStartDbMigration:
    """ENH-1635: session_start triggers the session.db -> history.db rename."""

    def test_migrates_legacy_session_db(self, in_tmp: Path) -> None:
        (in_tmp / ".ll").mkdir()
        # Need a config so the ensure_db() block runs.
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({}))
        legacy = in_tmp / ".ll" / "session.db"
        legacy.write_bytes(b"legacy-db")

        handle(_event())

        assert (in_tmp / ".ll" / "history.db").exists()
        assert not legacy.exists()


class TestSessionStartLocalOverrides:
    def _write_base(self, root: Path, config: dict) -> None:
        (root / ".ll").mkdir(exist_ok=True)
        (root / ".ll" / "ll-config.json").write_text(json.dumps(config))

    def _write_local(self, root: Path, frontmatter: str) -> None:
        (root / ".ll").mkdir(exist_ok=True)
        (root / ".ll" / "ll.local.md").write_text(f"---\n{frontmatter}\n---\n\n# notes\n")

    def test_local_overrides_deep_merge(self, in_tmp: Path) -> None:
        self._write_base(in_tmp, {"a": {"b": 1, "c": 2}, "x": [1, 2, 3]})
        self._write_local(in_tmp, "a:\n  b: 99\n")

        result = handle(_event())

        assert result.feedback is not None
        assert "Local overrides applied from:" in result.feedback
        assert result.stdout is not None
        merged = json.loads(result.stdout)
        assert merged == {"a": {"b": 99, "c": 2}, "x": [1, 2, 3]}

    def test_local_null_removes_key(self, in_tmp: Path) -> None:
        self._write_base(in_tmp, {"a": 1, "b": 2})
        self._write_local(in_tmp, "a: null\n")

        result = handle(_event())

        assert result.stdout is not None
        assert json.loads(result.stdout) == {"b": 2}

    def test_local_array_replaces(self, in_tmp: Path) -> None:
        self._write_base(in_tmp, {"items": [1, 2, 3]})
        self._write_local(in_tmp, "items:\n  - 9\n")

        result = handle(_event())

        assert result.stdout is not None
        assert json.loads(result.stdout) == {"items": [9]}

    def test_empty_frontmatter_does_not_emit_overrides_line(self, in_tmp: Path) -> None:
        self._write_base(in_tmp, {"a": 1})
        (in_tmp / ".ll" / "ll.local.md").write_text("# no frontmatter\n")

        result = handle(_event())

        assert result.feedback is not None
        assert "Local overrides applied" not in result.feedback


class TestSessionStartFeatureValidation:
    def _run_with(self, root: Path, cfg: dict) -> str:
        (root / ".ll").mkdir(exist_ok=True)
        (root / ".ll" / "ll-config.json").write_text(json.dumps(cfg))
        result = handle(_event())
        return result.feedback or ""

    def test_warns_sync_enabled_without_github(self, in_tmp: Path) -> None:
        fb = self._run_with(in_tmp, {"sync": {"enabled": True}})
        assert "sync.enabled is true but sync.github is not configured" in fb

    def test_no_warning_when_sync_properly_configured(self, in_tmp: Path) -> None:
        fb = self._run_with(
            in_tmp, {"sync": {"enabled": True, "github": {"label_mapping": {"BUG": "bug"}}}}
        )
        assert "sync.enabled is true but sync.github is not configured" not in fb

    def test_warns_documents_enabled_without_categories(self, in_tmp: Path) -> None:
        fb = self._run_with(in_tmp, {"documents": {"enabled": True}})
        assert "documents.enabled is true but no document categories configured" in fb

    def test_no_warnings_when_features_disabled(self, in_tmp: Path) -> None:
        fb = self._run_with(
            in_tmp,
            {
                "sync": {"enabled": False},
                "documents": {"enabled": False},
                "product": {"enabled": False},
                "design_tokens": {"enabled": False},
            },
        )
        assert "Warning:" not in fb

    def test_no_product_warning_even_when_enabled(self, in_tmp: Path) -> None:
        # Matches TestSessionStartValidation::test_no_warnings_when_properly_configured —
        # product.enabled must NOT trigger any new warning.
        fb = self._run_with(
            in_tmp,
            {
                "sync": {"enabled": True, "github": {"label_mapping": {"BUG": "bug"}}},
                "documents": {
                    "enabled": True,
                    "categories": {"arch": {"files": ["docs/ARCH.md"]}},
                },
                "product": {"enabled": True, "goals_file": ".ll/ll-goals.md"},
                "design_tokens": {"enabled": False},
            },
        )
        assert "Warning:" not in fb

    def test_warns_design_tokens_enabled_without_path(self, in_tmp: Path) -> None:
        fb = self._run_with(in_tmp, {"design_tokens": {"enabled": True}})
        assert "design_tokens.enabled is true but path" in fb
        assert "does not exist" in fb


class TestSessionStartLargeConfigWarning:
    def test_large_config_warning_appears(self, in_tmp: Path) -> None:
        # Build a config whose JSON repr exceeds the 5000-char threshold.
        big = {"items": ["x" * 100 for _ in range(60)]}
        (in_tmp / ".ll").mkdir()
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps(big))

        result = handle(_event())

        assert result.feedback is not None
        assert "Warning: Large config (" in result.feedback

    def test_small_config_no_warning(self, in_tmp: Path) -> None:
        (in_tmp / ".ll").mkdir()
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({"a": 1}))

        result = handle(_event())

        assert result.feedback is not None
        assert "Large config" not in result.feedback


class TestSessionStartBackfillThread:
    """ENH-1830: session_start spawns a daemon backfill thread when config is present."""

    def test_spawns_daemon_thread_when_config_present(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (in_tmp / ".ll").mkdir()
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({}))

        started: list[bool] = []

        class _MockThread:
            def __init__(self, target, daemon=False, **kw):
                started.append(daemon)

            def start(self):
                pass

        monkeypatch.setattr("little_loops.hooks.session_start.threading.Thread", _MockThread)
        handle(_event())
        assert len(started) == 1, "exactly one thread should be spawned"
        assert started[0] is True, "thread must be a daemon thread"

    def test_no_thread_when_no_config(self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        started: list[bool] = []

        class _MockThread:
            def __init__(self, target, daemon=False, **kw):
                started.append(daemon)

            def start(self):
                pass

        monkeypatch.setattr("little_loops.hooks.session_start.threading.Thread", _MockThread)
        handle(_event())
        assert started == [], "no thread should be spawned when project has no config"

    def test_backfill_error_does_not_propagate(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The thread target catches exceptions and logs a warning — errors must not surface."""
        (in_tmp / ".ll").mkdir()
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({}))

        executed: list[bool] = []

        def _inline_thread(target, daemon=False, **kw):
            class _T:
                def start(self_inner):
                    executed.append(True)
                    target()  # run synchronously; must not raise

            return _T()

        def _raise(*a, **kw):
            raise RuntimeError("simulated backfill failure")

        monkeypatch.setattr("little_loops.hooks.session_start.threading.Thread", _inline_thread)
        # Patch backfill_incremental inside the module that imports it at call time
        import little_loops.session_store as ss

        monkeypatch.setattr(ss, "backfill_incremental", _raise)
        result = handle(_event())
        assert result.exit_code == 0
        assert executed == [True], "thread target should have been called"

    def test_backfill_warning_logged(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When backfill_incremental raises, a WARNING is emitted by the session_start logger."""
        (in_tmp / ".ll").mkdir()
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({}))

        def _inline_thread(target, daemon=False, **kw):
            class _T:
                def start(self_inner):
                    target()  # run synchronously

            return _T()

        def _raise(*a, **kw):
            raise RuntimeError("simulated backfill failure")

        monkeypatch.setattr("little_loops.hooks.session_start.threading.Thread", _inline_thread)
        import little_loops.session_store as ss
        import little_loops.user_messages as um

        monkeypatch.setattr(ss, "backfill_incremental", _raise)
        # Create a JSONL file so the backfill guard passes (ENH-1945: empty
        # jsonl_files list skips the backfill call, so a file must exist).
        (in_tmp / "session.jsonl").write_text("{}")
        monkeypatch.setattr(um, "get_project_folder", lambda *a, **kw: in_tmp)

        with caplog.at_level(logging.WARNING):
            result = handle(_event())

        assert result.exit_code == 0
        assert any("backfill" in r.message.lower() for r in caplog.records)


class TestSessionStartCodexTranscriptPath:
    """ENH-1945: session_start consumes transcript_path from Codex hook payloads."""

    def _codex_event(self, transcript_path: str | None = None) -> LLHookEvent:
        """Helper: create a Codex LLHookEvent with optional transcript_path."""
        payload: dict[str, str] = {}
        if transcript_path is not None:
            payload["transcript_path"] = transcript_path
        return LLHookEvent(host="codex", intent="session_start", payload=payload)

    def test_codex_backfill_consumes_transcript_path(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When transcript_path is in the Codex payload, _run_backfill uses it directly."""
        (in_tmp / ".ll").mkdir()
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({}))

        # Create a mock transcript file
        transcript = in_tmp / "codex-session.jsonl"
        transcript.write_text(json.dumps({"role": "user", "content": "hello"}) + "\n")

        captured_files: list[list[Path]] = []

        def _capture_backfill(db, *, jsonl_files, **kw):
            captured_files.append(list(jsonl_files))

        def _inline_thread(target, daemon=False, **kw):
            class _T:
                def start(self_inner):
                    target()

            return _T()

        monkeypatch.setattr("little_loops.hooks.session_start.threading.Thread", _inline_thread)
        import little_loops.session_store as ss

        monkeypatch.setattr(ss, "backfill_incremental", _capture_backfill)

        result = handle(self._codex_event(transcript_path=str(transcript)))
        assert result.exit_code == 0
        assert len(captured_files) == 1
        assert captured_files[0] == [transcript]

    def test_codex_backfill_falls_back_when_no_transcript_path(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When transcript_path is absent from payload, falls back to directory probing."""
        (in_tmp / ".ll").mkdir()
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({}))

        # Create a mock Claude Code project folder
        fake_home = in_tmp / "home"
        claude_dir = fake_home / ".claude" / "projects"
        encoded = str(in_tmp.resolve()).replace("/", "-")
        project_dir = claude_dir / encoded
        project_dir.mkdir(parents=True)
        session_file = project_dir / "session.jsonl"
        session_file.write_text(json.dumps({"role": "user", "content": "hello"}) + "\n")
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        captured_files: list[list[Path]] = []

        def _capture_backfill(db, *, jsonl_files, **kw):
            captured_files.append(list(jsonl_files))

        def _inline_thread(target, daemon=False, **kw):
            class _T:
                def start(self_inner):
                    target()

            return _T()

        monkeypatch.setattr("little_loops.hooks.session_start.threading.Thread", _inline_thread)
        import little_loops.session_store as ss

        monkeypatch.setattr(ss, "backfill_incremental", _capture_backfill)

        result = handle(self._codex_event())  # No transcript_path in payload
        assert result.exit_code == 0
        # Should fall back to directory probing (which finds session.jsonl)
        assert len(captured_files) == 1
        assert len(captured_files[0]) == 1

    def test_codex_backfill_skips_when_transcript_does_not_exist(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When transcript_path points to a missing file, backfill skips gracefully."""
        (in_tmp / ".ll").mkdir()
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({}))

        captured_files: list[list[Path]] = []

        def _capture_backfill(db, *, jsonl_files, **kw):
            captured_files.append(list(jsonl_files))

        def _inline_thread(target, daemon=False, **kw):
            class _T:
                def start(self_inner):
                    target()

            return _T()

        monkeypatch.setattr("little_loops.hooks.session_start.threading.Thread", _inline_thread)
        import little_loops.session_store as ss

        monkeypatch.setattr(ss, "backfill_incremental", _capture_backfill)

        result = handle(self._codex_event(transcript_path="/nonexistent/session.jsonl"))
        assert result.exit_code == 0
        # No files to backfill — backfill_incremental should not be called
        # OR called with empty jsonl_files list
        assert len(captured_files) == 0 or captured_files[0] == []

    def test_codex_payload_preserves_event_for_backfill(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The event object is NOT deleted before _run_backfill can read it."""
        (in_tmp / ".ll").mkdir()
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({}))

        transcript = in_tmp / "codex-session.jsonl"
        transcript.write_text(json.dumps({"role": "user", "content": "hello"}) + "\n")

        captured_payload: list[dict] = []

        def _capture(db, *, jsonl_files, **kw):
            captured_payload.append({"jsonl_files": [str(f) for f in jsonl_files]})

        def _inline_thread(target, daemon=False, **kw):
            class _T:
                def start(self_inner):
                    target()

            return _T()

        monkeypatch.setattr("little_loops.hooks.session_start.threading.Thread", _inline_thread)
        import little_loops.session_store as ss

        monkeypatch.setattr(ss, "backfill_incremental", _capture)

        result = handle(self._codex_event(transcript_path=str(transcript)))
        assert result.exit_code == 0
        assert len(captured_payload) == 1
        assert captured_payload[0]["jsonl_files"] == [str(transcript)]


class TestSessionStartProjectDigest:
    """Tests for gated project-context digest injection (ENH-1907)."""

    def test_gate_off_no_project_context_block(self, in_tmp: Path) -> None:
        (in_tmp / ".ll").mkdir()
        (in_tmp / ".ll" / "ll-config.json").write_text(
            json.dumps({"history": {"session_digest": {"enabled": False}}})
        )
        result = handle(_event())
        assert result.exit_code == 0
        assert "<project_context>" not in (result.stdout or "")

    def test_gate_on_empty_db_no_block(self, in_tmp: Path) -> None:
        (in_tmp / ".ll").mkdir()
        (in_tmp / ".ll" / "ll-config.json").write_text(
            json.dumps({"history": {"session_digest": {"enabled": True}}})
        )
        result = handle(_event())
        assert result.exit_code == 0
        assert "<project_context>" not in (result.stdout or "")

    def test_gate_on_populated_db_block_present(self, in_tmp: Path) -> None:
        from little_loops.session_store import record_correction

        (in_tmp / ".ll").mkdir()
        (in_tmp / ".ll" / "ll-config.json").write_text(
            json.dumps({"history": {"session_digest": {"enabled": True}}})
        )
        db = in_tmp / ".ll" / "history.db"
        record_correction(db, "sess-1", "no Co-Authored-By trailers", "user")

        result = handle(_event())
        assert result.exit_code == 0
        assert "<project_context>" in (result.stdout or "")

    def test_gate_on_block_respects_char_cap(self, in_tmp: Path) -> None:
        from little_loops.session_store import record_correction

        (in_tmp / ".ll").mkdir()
        (in_tmp / ".ll" / "ll-config.json").write_text(
            json.dumps({"history": {"session_digest": {"enabled": True, "char_cap": 300}}})
        )
        db = in_tmp / ".ll" / "history.db"
        for i in range(20):
            record_correction(
                db, f"sess-{i}", f"correction item {i} with some extra text here", "user"
            )

        result = handle(_event())
        assert result.exit_code == 0
        stdout = result.stdout or ""
        if "<project_context>" in stdout:
            start = stdout.index("<project_context>")
            end = stdout.index("</project_context>") + len("</project_context>")
            block = stdout[start:end]
            assert len(block) <= 300

    def test_digest_failure_does_not_block_startup(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (in_tmp / ".ll").mkdir()
        (in_tmp / ".ll" / "ll-config.json").write_text(
            json.dumps({"history": {"session_digest": {"enabled": True}}})
        )
        import little_loops.history_reader as hr

        def _raise(*a: object, **kw: object) -> None:
            raise RuntimeError("simulated digest failure")

        monkeypatch.setattr(hr, "project_digest", _raise)

        result = handle(_event())
        assert result.exit_code == 0
