"""Shared gate utilities for learning-test staleness checks (ENH-2208).

Exposes ``is_record_stale()`` as a standalone importable helper consumed by
the discoverability gate hook and downstream sprint/release gates
(ENH-2209, ENH-2210, ENH-2214, ENH-2217).
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.learning_tests import LearnTestRecord


def is_record_stale(record: LearnTestRecord, stale_after_days: int) -> bool:
    """Return True if the record's proof date exceeds the staleness threshold.

    Args:
        record: A LearnTestRecord with a ``date`` field (ISO 8601: YYYY-MM-DD).
        stale_after_days: Age threshold in days. Clamped to minimum 1 to
            prevent ``stale_after_days=0`` from being a footgun that passes
            all records whose date is exactly today.

    Returns:
        True if age in days exceeds the threshold; False if fresh or unparseable.
    """
    threshold = max(1, stale_after_days)
    try:
        record_date = datetime.date.fromisoformat(record.date)
    except (ValueError, TypeError, AttributeError):
        return False
    age_days = (datetime.date.today() - record_date).days
    return age_days > threshold
