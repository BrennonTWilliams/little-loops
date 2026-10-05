"""Python-direct tests for ``little_loops.hooks.edit_batch_nudge.handle`` (FEAT-2470).

The handler is stateful: it tracks consecutive *unbatched* single edits in
``.ll/ll-edit-batch-state.json`` and only nudges (``exit_code=2``) once a run
reaches ``_NUDGE_THRESHOLD`` — and at most **once per session**. A sticky
``nudged`` latch in the state file suppresses all subsequent nudges until
``session_id`` changes. Batched edits (fires within
``_BATCH_WINDOW_SECONDS``) and ``MultiEdit`` reset the run counter; every
non-edit tool passes through with exit 0 and no feedback. Tests isolate state
via ``monkeypatch.chdir(tmp_path)`` and drive the clock via ``_now``.
"""

from __future__ import annotations

import json

import pytest

from little_loops.hooks import edit_batch_nudge
from little_loops.hooks.edit_batch_nudge import (
    _BATCH_WINDOW_SECONDS,
    _NUDGE_THRESHOLD,
    handle,
)
from little_loops.hooks.types import LLHookEvent


def _event(
    payload: dict | None = None, *, cwd: str | None = None, host: str = "claude-code"
) -> LLHookEvent:
    return LLHookEvent(
        host=host,
        intent="edit_batch_nudge",
        payload=payload or {},
        cwd=cwd,
    )


class _Clock:
    """Monkeypatchable stand-in for ``edit_batch_nudge._now``."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch, tmp_path) -> _Clock:
    """Isolate the state file to ``tmp_path`` and give the handler a fake clock.

    ``tmp_path`` must itself resolve as a project root (ENH-2927 routes state
    resolution through ``resolve_ll_dir``, which requires a discoverable
    ``.ll/`` on the walk) — otherwise the handler silently no-ops rather than
    writing state, and every assertion below would see ``exit_code == 0``
    regardless of the run counter.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    (tmp_path / ".ll").mkdir()
    c = _Clock()
    monkeypatch.setattr(edit_batch_nudge, "_now", c)
    return c


class TestPassThrough:
    def test_non_edit_tool_passes_through(self, clock: _Clock) -> None:
        result = handle(_event({"tool_name": "Bash", "tool_input": {"command": "ls"}}))
        assert result.exit_code == 0
        assert result.feedback is None
        assert result.stdout is None

    def test_empty_payload_passes_through(self, clock: _Clock) -> None:
        result = handle(_event())
        assert result.exit_code == 0
        assert result.feedback is None
        assert result.stdout is None

    def test_read_tool_passes_through(self, clock: _Clock) -> None:
        result = handle(_event({"tool_name": "Read"}))
        assert result.exit_code == 0
        assert result.feedback is None
        assert result.stdout is None

    def test_handler_does_not_mutate_payload(self, clock: _Clock) -> None:
        payload = {"tool_name": "Edit", "session_id": "s1"}
        handle(_event(payload))
        assert payload == {"tool_name": "Edit", "session_id": "s1"}


