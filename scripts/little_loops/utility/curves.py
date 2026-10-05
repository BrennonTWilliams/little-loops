"""Legacy response curves behind ``ll-loop next-loop`` scoring.

Pure functions: no filesystem, database, clock, or network access. The caller
injects the instant used for recency. The formulas (and their quirks) are the
pre-extraction ones and are preserved exactly: frequency is **not** capped at 1,
and recency can exceed 1 for future timestamps.
"""

from __future__ import annotations

import math
from datetime import datetime

__all__ = ["frequency_score", "recency_score"]

_FREQUENCY_REFERENCE_RUNS = 50  # log-scale normalisation reference (not a cap)
_DECAY_HALF_LIFE_DAYS = 7.0  # recency decay: halves every 7 days


def frequency_score(run_count: int) -> float:
    """Return ``log1p(run_count) / log1p(50)`` for a nonnegative integer count.

    The result is uncapped: counts above 50 score above 1.

    Raises:
        ValueError: *run_count* is not a nonnegative ``int`` (booleans are
            rejected) or is too large for ``log1p``'s float arithmetic.
    """
    if isinstance(run_count, bool) or not isinstance(run_count, int):
        raise ValueError(f"run_count must be a nonnegative integer, got {run_count!r}")
    if run_count < 0:
        raise ValueError(f"run_count must be nonnegative, got {run_count}")
    if run_count == 0:
        return 0.0
    try:
        return math.log1p(run_count) / math.log1p(_FREQUENCY_REFERENCE_RUNS)
    except OverflowError as exc:
        raise ValueError("run_count is too large to score") from exc


def recency_score(started_at: str | None, *, as_of: datetime) -> float:
    """Exponential decay (seven-day half-life) from *started_at* to *as_of*.

    A missing, malformed, or timezone-naive *started_at* yields ``0.0``. A future
    timestamp yields a value above 1; an extreme one raises ``OverflowError``
    from ``math.exp`` (legacy behaviour, intentionally unchanged).

    Raises:
        ValueError: *as_of* is not a timezone-aware ``datetime``. This is checked
            before any *started_at* fallback so a caller clock error never
            becomes zero recency.
    """
    if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError(f"as_of must be a timezone-aware datetime, got {as_of!r}")
    if not started_at:
        return 0.0
    try:
        ts = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        days = (as_of - ts).total_seconds() / 86400.0
        return math.exp(-days * math.log(2) / _DECAY_HALF_LIFE_DAYS)
    except (ValueError, TypeError):
        return 0.0
