"""Shared internals for the history_reader package (ENH-2775 split from the
former flat ``history_reader.py``).

Holds the read-only-connection/row-mapping helpers and cross-domain constants
every query submodule depends on: ``_connect_readonly`` (64 call sites in the
former flat module), ``_row_to_dataclass``, ``_stale_cutoff``,
``STALE_DAYS_DEFAULT``, and the fixed-name ``logger`` asserted by
``test_verdict_grammar_regression.py::test_high_confidence_abstention_warns``
(must stay ``logging.getLogger("little_loops.history_reader")``, never
``getLogger(__name__)``, so the 67 existing ``"history_reader: <func> query
failed"`` warnings keep the same logger name after the split).

Also re-imports the small set of cross-package names (``session_store``'s
``DEFAULT_DB_PATH``/``ensure_db``/``fts_phrase``/``normalize_issue_id`` and
``fsm.verdicts.CANNOT_JUDGE``) that most query submodules need, so every
sibling can satisfy the package's DAG rule (import from ``_base``/``models``
only, never sibling-to-sibling) with a single import line instead of each
reaching into ``little_loops.session_store`` directly.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from little_loops.fsm.verdicts import CANNOT_JUDGE
from little_loops.session_store import (
    DEFAULT_DB_PATH,
    ensure_db,
    fts_phrase,
    normalize_issue_id,
)

__all__ = [
    "CANNOT_JUDGE",
    "DEFAULT_DB_PATH",
    "STALE_DAYS_DEFAULT",
    "ensure_db",
    "fts_phrase",
    "logger",
    "normalize_issue_id",
    "_connect_readonly",
    "_row_to_dataclass",
    "_stale_cutoff",
]

logger = logging.getLogger("little_loops.history_reader")

STALE_DAYS_DEFAULT = 30


def _stale_cutoff(days: int) -> str:
    """ISO-8601 timestamp *days* ago."""
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect_readonly(db_path: Path) -> sqlite3.Connection | None:
    """Open a read-only connection, or return None on failure.

    Thin compatibility wrapper (ENH-3525) over
    :func:`little_loops.session_store.backend.open_history_readonly` with
    ``ensure=True`` — same signature and same "return None on failure"
    contract as before, so this module's ~70 callers are unchanged. Resolves
    *db_path* exactly once and migrates+opens the *same* resolved path
    (fixes the latent bug where the old inline implementation called
    `ensure_db(db_path)`, discarded its resolved return value, and reopened
    the unresolved `db_path` argument — silently divergent for a
    default-shaped path). Still honors the BUG-3181 no-re-resolve contract
    for an already-root-anchored absolute path, since `resolve_history_db()`
    only re-resolves a default-shaped argument.
    """
    from little_loops.session_store.backend import HistoryError, open_history_readonly

    try:
        return open_history_readonly(db_path, ensure=True)
    except HistoryError:
        logger.warning("history_reader: could not open %s read-only", db_path, exc_info=True)
        return None


def _row_to_dataclass(row: sqlite3.Row, dc: type[Any]) -> Any:
    """Map a sqlite3.Row to a dataclass instance, catching extra/unknown keys."""
    field_names = {f.name for f in dc.__dataclass_fields__.values()}
    kwargs = {k: row[k] for k in field_names if k in row.keys()}
    return dc(**kwargs)