class TestStatefulNudge:
    def _edit(self, session: str = "s1", *, host: str = "claude-code"):
        return handle(_event({"tool_name": "Edit", "session_id": session}, host=host))

    def test_single_edit_does_not_nudge(self, clock: _Clock) -> None:
        result = self._edit()
        assert result.exit_code == 0
        assert result.feedback is None
        assert result.stdout is None

    @pytest.mark.parametrize("host", ["claude-code", "codex"])
    def test_run_of_unbatched_edits_nudges_at_threshold(self, clock: _Clock, host: str) -> None:
        gap = _BATCH_WINDOW_SECONDS + 1.0
        results = []
        for _ in range(_NUDGE_THRESHOLD):
            results.append(self._edit(host=host))
            clock.advance(gap)
        # Only the threshold-th edit nudges.
        assert all(r.exit_code == 0 and r.stdout is None for r in results[:-1])
        fired = results[-1]
        assert "batch" in (fired.feedback or "").lower()
        if host == "claude-code":
            assert fired.exit_code == 0
            payload = json.loads(fired.stdout)
            hso = payload["hookSpecificOutput"]
            assert hso["hookEventName"] == "PostToolUse"
            assert "batch" in hso["additionalContext"].lower()
        else:
            assert fired.exit_code == 2
            assert fired.stdout is None

    @pytest.mark.parametrize("host", ["claude-code", "codex"])
    def test_counter_resets_after_firing(self, clock: _Clock, host: str) -> None:
        gap = _BATCH_WINDOW_SECONDS + 1.0
        for _ in range(_NUDGE_THRESHOLD):
            last = self._edit(host=host)
            clock.advance(gap)
        assert last.exit_code == (0 if host == "claude-code" else 2)
        # The very next unbatched edit does not re-nudge — the once-per-session
        # ``nudged`` latch is now set, so every subsequent edit in this session
        # passes through silently regardless of how the run counter evolves.
        passthrough = self._edit(host=host)
        assert passthrough.exit_code == 0
        assert passthrough.stdout is None

    def test_batched_edits_never_nudge(self, clock: _Clock) -> None:
        # Fires within the batch window (sub-second) simulate parallel edits.
        for _ in range(_NUDGE_THRESHOLD + 2):
            result = self._edit()
            clock.advance(_BATCH_WINDOW_SECONDS / 4)
            assert result.exit_code == 0
            assert result.stdout is None

    def test_multiedit_never_nudges_and_resets_run(self, clock: _Clock) -> None:
        gap = _BATCH_WINDOW_SECONDS + 1.0
        # Build up a run just below the threshold.
        for _ in range(_NUDGE_THRESHOLD - 1):
            self._edit()
            clock.advance(gap)
        # A MultiEdit passes through and clears the run.
        me = handle(_event({"tool_name": "MultiEdit", "session_id": "s1"}))
        assert me.exit_code == 0
        assert me.stdout is None
        clock.advance(gap)
        # Because the run was reset, the next edit does not immediately nudge.
        result = self._edit()
        assert result.exit_code == 0
        assert result.stdout is None

    def test_session_change_resets_run(self, clock: _Clock) -> None:
        gap = _BATCH_WINDOW_SECONDS + 1.0
        for _ in range(_NUDGE_THRESHOLD - 1):
            self._edit(session="s1")
            clock.advance(gap)
        # Switching sessions resets the counter, so this does not nudge even
        # though the raw count would otherwise reach the threshold.
        result = self._edit(session="s2")
        assert result.exit_code == 0
        assert result.stdout is None

    @pytest.mark.parametrize("host", ["claude-code", "codex"])
    def test_nudge_only_fires_once_per_session(self, clock: _Clock, host: str) -> None:
        """Once the nudge fires in a session, every subsequent unbatched edit passes through silently."""
        gap = _BATCH_WINDOW_SECONDS + 1.0
        # Reach the threshold once.
        results = []
        for _ in range(_NUDGE_THRESHOLD):
            results.append(self._edit(host=host))
            clock.advance(gap)
        assert results[-1].exit_code == (0 if host == "claude-code" else 2)
        # Now drive many more unbatched edits through — none should re-nudge.
        post_fire = []
        for _ in range(_NUDGE_THRESHOLD * 4):
            post_fire.append(self._edit(host=host))
            clock.advance(gap)
        assert all(r.exit_code == 0 and r.stdout is None for r in post_fire), (
            "once-per-session latch leaked: a later unbatched edit re-nudged"
        )

    def test_nudge_only_fires_once_even_across_batched_resets(self, clock: _Clock) -> None:
        """Batched edits / MultiEdit after the first nudge do not re-arm the hook."""
        gap = _BATCH_WINDOW_SECONDS + 1.0
        # Fire the nudge once.
        for _ in range(_NUDGE_THRESHOLD):
            self._edit()
            clock.advance(gap)
        # Now do a MultiEdit (which would normally reset the run counter)...
        me = handle(_event({"tool_name": "MultiEdit", "session_id": "s1"}))
        clock.advance(gap)
        assert me.exit_code == 0
        assert me.stdout is None
        # ...then a fast pair of batched edits (within the batch window)...
        for _ in range(2):
            self._edit()
            clock.advance(_BATCH_WINDOW_SECONDS / 4)
        # ...then a long unbatched stretch. None of these should re-nudge:
        # the latch is sticky for the lifetime of the session_id.
        for _ in range(_NUDGE_THRESHOLD + 2):
            result = self._edit()
            clock.advance(gap)
            assert result.exit_code == 0, "latch cleared by a later tool call"
            assert result.stdout is None

    @pytest.mark.parametrize("host", ["claude-code", "codex"])
    def test_session_change_rearms_nudge(self, clock: _Clock, host: str) -> None:
        """Switching session_id clears the nudged latch and re-arms the hook for the new session."""
        gap = _BATCH_WINDOW_SECONDS + 1.0
        # Fire the nudge once in session s1.
        for _ in range(_NUDGE_THRESHOLD):
            self._edit(session="s1", host=host)
            clock.advance(gap)
        # New session — should be able to nudge again.
        results = []
        for _ in range(_NUDGE_THRESHOLD):
            results.append(self._edit(session="s2", host=host))
            clock.advance(gap)
        assert all(r.exit_code == 0 and r.stdout is None for r in results[:-1])
        assert results[-1].exit_code == (0 if host == "claude-code" else 2)

    def test_state_records_nudged_flag(self, clock: _Clock, tmp_path) -> None:
        """Persisted state includes ``nudged`` so a process restart inherits the latch."""
        from little_loops.hooks.edit_batch_nudge import _STATE_FILENAME, _load_state

        gap = _BATCH_WINDOW_SECONDS + 1.0
        for _ in range(_NUDGE_THRESHOLD):
            self._edit()
            clock.advance(gap)
        state = _load_state(tmp_path / ".ll" / _STATE_FILENAME)
        assert state.get("session_id") == "s1"
        assert state.get("nudged") is True
        assert state.get("run") == 0

    def test_state_omits_nudged_until_first_fire(self, clock: _Clock, tmp_path) -> None:
        """Pre-fire state records ``nudged: False`` so the latch is explicit, not implicit."""
        from little_loops.hooks.edit_batch_nudge import _STATE_FILENAME, _load_state

        gap = _BATCH_WINDOW_SECONDS + 1.0
        # One unbatched edit — well below threshold.
        self._edit()
        clock.advance(gap)
        state = _load_state(tmp_path / ".ll" / _STATE_FILENAME)
        assert state.get("nudged") is False
        assert state.get("run") == 1


