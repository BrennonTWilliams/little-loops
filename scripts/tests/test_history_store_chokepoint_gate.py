"""Gate: no raw ``sqlite3.connect(`` calls outside the backend chokepoint (ENH-3525).

AST-scans ``scripts/little_loops/`` for real ``sqlite3.connect(...)`` call
sites (not string/docstring mentions) and fails on any site outside
``session_store/backend.py`` and the reasoned allowlist below. This is the
same "enumerate every site, keep the chokepoint the only opener" pattern
``.claude/CLAUDE.md`` § Host CLI Abstraction already applies to host-CLI
subprocess spawns.

The allowlist has two kinds of entries:

- **Permanent** — never a history-store connection at all (a different
  database entirely), or the chokepoint's own internal implementation.
- **Provisional (ENH-3525 A2)** — a real history.db connection this issue's
  Phase A ("A1") deliberately leaves unrouted. A1 folds the 7 in-scope
  read-only opens plus the ``workspace_quality`` ATTACH into the chokepoint
  and fixes the three path-resolution bypasses; routing the remaining write
  call sites through ``open_history()`` is A2's "consumer error-type
  conversion" pass (Implementation Steps 5-6), which also converts each
  site's ``except sqlite3.*`` handling — shrink this allowlist as each site
  is routed.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC_ROOT = _REPO_ROOT / "scripts" / "little_loops"

# path relative to scripts/little_loops -> one-line reason.
_ALLOWLIST: dict[str, str] = {
    # -- Permanent: a different database entirely, not history.db. --
    "queue_store.py": "queue.db is an independent local store, not history.db",
    "codequery/codegraph.py": "codegraph index DB, not history.db (issue-confirmed exclusion)",
    "session_store/sessions.py": (
        "Codex's own ~/.codex/state_*.sqlite session index, not .ll/history.db "
        "(issue-confirmed exclusion)"
    ),
    # -- Permanent: the chokepoint's own implementation. --
    "session_store/backend.py": "the chokepoint itself",
    "session_store/schema.py": (
        "ensure_db()/connect()'s own migration+connect sequence, which "
        "SqliteBackend.connect()/ensure_schema() wrap rather than duplicate "
        "(connect()'s two-connection-per-call shape is deliberately out of "
        "scope for ENH-3525); _reference_manifest_at()'s :memory: replay is "
        "a scratch DB, not a real store"
    ),
    "session_store/queries.py": (
        "_connect_readonly() already implements the strict read-only contract "
        "(mode=ro, never creates/migrates, D19) and is pinned verbatim by "
        "test_feat3304_artifact_dashboard.py::"
        "test_snapshot_builder_never_uses_the_migrating_open_path's literal "
        "source-text assertion"
    ),
    "issue_history/workspace_quality.py": (
        "_open_union()/_open_memory()'s :memory: connections are scratch hosts "
        "for read-only-ATTACHed real history.db files (gated on the 'attach' "
        "capability), not themselves history-store connections"
    ),
    # -- Provisional (ENH-3525 A2): real history.db writers not yet routed. --
    "session_store/writers.py": (
        "SQLiteTransport keeps one long-lived connection across many events "
        "(not a per-call open); routing it through open_history() is A2 "
        "Step 5 consumer-error-type-conversion territory"
    ),
    "session_store/lifecycle.py": (
        "VACUUM maintenance connections (capability-gated by supports('vacuum') "
        "in Program Design); routing pending ENH-3525 A2"
    ),
    "cli/logs.py": "raw history.db connections pending ENH-3525 A2 consumer routing",
    "cli/ctx_stats.py": "raw history.db connections pending ENH-3525 A2 consumer routing",
    "cli/history.py": "raw history.db connection pending ENH-3525 A2 consumer routing",
}


def _sqlite_connect_calls(tree: ast.AST) -> list[ast.Call]:
    calls = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "connect"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "sqlite3"
        ):
            calls.append(node)
    return calls


def _iter_source_files() -> list[Path]:
    return sorted(p for p in _SRC_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def test_no_raw_sqlite_connect_outside_chokepoint_and_allowlist() -> None:
    violations: list[str] = []
    for path in _iter_source_files():
        rel = path.relative_to(_SRC_ROOT).as_posix()
        if rel in _ALLOWLIST:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        calls = _sqlite_connect_calls(tree)
        for call in calls:
            violations.append(f"{rel}:{call.lineno}")

    assert not violations, (
        "raw sqlite3.connect( outside session_store/backend.py and the "
        "allowlist -- route through little_loops.session_store.backend "
        "(open_history/open_history_readonly/connect_readonly/resolve_backend) "
        "or add a reasoned allowlist entry in this test:\n" + "\n".join(violations)
    )


def test_allowlist_entries_still_exist_and_still_have_raw_connects() -> None:
    """Catch allowlist drift: an entry for a file that no longer exists, or
    that no longer has any raw sqlite3.connect( call (fully migrated -- the
    entry should be removed, shrinking the gate)."""
    stale_paths = []
    fully_migrated = []
    for rel in _ALLOWLIST:
        path = _SRC_ROOT / rel
        if not path.exists():
            stale_paths.append(rel)
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if not _sqlite_connect_calls(tree):
            fully_migrated.append(rel)

    assert not stale_paths, f"allowlist entries for files that no longer exist: {stale_paths}"
    assert not fully_migrated, (
        "allowlist entries for files with no remaining raw sqlite3.connect( -- "
        f"remove these entries: {fully_migrated}"
    )
