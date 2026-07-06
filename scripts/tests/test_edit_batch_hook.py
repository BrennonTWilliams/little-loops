"""Python-direct tests for ``little_loops.hooks.edit_batch_nudge.handle`` (FEAT-2470).

The handler is stateful: it tracks consecutive *unbatched* single edits in
``.ll/ll-edit-batch-state.json`` and only nudges (``exit_code=2``) once a run
reaches ``_NUDGE_THRESHOLD``. Batched edits (fires within
``_BATCH_WINDOW_SECONDS``) and ``MultiEdit`` reset the run; every non-edit tool
passes through with exit 0 and no feedback. Tests isolate state via
``monkeypatch.chdir(tmp_path)`` and drive the clock via ``_now``.
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
        # The very next unbatched edit starts a fresh run and does not re-nudge.
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