class TestNoStrayDirCreation:
    """ENH-2927: the hook must never create ``.ll/`` outside a resolved project."""

    def test_no_project_and_no_claude_project_dir_is_noop(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """cwd outside any project, no CLAUDE_PROJECT_DIR: exit 0, nothing created."""
        outside = tmp_path / "not-a-project"
        outside.mkdir()
        monkeypatch.chdir(outside)
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.setattr(edit_batch_nudge, "_now", _Clock())
        # Enough unbatched edits to hit the nudge threshold if state were writable.
        result = None
        for _ in range(_NUDGE_THRESHOLD):
            result = handle(_event({"tool_name": "Edit", "session_id": "s1"}, cwd=str(outside)))
        assert result is not None
        assert result.exit_code == 0
        assert result.feedback is None
        assert result.stdout is None
        assert not (outside / ".ll").exists()

    def test_claude_project_dir_anchors_state_there(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """CLAUDE_PROJECT_DIR wins over cwd — state lands at that root, not cwd."""
        from little_loops.hooks.edit_batch_nudge import _STATE_FILENAME

        project_root = tmp_path / "the-project"
        project_root.mkdir()
        subdir = project_root / "sub"
        subdir.mkdir()
        monkeypatch.chdir(subdir)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project_root))
        monkeypatch.setattr(edit_batch_nudge, "_now", _Clock())
        result = handle(_event({"tool_name": "Edit", "session_id": "s1"}, cwd=str(subdir)))
        assert result.exit_code == 0
        assert result.stdout is None
        assert (project_root / ".ll" / _STATE_FILENAME).is_file()
        assert not (subdir / ".ll").exists()


