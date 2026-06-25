"""Python-direct tests for ``little_loops.hooks.session_start.handle`` (FEAT-1450).

Adapter round-trip tests live in ``test_hooks_integration.py::TestSessionStartValidation``;
this module exercises the pure-function handler under unit conditions.
"""

from __future__ import annotations

import json
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
        (in_tmp / ".ll").mkdir(exist_ok=True)
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
        (in_tmp / ".ll").mkdir(exist_ok=True)
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({"ll": True}))

        result = handle(LLHookEvent(host="codex", intent="session_start", payload={}))

        assert result.exit_code == 0
        assert result.stdout is not None
        assert json.loads(result.stdout) == {"codex": True}


class TestSessionStartContextStateCleanup:
    def test_removes_prior_session_state(self, in_tmp: Path) -> None:
        (in_tmp / ".ll").mkdir(exist_ok=True)
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
        (in_tmp / ".ll").mkdir(exist_ok=True)
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
        (in_tmp / ".ll").mkdir(exist_ok=True)
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps(big))

        result = handle(_event())

        assert result.feedback is not None
        assert "Warning: Large config (" in result.feedback

    def test_small_config_no_warning(self, in_tmp: Path) -> None:
        (in_tmp / ".ll").mkdir(exist_ok=True)
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({"a": 1}))

        result = handle(_event())

        assert result.feedback is not None
        assert "Large config" not in result.feedback


