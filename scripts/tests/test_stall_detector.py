"""Unit tests for StallDetector (FEAT-1637)."""

from __future__ import annotations

import dataclasses

import pytest

from little_loops.fsm.stall_detector import Stall, StallDetector


class TestStallDetector:
    def test_check_returns_none_below_window(self) -> None:
        d = StallDetector(window=3)
        d.record("A", 0, "no")
        d.record("A", 0, "no")
        assert d.check() is None

    def test_check_fires_on_identical_window(self) -> None:
        d = StallDetector(window=3)
        d.record("check_semantic_vision", 124, "no")
        d.record("check_semantic_vision", 124, "no")
        d.record("check_semantic_vision", 124, "no")
        stall = d.check()
        assert stall is not None
        assert stall.triple == ("check_semantic_vision", 124, "no")
        assert stall.count == 3

    def test_check_returns_none_when_streak_broken(self) -> None:
        d = StallDetector(window=3)
        d.record("A", 124, "no")
        d.record("A", 124, "no")
        d.record("B", 0, "yes")
        assert d.check() is None

    def test_streak_can_rebuild_after_break(self) -> None:
        d = StallDetector(window=3)
        d.record("A", 124, "no")
        d.record("A", 124, "no")
        d.record("B", 0, "yes")
        assert d.check() is None
        d.record("B", 0, "yes")
        d.record("B", 0, "yes")
        stall = d.check()
        assert stall is not None
        assert stall.triple == ("B", 0, "yes")
        assert stall.count == 3

    def test_window_one_fires_immediately(self) -> None:
        d = StallDetector(window=1)
        d.record("X", 1, "no")
        stall = d.check()
        assert stall is not None
        assert stall.count == 1

    def test_window_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            StallDetector(window=0)
        with pytest.raises(ValueError):
            StallDetector(window=-1)

    def test_reset_clears_window(self) -> None:
        d = StallDetector(window=2)
        d.record("A", 1, "no")
        d.record("A", 1, "no")
        assert d.check() is not None
        d.reset()
        assert d.check() is None
        d.record("A", 1, "no")
        assert d.check() is None

    def test_timeout_error_triple_treated_as_stall(self) -> None:
        # Per BUG-1640 cross-reference: exit_code=124 with verdict="error"
        # should stall just like the deterministic-no case.
        d = StallDetector(window=3)
        d.record("slow_state", 124, "error")
        d.record("slow_state", 124, "error")
        d.record("slow_state", 124, "error")
        stall = d.check()
        assert stall is not None
        assert stall.triple == ("slow_state", 124, "error")

    def test_distinct_exit_codes_do_not_match(self) -> None:
        d = StallDetector(window=2)
        d.record("A", 1, "no")
        d.record("A", 2, "no")
        assert d.check() is None

    def test_stall_dataclass_is_frozen(self) -> None:
        s = Stall(triple=("A", 0, "no"), count=3)
        with pytest.raises(dataclasses.FrozenInstanceError):
            s.count = 4  # type: ignore[misc]
