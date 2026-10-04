"""Absolute monotonic deadline shared by every read on a strict read-only connection (ENH-3720).

A :class:`Deadline` is an immutable expiry on the :func:`time.monotonic` clock. It is passed to
``connect_readonly(..., deadline=...)``; the opted-in connection then spends one budget across
opening, remote access verification and every later read statement, instead of a fresh
allowance per request or statement. This module opens no database.

The deadline is not a universal hard wall-time guarantee. Synchronous DNS resolution, JSON
encoding/decoding, SQLite user-defined functions and filesystem stalls are not preempted, and
local cancellation runs at SQLite progress-handler granularity (every
:data:`PROGRESS_INTERVAL` virtual-machine instructions). Expiry is rechecked before further I/O
and before reporting success after synchronous work.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

# SQLite VM instructions between progress-handler calls on a deadline-bound connection.
PROGRESS_INTERVAL = 1000


def now() -> float:
    """The clock every deadline check reads (``time.monotonic``); one seam for fake clocks."""
    return time.monotonic()


@dataclass(frozen=True)
class Deadline:
    """An absolute expiry, in seconds on the monotonic clock."""

    expires_at: float

    @classmethod
    def after(cls, seconds: float) -> Deadline:
        """A deadline *seconds* from now (a non-positive value is already expired)."""
        return cls(now() + seconds)

    def remaining(self) -> float:
        """Seconds left, floored at zero."""
        return max(0.0, self.expires_at - now())

    def expired(self) -> bool:
        return now() >= self.expires_at


__all__ = ["PROGRESS_INTERVAL", "Deadline", "now"]
