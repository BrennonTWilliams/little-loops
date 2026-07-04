"""Tests for little_loops.pytest_history_plugin (ENH-2459)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from little_loops.pytest_history_plugin import (
    LLHistoryPlugin,
    _capture_enabled,
    _infer_env_label,
    pytest_configure,
)
from little_loops.session_store import recent


def _report(when: str, outcome: str, nodeid: str = "tests/test_x.py::test_a") -> SimpleNamespace:
    """Build a minimal pytest TestReport stand-in."""
    return SimpleNamespace(
        when=when,
        nodeid=nodeid,
        passed=outcome == "passed",
        failed=outcome == "failed",
        skipped=outcome == "skipped",
    )


class TestCaptureGating:
    """Capture activates only inside little-loops projects, honours opt-out."""

    def test_opt_out_env_disables(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ll").mkdir()
        monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_LL_HISTORY", "1")
        assert not _capture_enabled()

    def test_disabled_without_ll_dir(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PYTEST_DISABLE_PLUGIN_LL_HISTORY", raising=False)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        assert not _capture_enabled()

    def test_enabled_with_ll_dir(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ll").mkdir()
        monkeypatch.delenv("PYTEST_DISABLE_PLUGIN_LL_HISTORY", raising=False)
        monkeypatch.delenv("LL_HISTORY_DB", raising=False)
        assert _capture_enabled()

    def test_enabled_via_ll_history_db_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PYTEST_DISABLE_PLUGIN_LL_HISTORY", raising=False)
        monkeypatch.setenv("LL_HISTORY_DB", str(tmp_path / "h.db"))
        assert _capture_enabled()

    def test_configure_skips_xdist_worker(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ll").mkdir()
        monkeypatch.delenv("PYTEST_DISABLE_PLUGIN_LL_HISTORY", raising=False)
        config = MagicMock()
        config.workerinput = {"workerid": "gw0"}  # marks an xdist worker
        pytest_configure(config)
        config.pluginmanager.register.assert_not_called()

    def test_configure_registers_on_controller(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ll").mkdir()
        monkeypatch.delenv("PYTEST_DISABLE_PLUGIN_LL_HISTORY", raising=False)
        config = MagicMock(spec=["pluginmanager"])  # no workerinput attribute
        pytest_configure(config)
        assert config.pluginmanager.register.called


class TestOutcomeCounting:
    """pytest_runtest_logreport tallies per-phase outcomes."""

    def test_counts_call_phase_outcomes(self) -> None:
        plugin = LLHistoryPlugin("pytest")
        plugin.pytest_runtest_logreport(_report("call", "passed"))
        plugin.pytest_runtest_logreport(_report("call", "passed"))
        plugin.pytest_runtest_logreport(_report("call", "failed", "tests/t.py::test_fail"))
        plugin.pytest_runtest_logreport(_report("call", "skipped"))
        assert plugin.passed == 2
        assert plugin.failed == 1
        assert plugin.skipped == 1
        assert plugin.failing_names == ["tests/t.py::test_fail"]

    def test_setup_failure_counts_as_error(self) -> None:
        plugin = LLHistoryPlugin("pytest")
        plugin.pytest_runtest_logreport(_report("setup", "failed", "tests/t.py::test_err"))
        assert plugin.errored == 1
        assert plugin.failed == 0
        assert plugin.failing_names == ["tests/t.py::test_err"]

    def test_setup_skip_counts_as_skipped(self) -> None:
        plugin = LLHistoryPlugin("pytest")
        plugin.pytest_runtest_logreport(_report("setup", "skipped"))
        assert plugin.skipped == 1

    def test_teardown_failure_counts_as_error(self) -> None:
        plugin = LLHistoryPlugin("pytest")
        plugin.pytest_runtest_logreport(_report("teardown", "failed"))
        assert plugin.errored == 1


class TestSessionFinishWritesRow:
    """pytest_sessionfinish records one test_run_events row (best-effort)."""

    def test_writes_row_to_history_db(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        db = tmp_path / "h.db"
        monkeypatch.setenv("LL_HISTORY_DB", str(db))
        plugin = LLHistoryPlugin("pytest scripts/tests/test_x.py")
        plugin.pytest_sessionstart(None)
        plugin.pytest_runtest_logreport(_report("call", "passed"))
        plugin.pytest_runtest_logreport(_report("call", "failed", "tests/t.py::test_boom"))
        plugin.pytest_sessionfinish(None, exitstatus=1)

        rows = recent(db, kind="test_run")
        assert len(rows) == 1
        row = rows[0]
        assert row["total"] == 2
        assert row["passed"] == 1
        assert row["failed"] == 1
        assert json.loads(row["failing_names_json"]) == ["tests/t.py::test_boom"]
        assert row["command"].startswith("pytest")
        assert row["duration_s"] is not None
        assert row["env_label"] in ("ci", "worktree", "local")

    def test_sessionfinish_never_raises_on_broken_db(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Point at a path that cannot be a database (a directory).
        monkeypatch.setenv("LL_HISTORY_DB", str(tmp_path))
        plugin = LLHistoryPlugin("pytest")
        plugin.pytest_runtest_logreport(_report("call", "passed"))
        plugin.pytest_sessionfinish(None, exitstatus=0)  # must not raise


class TestEnvLabel:
    """_infer_env_label classifies ci / worktree / local."""

    def test_ci_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CI", "true")
        assert _infer_env_label() == "ci"

    def test_ll_auto_run_counts_as_ci(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in ("CI", "GITHUB_ACTIONS", "JENKINS_URL"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("LL_AUTO_RUN", "true")
        assert _infer_env_label() == "ci"

    def test_worktree_detection(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        for var in ("CI", "GITHUB_ACTIONS", "JENKINS_URL", "LL_AUTO_RUN"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x\n", encoding="utf-8")
        assert _infer_env_label() == "worktree"

    def test_local_default(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        for var in ("CI", "GITHUB_ACTIONS", "JENKINS_URL", "LL_AUTO_RUN"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.chdir(tmp_path)
        assert _infer_env_label() == "local"
