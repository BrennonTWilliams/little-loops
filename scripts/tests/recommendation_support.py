"""Shared fixtures/helpers for the FEAT-3711 ``recommendation_events`` tests.

Real stores come from ``ensure_db`` (the shipped migration), never hand-written DDL, except
the deliberate lookalike builders that exist to violate one part of the consumed shape.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from little_loops.next_arena.actions import (
    FINGERPRINT_SCOPE_V1,
    LoopActionSpec,
    action_fingerprint,
    action_key,
    slash_spec_for,
    spec_to_dict,
)
from little_loops.next_arena.recording import project_key_for
from little_loops.session_store import RECOMMENDATION_EVENT_COLUMNS, ensure_db
from little_loops.session_store.backend import LocalTarget

NOW = datetime(2026, 10, 8, 9, 30, 0, tzinfo=UTC)
LATER = datetime(2026, 10, 8, 9, 31, 0, 123456, tzinfo=UTC)

#: DDL of the migration with exactly one part changed, for the lookalike fixtures.
_BASE_COLUMNS = """
    id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
    rec_id {rec} NOT NULL, kind {kind} NOT NULL, ts TEXT NOT NULL,
    project_key {pk} NOT NULL, session_id TEXT, invocation_id TEXT NOT NULL,
    as_of TEXT NOT NULL, rank INTEGER NOT NULL, action_type TEXT NOT NULL,
    action_key TEXT NOT NULL, action_fingerprint TEXT NOT NULL, target TEXT NOT NULL,
    target_key TEXT NOT NULL, action_spec TEXT NOT NULL, requested_top INTEGER,
    requested_types TEXT NOT NULL"""


def make_real_store(path: Path) -> Path:
    """A fully migrated store (the current ``SCHEMA_VERSION``) at *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_db(LocalTarget(path))  # typed target: never redirected by LL_HISTORY_DB/config
    return path


def replace_table(
    path: Path,
    *,
    ddl_tail: str,
    rec: str = "TEXT",
    kind: str = "TEXT",
    pk: str = "TEXT",
    extra: tuple[str, ...] = (),
) -> None:
    """Swap the real ``recommendation_events`` for a variant (*ddl_tail* = constraints/indexes)."""
    conn = sqlite3.connect(path)
    try:
        conn.execute("DROP TABLE recommendation_events")
        columns = _BASE_COLUMNS.format(rec=rec, kind=kind, pk=pk)
        tail = f", {ddl_tail}" if ddl_tail else ""
        conn.execute(f"CREATE TABLE recommendation_events ({columns}{tail})")
        for statement in extra:
            conn.execute(statement)
        conn.commit()
    finally:
        conn.close()


def slash_offer(issue_id: str = "FEAT-001", *, root: str = "/proj") -> SimpleNamespace:
    """A candidate-shaped offer for the ``implement-issue`` slash action."""
    spec = slash_spec_for("manage-issue:implement", issue_id, root)
    return SimpleNamespace(
        action_type="implement-issue",
        action_key=action_key(spec),
        action_fingerprint=action_fingerprint(spec),
        target=issue_id,
        target_key=f"issue:{issue_id}",
        action_spec=spec,
    )


def loop_offer(name: str = "daily", *, root: str = "/proj") -> SimpleNamespace:
    """A candidate-shaped offer for the ``run-loop`` action (carries definition provenance)."""
    spec = LoopActionSpec(
        target=name,
        definition_source=f".loops/{name}.yaml",
        definition_digest="sha256:" + "ab" * 32,
        fingerprint_scope=FINGERPRINT_SCOPE_V1,
        working_directory=root,
    )
    return SimpleNamespace(
        action_type="run-loop",
        action_key=action_key(spec),
        action_fingerprint=action_fingerprint(spec),
        target=name,
        target_key=f"loop:{name}",
        action_spec=spec,
    )


def event_row(root: Path | str = "/proj", **overrides: Any) -> dict[str, Any]:
    """A complete ``shown`` row as a mapping (override any column)."""
    spec = slash_spec_for("manage-issue:implement", "FEAT-001", str(root))
    row: dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "rec_id": str(uuid.uuid4()),
        "kind": "shown",
        "ts": "2026-10-08T09:30:00.000000Z",
        "project_key": project_key_for(Path(root)),
        "session_id": None,
        "invocation_id": str(uuid.uuid4()),
        "as_of": "2026-10-08T09:29:59.000000Z",
        "rank": 1,
        "action_type": "implement-issue",
        "action_key": action_key(spec),
        "action_fingerprint": action_fingerprint(spec),
        "target": "FEAT-001",
        "target_key": "issue:FEAT-001",
        "action_spec": json.dumps(spec_to_dict(spec), sort_keys=True, separators=(",", ":")),
        "requested_top": None,
        "requested_types": "[]",
    }
    row.update(overrides)
    return row


def insert_row(path: Path, row: dict[str, Any]) -> None:
    """Insert *row* verbatim (no validation beyond the table's own constraints)."""
    conn = sqlite3.connect(path)
    try:
        columns = list(row)
        conn.execute(
            f"INSERT INTO recommendation_events ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})",
            [row[c] for c in columns],
        )
        conn.commit()
    finally:
        conn.close()


def fetch_rows(path: Path) -> list[dict[str, Any]]:
    """All stored rows in insertion order, as mappings over the consumed columns."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        cols = ", ".join(RECOMMENDATION_EVENT_COLUMNS)
        return [
            dict(r) for r in conn.execute(f"SELECT {cols} FROM recommendation_events ORDER BY id")
        ]
    finally:
        conn.close()
