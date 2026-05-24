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
            },
        )
        assert "Warning:" not in fb


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
