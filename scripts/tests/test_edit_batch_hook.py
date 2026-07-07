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

import pytest

from little_loops.hooks import edit_batch_nudge
from little_loops.hooks.edit_batch_nudge import (
    _BATCH_WINDOW_SECONDS,
    _NUDGE_THRESHOLD,
    handle,
)
from little_loops.hooks.types import LLHookEvent


def _event(payload: dict | None = None, *, cwd: str | None = None) -> LLHookEvent:
    return LLHookEvent(
        host="claude-code",
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
    """Isolate the state file to ``tmp_path`` and give the handler a fake clock."""
    monkeypatch.chdir(tmp_path)
    c = _Clock()
    monkeypatch.setattr(edit_batch_nudge, "_now", c)
    return c


class TestPassThrough:
    def test_non_edit_tool_passes_through(self, clock: _Clock) -> None:
        result = handle(_event({"tool_name": "Bash", "tool_input": {"command": "ls"}}))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_empty_payload_passes_through(self, clock: _Clock) -> None:
        result = handle(_event())
        assert result.exit_code == 0
        assert result.feedback is None

    def test_read_tool_passes_through(self, clock: _Clock) -> None:
        result = handle(_event({"tool_name": "Read"}))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_handler_does_not_mutate_payload(self, clock: _Clock) -> None:
        payload = {"tool_name": "Edit", "session_id": "s1"}
        handle(_event(payload))
        assert payload == {"tool_name": "Edit", "session_id": "s1"}


class TestStatefulNudge:
    def _edit(self, session: str = "s1"):
        return handle(_event({"tool_name": "Edit", "session_id": session}))

    def test_single_edit_does_not_nudge(self, clock: _Clock) -> None:
        result = self._edit()
        assert result.exit_code == 0
        assert result.feedback is None

    def test_run_of_unbatched_edits_nudges_at_threshold(self, clock: _Clock) -> None:
        gap = _BATCH_WINDOW_SECONDS + 1.0
        results = []
        for _ in range(_NUDGE_THRESHOLD):
            results.append(self._edit())
            clock.advance(gap)
        # Only the threshold-th edit nudges.
        assert all(r.exit_code == 0 for r in results[:-1])
        assert results[-1].exit_code == 2
        assert "batch" in (results[-1].feedback or "").lower()

    def test_counter_resets_after_firing(self, clock: _Clock) -> None:
        gap = _BATCH_WINDOW_SECONDS + 1.0
        for _ in range(_NUDGE_THRESHOLD):
            last = self._edit()
            clock.advance(gap)
        assert last.exit_code == 2
        # The very next unbatched edit does not re-nudge — the once-per-session
        # ``nudged`` latch is now set, so every subsequent edit in this session
        # passes through silently regardless of how the run counter evolves.
        assert self._edit().exit_code == 0

    def test_batched_edits_never_nudge(self, clock: _Clock) -> None:
        # Fires within the batch window (sub-second) simulate parallel edits.
        for _ in range(_NUDGE_THRESHOLD + 2):
            result = self._edit()
            clock.advance(_BATCH_WINDOW_SECONDS / 4)
            assert result.exit_code == 0

    def test_multiedit_never_nudges_and_resets_run(self, clock: _Clock) -> None:
        gap = _BATCH_WINDOW_SECONDS + 1.0
        # Build up a run just below the threshold.
        for _ in range(_NUDGE_THRESHOLD - 1):
            self._edit()
            clock.advance(gap)
        # A MultiEdit passes through and clears the run.
        me = handle(_event({"tool_name": "MultiEdit", "session_id": "s1"}))
        assert me.exit_code == 0
        clock.advance(gap)
        # Because the run was reset, the next edit does not immediately nudge.
        assert self._edit().exit_code == 0

    def test_session_change_resets_run(self, clock: _Clock) -> None:
        gap = _BATCH_WINDOW_SECONDS + 1.0
        for _ in range(_NUDGE_THRESHOLD - 1):
            self._edit(session="s1")
            clock.advance(gap)
        # Switching sessions resets the counter, so this does not nudge even
        # though the raw count would otherwise reach the threshold.
        result = self._edit(session="s2")
        assert result.exit_code == 0

    def test_nudge_only_fires_once_per_session(self, clock: _Clock) -> None:
        """Once the nudge fires in a session, every subsequent unbatched edit passes through silently."""
        gap = _BATCH_WINDOW_SECONDS + 1.0
        # Reach the threshold once.
        results = []
        for _ in range(_NUDGE_THRESHOLD):
            results.append(self._edit())
            clock.advance(gap)
        assert results[-1].exit_code == 2
        # Now drive many more unbatched edits through — none should re-nudge.
        post_fire = []
        for _ in range(_NUDGE_THRESHOLD * 4):
            post_fire.append(self._edit())
            clock.advance(gap)
        assert all(r.exit_code == 0 for r in post_fire), (
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

    def test_session_change_rearms_nudge(self, clock: _Clock) -> None:
        """Switching session_id clears the nudged latch and re-arms the hook for the new session."""
        gap = _BATCH_WINDOW_SECONDS + 1.0
        # Fire the nudge once in session s1.
        for _ in range(_NUDGE_THRESHOLD):
            self._edit(session="s1")
            clock.advance(gap)
        # New session — should be able to nudge again.
        results = []
        for _ in range(_NUDGE_THRESHOLD):
            results.append(self._edit(session="s2"))
            clock.advance(gap)
        assert all(r.exit_code == 0 for r in results[:-1])
        assert results[-1].exit_code == 2

    def test_state_records_nudged_flag(self, clock: _Clock) -> None:
        """Persisted state includes ``nudged`` so a process restart inherits the latch."""
        from little_loops.hooks.edit_batch_nudge import _load_state

        gap = _BATCH_WINDOW_SECONDS + 1.0
        for _ in range(_NUDGE_THRESHOLD):
            self._edit()
            clock.advance(gap)
        state = _load_state()
        assert state.get("session_id") == "s1"
        assert state.get("nudged") is True
        assert state.get("run") == 0

    def test_state_omits_nudged_until_first_fire(self, clock: _Clock) -> None:
        """Pre-fire state records ``nudged: False`` so the latch is explicit, not implicit."""
        from little_loops.hooks.edit_batch_nudge import _load_state

        gap = _BATCH_WINDOW_SECONDS + 1.0
        # One unbatched edit — well below threshold.
        self._edit()
        clock.advance(gap)
        state = _load_state()
        assert state.get("nudged") is False
        assert state.get("run") == 1


class TestRobustness:
    def test_state_write_failure_passes_through(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(edit_batch_nudge, "_now", _Clock())

        def _boom(*_a, **_k):
            raise OSError("disk full")

        # Persisting must never surface as an exception from the handler.
        monkeypatch.setattr(edit_batch_nudge, "atomic_write_json", _boom)
        result = handle(_event({"tool_name": "Edit", "session_id": "s1"}))
        assert result.exit_code == 0
        assert result.feedback is None
