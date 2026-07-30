"""Python-direct tests for ``little_loops.hooks.drift_check.handle`` (ENH-2888).

The handler surfaces throttled ``mention``/``route``-severity doc-drift
findings from ``doc_counts.verify_documentation()`` at session start. It is
throttled to at most once per ``hooks.doc_drift_throttle_days`` (default 7)
via a timestamp state file, and can be disabled entirely with
``LL_DOC_DRIFT_DISABLE``. Modeled on ``test_edit_batch_hook.py``'s
``_Clock`` fixture and ``test_sweep_stale_refs.py``'s no-op ladder.
"""

from __future__ import annotations

import json

import pytest

from little_loops.doc_counts import CountResult, VerificationResult
from little_loops.hooks import drift_check
from little_loops.hooks.drift_check import _STATE_FILENAME, handle
from little_loops.hooks.types import LLHookEvent


def _event(payload: dict | None = None, *, cwd: str | None = None) -> LLHookEvent:
    return LLHookEvent(host="claude-code", intent="drift_check", payload=payload or {}, cwd=cwd)


class _Clock:
    """Monkeypatchable stand-in for ``drift_check._now``."""

    def __init__(self, start: float = 1_000_000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch, tmp_path) -> _Clock:
    """Isolate the state file to ``tmp_path`` and give the handler a fake clock.

    ``tmp_path`` must itself resolve as a project root (ENH-2927 routes state
    resolution through ``resolve_ll_dir``) or the handler silently no-ops.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    (tmp_path / ".ll").mkdir(exist_ok=True)
    c = _Clock()
    monkeypatch.setattr(drift_check, "_now", c)
    return c


def _mock_verification(mismatches: list[CountResult]) -> VerificationResult:
    result = VerificationResult(total_checked=len(mismatches))
    for m in mismatches:
        result.add_result(m)
    return result


class TestOptOut:
    def test_env_var_disable_skips_entirely(self, clock: _Clock, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("LL_DOC_DRIFT_DISABLE", "1")
        result = handle(_event(cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None
        assert not (tmp_path / ".ll" / _STATE_FILENAME).exists()


class TestNoStrayDirCreation:
    """ENH-2927: a hook must never create ``.ll/`` outside a resolved project."""

    def test_no_project_and_no_claude_project_dir_is_noop(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """cwd outside any project, no CLAUDE_PROJECT_DIR: exit 0, no state written."""
        outside = tmp_path / "not-a-project"
        outside.mkdir()
        monkeypatch.chdir(outside)
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.setattr(drift_check, "_now", _Clock())
        result = handle(_event(cwd=str(outside)))
        assert result.exit_code == 0
        assert result.feedback is None
        assert not (outside / ".ll").exists()

    def test_claude_project_dir_anchors_state_there(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """CLAUDE_PROJECT_DIR wins over cwd — state lands at that root, not cwd."""
        project_root = tmp_path / "the-project"
        project_root.mkdir()
        subdir = project_root / "sub"
        subdir.mkdir()
        monkeypatch.chdir(subdir)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project_root))
        monkeypatch.setattr(drift_check, "_now", _Clock())
        monkeypatch.setattr(
            "little_loops.doc_counts.verify_documentation",
            lambda base_dir=None: _mock_verification([]),
        )
        result = handle(_event(cwd=str(subdir)))
        assert result.exit_code == 0
        assert (project_root / ".ll" / _STATE_FILENAME).is_file()
        assert not (subdir / ".ll").exists()


class TestNoFindings:
    def test_no_mismatches_passes_through_silently(
        self, clock: _Clock, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setattr(
            "little_loops.doc_counts.verify_documentation",
            lambda base_dir=None: _mock_verification([]),
        )
        result = handle(_event(cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None
        assert (tmp_path / ".ll" / _STATE_FILENAME).is_file()

    def test_auto_severity_mismatch_is_not_surfaced(
        self, clock: _Clock, monkeypatch, tmp_path
    ) -> None:
        """Only mention/route severity findings surface — auto is silently skipped."""
        mismatch = CountResult(
            category="commands",
            actual=5,
            documented=4,
            file="README.md",
            line=10,
            matches=False,
            action_severity="auto",
        )
        monkeypatch.setattr(
            "little_loops.doc_counts.verify_documentation",
            lambda base_dir=None: _mock_verification([mismatch]),
        )
        result = handle(_event(cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None


class TestFindingsSurfaced:
    def test_mention_severity_mismatch_surfaces_feedback(
        self, clock: _Clock, monkeypatch, tmp_path
    ) -> None:
        mismatch = CountResult(
            category="commands",
            actual=5,
            documented=4,
            file="README.md",
            line=10,
            matches=False,
            action_severity="mention",
        )
        monkeypatch.setattr(
            "little_loops.doc_counts.verify_documentation",
            lambda base_dir=None: _mock_verification([mismatch]),
        )
        result = handle(_event(cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is not None
        assert "README.md:10" in result.feedback
        assert "commands" in result.feedback

    def test_route_severity_includes_route_owner(
        self, clock: _Clock, monkeypatch, tmp_path
    ) -> None:
        mismatch = CountResult(
            category="loops",
            actual=3,
            documented=2,
            file="docs/ARCHITECTURE.md",
            line=5,
            matches=False,
            action_severity="route",
            route_owner="/ll:update-docs",
        )
        monkeypatch.setattr(
            "little_loops.doc_counts.verify_documentation",
            lambda base_dir=None: _mock_verification([mismatch]),
        )
        result = handle(_event(cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert "/ll:update-docs" in result.feedback


class TestThrottle:
    def test_second_call_within_window_is_throttled(
        self, clock: _Clock, monkeypatch, tmp_path
    ) -> None:
        mismatch = CountResult(
            category="commands",
            actual=5,
            documented=4,
            file="README.md",
            line=10,
            matches=False,
            action_severity="mention",
        )
        monkeypatch.setattr(
            "little_loops.doc_counts.verify_documentation",
            lambda base_dir=None: _mock_verification([mismatch]),
        )
        first = handle(_event(cwd=str(tmp_path)))
        assert first.feedback is not None

        clock.advance(60)  # well within the 7-day default throttle
        second = handle(_event(cwd=str(tmp_path)))
        assert second.exit_code == 0
        assert second.feedback is None

    def test_call_after_throttle_window_reruns(self, clock: _Clock, monkeypatch, tmp_path) -> None:
        mismatch = CountResult(
            category="commands",
            actual=5,
            documented=4,
            file="README.md",
            line=10,
            matches=False,
            action_severity="mention",
        )
        monkeypatch.setattr(
            "little_loops.doc_counts.verify_documentation",
            lambda base_dir=None: _mock_verification([mismatch]),
        )
        first = handle(_event(cwd=str(tmp_path)))
        assert first.feedback is not None

        clock.advance(8 * 86400)  # past the 7-day default throttle
        second = handle(_event(cwd=str(tmp_path)))
        assert second.feedback is not None

    def test_custom_throttle_days_from_config(self, clock: _Clock, monkeypatch, tmp_path) -> None:
        (tmp_path / ".ll").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".ll" / "ll-config.json").write_text(
            json.dumps({"hooks": {"doc_drift_throttle_days": 1}})
        )
        mismatch = CountResult(
            category="commands",
            actual=5,
            documented=4,
            file="README.md",
            line=10,
            matches=False,
            action_severity="mention",
        )
        monkeypatch.setattr(
            "little_loops.doc_counts.verify_documentation",
            lambda base_dir=None: _mock_verification([mismatch]),
        )
        first = handle(_event(cwd=str(tmp_path)))
        assert first.feedback is not None

        clock.advance(2 * 86400)  # past the configured 1-day throttle
        second = handle(_event(cwd=str(tmp_path)))
        assert second.feedback is not None


class TestErrorHandling:
    def test_verify_documentation_error_passes_through(
        self, clock: _Clock, monkeypatch, tmp_path
    ) -> None:
        def _raise(base_dir=None):
            raise RuntimeError("boom")

        monkeypatch.setattr("little_loops.doc_counts.verify_documentation", _raise)
        result = handle(_event(cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_malformed_state_file_passes_through(
        self, clock: _Clock, monkeypatch, tmp_path
    ) -> None:
        state_dir = tmp_path / ".ll"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / _STATE_FILENAME).write_text("not json{{{")
        monkeypatch.setattr(
            "little_loops.doc_counts.verify_documentation",
            lambda base_dir=None: _mock_verification([]),
        )
        result = handle(_event(cwd=str(tmp_path)))
        assert result.exit_code == 0