class TestRobustness:
    def test_state_write_failure_passes_through(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        (tmp_path / ".ll").mkdir()
        monkeypatch.setattr(edit_batch_nudge, "_now", _Clock())

        def _boom(*_a, **_k):
            raise OSError("disk full")

        # Persisting must never surface as an exception from the handler.
        monkeypatch.setattr(edit_batch_nudge, "atomic_write_json", _boom)
        result = handle(_event({"tool_name": "Edit", "session_id": "s1"}))
        assert result.exit_code == 0
        assert result.feedback is None
        assert result.stdout is None


def _write_config(root, cfg: dict) -> None:
    (root / ".ll").mkdir(exist_ok=True)
    (root / ".ll" / "ll-config.json").write_text(json.dumps({"hooks": {"edit_batch_nudge": cfg}}))


def _write_raw_config(root, data) -> None:
    (root / ".ll").mkdir(exist_ok=True)
    (root / ".ll" / "ll-config.json").write_text(json.dumps(data))


def _write_local(root, frontmatter: str) -> None:
    (root / ".ll").mkdir(exist_ok=True)
    (root / ".ll" / "ll.local.md").write_text(f"---\n{frontmatter}\n---\n\n# Local\n")


def _edit(session: str = "s1", **kw):
    return handle(_event({"tool_name": "Edit", "session_id": session}, **kw))


def _unbatched_run(clock: _Clock, n: int, gap: float):
    """Fire *n* edits *gap* seconds apart; return all results."""
    results = []
    for _ in range(n):
        results.append(_edit())
        clock.advance(gap)
    return results


class TestConfigSettings:
    """ENH-3645: ``hooks.edit_batch_nudge`` config toggle and tunables."""

    def test_disabled_is_silent_and_writes_no_state(self, clock: _Clock, tmp_path) -> None:
        from little_loops.hooks.edit_batch_nudge import _STATE_FILENAME

        _write_config(tmp_path, {"enabled": False})
        results = _unbatched_run(clock, _NUDGE_THRESHOLD + 1, _BATCH_WINDOW_SECONDS + 1.0)
        assert all(r.exit_code == 0 and r.stdout is None and r.feedback is None for r in results)
        assert not (tmp_path / ".ll" / _STATE_FILENAME).exists()

    def test_enabled_true_behaves_as_default(self, clock: _Clock, tmp_path) -> None:
        _write_config(tmp_path, {"enabled": True})
        results = _unbatched_run(clock, _NUDGE_THRESHOLD, _BATCH_WINDOW_SECONDS + 1.0)
        assert results[-1].stdout is not None

    @pytest.mark.parametrize("threshold", [2, 2.0])
    def test_custom_threshold(self, clock: _Clock, tmp_path, threshold) -> None:
        _write_config(tmp_path, {"threshold": threshold})
        results = _unbatched_run(clock, 2, _BATCH_WINDOW_SECONDS + 1.0)
        assert results[0].stdout is None
        assert results[1].stdout is not None

    def test_custom_window(self, clock: _Clock, tmp_path) -> None:
        # A 10s window makes 5s-apart edits count as batched: never nudges.
        _write_config(tmp_path, {"window_seconds": 10})
        results = _unbatched_run(clock, _NUDGE_THRESHOLD + 2, 5.0)
        assert all(r.stdout is None for r in results)

    @pytest.mark.parametrize(
        "cfg",
        [
            {"threshold": True},
            {"threshold": "2"},
            {"threshold": 0},
            {"threshold": 2.5},
            {"threshold": None},
            {"window_seconds": True},
            {"window_seconds": "9"},
            {"window_seconds": -1},
            {"enabled": "false"},
            {"enabled": 0},
        ],
    )
    def test_invalid_values_fall_back_to_defaults(self, clock: _Clock, tmp_path, cfg) -> None:
        _write_config(tmp_path, cfg)
        results = _unbatched_run(clock, _NUDGE_THRESHOLD, _BATCH_WINDOW_SECONDS + 1.0)
        assert all(r.stdout is None for r in results[:-1])
        assert results[-1].stdout is not None

    def test_local_null_under_absent_ancestor_keeps_effective_defaults(
        self, clock: _Clock, tmp_path
    ) -> None:
        """FEAT-3681: a null reset under an absent ancestor falls back to defaults."""
        _write_raw_config(tmp_path, {})
        _write_local(tmp_path, "hooks:\n  edit_batch_nudge:\n    threshold: null\n    enabled: null")
        results = _unbatched_run(clock, _NUDGE_THRESHOLD, _BATCH_WINDOW_SECONDS + 1.0)
        assert all(r.stdout is None for r in results[:-1])
        assert results[-1].stdout is not None

    def test_non_finite_window_falls_back(self, clock: _Clock, tmp_path) -> None:
        # json.dumps emits the non-standard ``Infinity`` token, which json.loads accepts.
        (tmp_path / ".ll").mkdir(exist_ok=True)
        (tmp_path / ".ll" / "ll-config.json").write_text(
            '{"hooks": {"edit_batch_nudge": {"window_seconds": Infinity}}}'
        )
        results = _unbatched_run(clock, _NUDGE_THRESHOLD, _BATCH_WINDOW_SECONDS + 1.0)
        assert results[-1].stdout is not None

    def test_invalid_key_does_not_discard_valid_sibling(self, clock: _Clock, tmp_path) -> None:
        _write_config(tmp_path, {"threshold": "bad", "window_seconds": 10})
        # Window 10 applies (5s gaps batched) even though threshold fell back.
        results = _unbatched_run(clock, _NUDGE_THRESHOLD + 2, 5.0)
        assert all(r.stdout is None for r in results)

    @pytest.mark.parametrize(
        "data",
        [
            {"hooks": []},
            {"hooks": {"edit_batch_nudge": True}},
            {"hooks": {"edit_batch_nudge": "off"}},
            [],
        ],
    )
    def test_malformed_shapes_yield_defaults_and_stay_enabled(
        self, clock: _Clock, tmp_path, data
    ) -> None:
        _write_raw_config(tmp_path, data)
        results = _unbatched_run(clock, _NUDGE_THRESHOLD, _BATCH_WINDOW_SECONDS + 1.0)
        assert results[-1].stdout is not None

    def test_malformed_config_file_yields_defaults(self, clock: _Clock, tmp_path) -> None:
        (tmp_path / ".ll" / "ll-config.json").write_text("{not json")
        results = _unbatched_run(clock, _NUDGE_THRESHOLD, _BATCH_WINDOW_SECONDS + 1.0)
        assert results[-1].stdout is not None

    def test_local_override_disables(self, clock: _Clock, tmp_path) -> None:
        from little_loops.hooks.edit_batch_nudge import _STATE_FILENAME

        _write_config(tmp_path, {"enabled": True})
        _write_local(tmp_path, "hooks:\n  edit_batch_nudge:\n    enabled: false")
        results = _unbatched_run(clock, _NUDGE_THRESHOLD, _BATCH_WINDOW_SECONDS + 1.0)
        assert all(r.stdout is None for r in results)
        assert not (tmp_path / ".ll" / _STATE_FILENAME).exists()

    def test_local_null_removes_base_disable(self, clock: _Clock, tmp_path) -> None:
        _write_config(tmp_path, {"enabled": False})
        _write_local(tmp_path, "hooks:\n  edit_batch_nudge:\n    enabled: null")
        results = _unbatched_run(clock, _NUDGE_THRESHOLD, _BATCH_WINDOW_SECONDS + 1.0)
        assert results[-1].stdout is not None

    def test_local_override_without_base_config(self, clock: _Clock, tmp_path) -> None:
        _write_local(tmp_path, "hooks:\n  edit_batch_nudge:\n    threshold: 2")
        results = _unbatched_run(clock, 2, _BATCH_WINDOW_SECONDS + 1.0)
        assert results[1].stdout is not None

    def test_config_under_claude_project_dir_honored_from_subdir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        from little_loops.hooks.edit_batch_nudge import _STATE_FILENAME

        project_root = tmp_path / "the-project"
        subdir = project_root / "sub"
        subdir.mkdir(parents=True)
        _write_config(project_root, {"enabled": False})
        monkeypatch.chdir(subdir)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project_root))
        monkeypatch.setattr(edit_batch_nudge, "_now", _Clock())
        for _ in range(_NUDGE_THRESHOLD):
            result = _edit(cwd=str(subdir))
            assert result.stdout is None
        assert not (project_root / ".ll" / _STATE_FILENAME).exists()
        assert not (subdir / ".ll").exists()

    def test_disabled_never_creates_ll_dir(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        """No resolvable project: silent no-op, and no ``.ll/`` is fabricated."""
        outside = tmp_path / "not-a-project"
        outside.mkdir()
        monkeypatch.chdir(outside)
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.setattr(edit_batch_nudge, "_now", _Clock())
        result = _edit(cwd=str(outside))
        assert result.exit_code == 0
        assert not (outside / ".ll").exists()

    def test_disabled_with_claude_project_dir_lacking_ll_creates_nothing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        project_root = tmp_path / "bare"
        project_root.mkdir()
        # A root-level config (no ``.ll/`` dir) disables the hook; the state
        # step — the only one that mkdirs — must never run.
        (project_root / "ll-config.json").write_text(
            json.dumps({"hooks": {"edit_batch_nudge": {"enabled": False}}})
        )
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project_root))
        monkeypatch.setattr(edit_batch_nudge, "_now", _Clock())
        assert _edit(cwd=str(project_root)).exit_code == 0
        assert not (project_root / ".ll").exists()
