"""Stall detector for repeated `(state, exit_code, verdict)` triples.

Detects deterministic FSM stalls where the same state produces the
same exit code and verdict across consecutive iterations, allowing
loops to abort or route to a recovery state instead of burning their
iteration budget on a stuck transition.

Treats timeout-driven errors identically to deterministic "no"
verdicts: `(state, exit_code=124, verdict="error")` is a stall just
as much as `(state, exit_code=124, verdict="no")` — see BUG-1640.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Stall:
    """A detected stall: the repeating triple and its consecutive count."""

    triple: tuple[str, int, str]
    count: int


class StallDetector:
    """Track consecutive identical `(state, exit_code, verdict)` triples.

    `record()` appends a triple per FSM transition. `check()` returns a
    `Stall` when the last `window` recorded triples are all identical,
    else None.
    """

    def __init__(self, window: int) -> None:
        if window < 1:
            raise ValueError(f"window must be >= 1, got {window}")
        self._window: int = window
        self._recent: deque[tuple[str, int, str]] = deque(maxlen=window)

    def record(self, state: str, exit_code: int, verdict: str) -> None:
        """Append a transition triple to the rolling window."""
        self._recent.append((state, exit_code, verdict))

    def check(self) -> Stall | None:
        """Return a Stall if the last `window` triples are all identical."""
        if len(self._recent) < self._window:
            return None
        first = self._recent[0]
        for triple in self._recent:
            if triple != first:
                return None
        return Stall(triple=first, count=self._window)

    def reset(self) -> None:
        """Clear the rolling window (used on streak break by external callers)."""
        self._recent.clear()