class TestSessionStartBackfillThread:
    """ENH-1830 / BUG-1882: session_start spawns a detached subprocess for backfill."""

    def _mock_popen(self, monkeypatch: pytest.MonkeyPatch) -> list[list]:
        """Patch subprocess.Popen; return list that accumulates captured arg lists."""
        calls: list[list] = []

        class _FakePopen:
            def __init__(self_inner, args, **kw):
                calls.append(list(args))

        monkeypatch.setattr("little_loops.hooks.session_start.subprocess.Popen", _FakePopen)
        return calls

    def test_spawns_subprocess_when_config_present(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (in_tmp / ".ll").mkdir(exist_ok=True)
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({}))
        calls = self._mock_popen(monkeypatch)
        import little_loops.user_messages as um

        monkeypatch.setattr(um, "get_project_folder", lambda *a, **kw: in_tmp)
        monkeypatch.delenv("LL_NON_INTERACTIVE", raising=False)
        handle(_event())
        assert len(calls) == 1, "exactly one Popen call should be made"
        assert "backfill_worker" in " ".join(calls[0])

    def test_no_subprocess_when_no_config(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self._mock_popen(monkeypatch)
        handle(_event())
        assert calls == [], "no subprocess should be spawned when project has no config"

    def test_backfill_error_does_not_propagate(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If Popen raises, contextlib.suppress isolates it — handle() must return 0."""
        (in_tmp / ".ll").mkdir(exist_ok=True)
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({}))

        def _raise(*a, **kw):
            raise OSError("simulated Popen failure")

        monkeypatch.setattr("little_loops.hooks.session_start.subprocess.Popen", _raise)
        import little_loops.user_messages as um

        monkeypatch.setattr(um, "get_project_folder", lambda *a, **kw: in_tmp)
        result = handle(_event())
        assert result.exit_code == 0

    def test_backfill_subprocess_passes_db_and_path(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Subprocess receives the db path and project folder as positional args."""
        (in_tmp / ".ll").mkdir(exist_ok=True)
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({}))
        calls = self._mock_popen(monkeypatch)
        import little_loops.user_messages as um

        monkeypatch.setattr(um, "get_project_folder", lambda *a, **kw: in_tmp)
        monkeypatch.delenv("LL_NON_INTERACTIVE", raising=False)
        handle(_event())
        assert len(calls) == 1
        args = calls[0]
        assert str(in_tmp / ".ll" / "history.db") in args
        assert str(in_tmp) in args


class TestSessionStartCodexTranscriptPath:
    """ENH-1945: session_start consumes transcript_path from Codex hook payloads."""

    def _codex_event(self, transcript_path: str | None = None) -> LLHookEvent:
        payload: dict[str, str] = {}
        if transcript_path is not None:
            payload["transcript_path"] = transcript_path
        return LLHookEvent(host="codex", intent="session_start", payload=payload)

    def _mock_popen(self, monkeypatch: pytest.MonkeyPatch) -> list[list]:
        calls: list[list] = []

        class _FakePopen:
            def __init__(self_inner, args, **kw):
                calls.append(list(args))

        monkeypatch.setattr("little_loops.hooks.session_start.subprocess.Popen", _FakePopen)
        return calls

    def test_codex_backfill_consumes_transcript_path(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When transcript_path is in the Codex payload, subprocess receives it directly."""
        (in_tmp / ".ll").mkdir(exist_ok=True)
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({}))

        transcript = in_tmp / "codex-session.jsonl"
        transcript.write_text(json.dumps({"role": "user", "content": "hello"}) + "\n")
        calls = self._mock_popen(monkeypatch)
        monkeypatch.delenv("LL_NON_INTERACTIVE", raising=False)

        result = handle(self._codex_event(transcript_path=str(transcript)))
        assert result.exit_code == 0
        assert len(calls) == 1
        assert str(transcript) in calls[0]

    def test_codex_backfill_falls_back_when_no_transcript_path(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When transcript_path is absent, falls back to directory probing."""
        (in_tmp / ".ll").mkdir(exist_ok=True)
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({}))
        calls = self._mock_popen(monkeypatch)
        import little_loops.user_messages as um

        project_dir = in_tmp / "sessions"
        project_dir.mkdir()
        monkeypatch.setattr(um, "get_project_folder", lambda *a, **kw: project_dir)
        monkeypatch.delenv("LL_NON_INTERACTIVE", raising=False)

        result = handle(self._codex_event())
        assert result.exit_code == 0
        assert len(calls) == 1
        assert str(project_dir) in calls[0]

    def test_codex_backfill_skips_when_transcript_does_not_exist(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When transcript_path points to a missing file and no project folder, no Popen."""
        (in_tmp / ".ll").mkdir(exist_ok=True)
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({}))
        calls = self._mock_popen(monkeypatch)
        import little_loops.user_messages as um

        monkeypatch.setattr(um, "get_project_folder", lambda *a, **kw: None)

        result = handle(self._codex_event(transcript_path="/nonexistent/session.jsonl"))
        assert result.exit_code == 0
        assert calls == [], "no subprocess when path is missing and no fallback folder"

    def test_codex_payload_path_passed_to_subprocess(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """transcript_path from payload is read synchronously and passed to subprocess args."""
        (in_tmp / ".ll").mkdir(exist_ok=True)
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({}))

        transcript = in_tmp / "codex-session.jsonl"
        transcript.write_text(json.dumps({"role": "user", "content": "hello"}) + "\n")
        calls = self._mock_popen(monkeypatch)
        monkeypatch.delenv("LL_NON_INTERACTIVE", raising=False)

        result = handle(self._codex_event(transcript_path=str(transcript)))
        assert result.exit_code == 0
        assert len(calls) == 1
        assert str(transcript) in calls[0]


class TestSessionStartProjectDigest:
    """Tests for gated project-context digest injection (ENH-1907)."""

    def test_gate_off_no_project_context_block(self, in_tmp: Path) -> None:
        (in_tmp / ".ll").mkdir(exist_ok=True)
        (in_tmp / ".ll" / "ll-config.json").write_text(
            json.dumps({"history": {"session_digest": {"enabled": False}}})
        )
        result = handle(_event())
        assert result.exit_code == 0
        assert "<project_context>" not in (result.stdout or "")

    def test_gate_on_empty_db_no_block(self, in_tmp: Path) -> None:
        (in_tmp / ".ll").mkdir(exist_ok=True)
        (in_tmp / ".ll" / "ll-config.json").write_text(
            json.dumps({"history": {"session_digest": {"enabled": True}}})
        )
        result = handle(_event())
        assert result.exit_code == 0
        assert "<project_context>" not in (result.stdout or "")

    def test_gate_on_populated_db_block_present(self, in_tmp: Path) -> None:
        from little_loops.session_store import record_correction

        (in_tmp / ".ll").mkdir(exist_ok=True)
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

        (in_tmp / ".ll").mkdir(exist_ok=True)
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

    def test_no_history_block_defaults_digest_on(self, in_tmp: Path) -> None:
        """Digest fires when config has no history block — default enabled=True (ENH-2040)."""
        from little_loops.session_store import record_correction

        (in_tmp / ".ll").mkdir(exist_ok=True)
        # Config exists but has no history: block — default SessionDigestConfig.enabled=True
        (in_tmp / ".ll" / "ll-config.json").write_text(json.dumps({"project": {"name": "test"}}))
        db = in_tmp / ".ll" / "history.db"
        record_correction(db, "sess-1", "no Co-Authored-By trailers", "user")

        result = handle(_event())
        assert result.exit_code == 0
        assert "<project_context>" in (result.stdout or "")

    def test_digest_failure_does_not_block_startup(
        self, in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (in_tmp / ".ll").mkdir(exist_ok=True)
        (in_tmp / ".ll" / "ll-config.json").write_text(
            json.dumps({"history": {"session_digest": {"enabled": True}}})
        )
        import little_loops.history_reader as hr

        def _raise(*a: object, **kw: object) -> None:
            raise RuntimeError("simulated digest failure")

        monkeypatch.setattr(hr, "project_digest", _raise)

        result = handle(_event())
        assert result.exit_code == 0
