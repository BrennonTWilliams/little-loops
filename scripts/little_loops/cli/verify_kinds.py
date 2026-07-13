"""ll-verify-kinds: assert every raw_events-adjacent CREATE TABLE is kind-registered (ENH-2581).

Scans ``session_store._MIGRATIONS`` for ``CREATE TABLE`` statements and asserts
each table name is either registered in ``_KIND_TABLE`` (so ``recent()``/
``search --kind`` can query it) or explicitly listed in ``_KINDLESS_TABLES``
(support tables with no "recent by kind" concept — ``meta``, ``search_index``,
``sessions``, ``assistant_messages``, ``summary_nodes``, ``summary_spans``,
``raw_events``). Catches the case a new ``*_events`` table is added without
registering its kind (the historical gap this issue fixes for ``snapshot``).

Exit codes:
    0 - every CREATE TABLE is registered or explicitly kindless
    1 - one or more tables are neither
"""

from __future__ import annotations

import argparse
import re
import sys

from little_loops import session_store
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

_CREATE_TABLE_RE = re.compile(
    r"CREATE TABLE (?:IF NOT EXISTS )?([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE
)


def _all_migration_tables() -> set[str]:
    """Return every table name created anywhere in ``_MIGRATIONS``."""
    tables: set[str] = set()
    for migration_sql in session_store._MIGRATIONS:
        tables.update(_CREATE_TABLE_RE.findall(migration_sql))
    return tables


def _run() -> tuple[int, list[str]]:
    """Return ``(exit_code, unregistered_table_names)``."""
    registered = set(session_store._KIND_TABLE.values())
    kindless = session_store._KINDLESS_TABLES
    unregistered = sorted(
        table
        for table in _all_migration_tables()
        if table not in registered and table not in kindless
    )
    return (1 if unregistered else 0), unregistered


def main_verify_kinds() -> int:
    """Entry point for ``ll-verify-kinds``."""
    with cli_event_context(DEFAULT_DB_PATH, "ll-verify-kinds", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-verify-kinds",
            description=(
                "Assert every CREATE TABLE in session_store._MIGRATIONS is either "
                "registered in _KIND_TABLE or explicitly listed in _KINDLESS_TABLES. "
                "Exits 1 if a table is neither (ENH-2581)."
            ),
        )
        parser.parse_args()

        exit_code, unregistered = _run()
        if unregistered:
            print(
                "ERROR: tables with no VALID_KINDS registration and not in "
                "_KINDLESS_TABLES: " + ", ".join(unregistered),
                file=sys.stderr,
            )
        return exit_code


if __name__ == "__main__":
    sys.exit(main_verify_kinds())
