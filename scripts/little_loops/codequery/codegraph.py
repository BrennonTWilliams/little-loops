"""SQLite-backed :class:`CodeQueryProvider` over a `codegraph` index (ENH-2613).

Reads the read-only ``.codegraph/codegraph.db`` index produced by the external
`colbymchenry/codegraph <https://github.com/colbymchenry/codegraph>`__ tool.
Schema discovered against this repo's live index (2026-06-01 build,
``sqlite3 .codegraph/codegraph.db .schema``)::

    nodes(id, kind, name, qualified_name, file_path, language, start_line,
          end_line, start_column, end_column, docstring, signature,
          visibility, is_exported, is_async, is_static, is_abstract,
          decorators, type_parameters, updated_at)
    edges(id, source, target, kind, metadata, line, col, provenance)
        FK'd to nodes(id); kind in {calls, contains, extends, imports,
        instantiates, references}
    files(path, content_hash, language, size, modified_at, indexed_at,
          node_count, errors)
    schema_versions(version, applied_at, description)

Verb mapping: ``callers_of``/``callees_of`` <- edges.kind='calls',
``importers_of`` <- edges.kind='imports', ``references`` <- edges.kind in
('calls', 'references'), ``defines`` <- nodes filtered by file_path. No edge
kind maps to ``impact_of``; it stays out of :meth:`capabilities` and raises
:class:`~little_loops.codequery.core.Unsupported`.
"""

from __future__ import annotations

import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from little_loops.codequery.core import CodeRef, Freshness, ProviderStatus, Unsupported

_NAME = "codegraph"
_GIT_TIMEOUT = 10

# codegraph edge kinds that resolve callers/callees/references.
_CALL_KINDS = ("calls",)
_REFERENCE_KINDS = ("calls", "references")


def _git_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return Path.cwd()
    return Path(result.stdout.strip())


def _git(repo_root: Path, *args: str) -> str | None:
    """Return stripped stdout of a git command run in *repo_root*, or None."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _open_db(db_path: Path) -> sqlite3.Connection | None:
    """Open *db_path* read-only, never raising. Mirrors ``issue_history/evolution.py::_open_db``."""
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        return conn
    except sqlite3.Error:
        return None


def _epoch_ms_to_iso(epoch_ms: int) -> str:
    return (
        datetime.fromtimestamp(epoch_ms / 1000, tz=UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _short_symbol(symbol: str) -> str:
    """Return the trailing identifier of a dotted or ``Class::method`` symbol path."""
    tail = symbol.rsplit("::", 1)[-1]
    return tail.rsplit(".", 1)[-1]


def _porcelain_paths(dirty_raw: str) -> list[str]:
    """Extract file paths from ``git status --porcelain`` output.

    Handles the ``XY path`` and rename ``XY old -> new`` formats (mirrors the
    parsing convention in ``parallel/merge_coordinator.py``).
    """
    paths = []
    for line in dirty_raw.splitlines():
        if not line:
            continue
        path = line[3:].split(" -> ")[-1].strip()
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        if path:
            paths.append(path)
    return paths


def _is_scan_relevant(path: str, focus_dirs: list[str], exclude_patterns: list[str]) -> bool:
    """Return True if *path* falls under the codegraph provider's scan scope.

    A path is relevant only if it's under one of ``focus_dirs`` (empty
    ``focus_dirs`` is treated as "no scope restriction", preserving prior
    repo-wide behavior) and doesn't match any ``exclude_patterns`` entry.
    """
    from little_loops.git_operations import _file_matches_pattern

    if any(_file_matches_pattern(path, pattern) for pattern in exclude_patterns):
        return False
    if not focus_dirs:
        return True
    return any(path == d.rstrip("/") or path.startswith(d.rstrip("/") + "/") for d in focus_dirs)


def _module_to_file_guess(module: str) -> str:
    """Best-effort conversion of a dotted module or file path to a repo-relative path."""
    if module.endswith(".py"):
        return module
    return module.replace(".", "/") + ".py"


class CodegraphProvider:
    """`codegraph` SQLite index-backed :class:`~little_loops.codequery.core.CodeQueryProvider`."""

    name = _NAME

    def capabilities(self) -> set[str]:
        return {"callers_of", "callees_of", "importers_of", "defines", "references"}

    def _config(self):
        from little_loops.config import BRConfig

        return BRConfig(_git_root()).code_query

    def _db_path(self) -> Path:
        root = _git_root()
        return root / self._config().codegraph.db_path

    def status(self) -> ProviderStatus:
        config = self._config()
        db_path = _git_root() / config.codegraph.db_path
        policy = config.staleness

        conn = _open_db(db_path)
        if conn is None:
            return ProviderStatus(
                available=False,
                freshness="unknown",
                indexed_at=None,
                detail=f"no codegraph index found at {db_path}",
            )

        try:
            row = conn.execute("SELECT MAX(indexed_at) AS ts FROM files").fetchone()
            indexed_ms = row["ts"] if row and row["ts"] is not None else None
            if indexed_ms is None:
                row = conn.execute("SELECT MAX(applied_at) AS ts FROM schema_versions").fetchone()
                indexed_ms = row["ts"] if row and row["ts"] is not None else None
        finally:
            conn.close()

        if indexed_ms is None:
            return ProviderStatus(
                available=False,
                freshness="unknown",
                indexed_at=None,
                detail=f"codegraph index at {db_path} has no timestamp metadata",
            )

        indexed_at = _epoch_ms_to_iso(int(indexed_ms))
        root = _git_root()
        head_moved_raw = _git(root, "log", f"--since={indexed_at}", "--oneline")
        head_moved = len(head_moved_raw.splitlines()) if head_moved_raw else 0
        dirty_raw = _git(root, "status", "--porcelain")

        from little_loops.config import BRConfig

        scan = BRConfig(root).scan
        dirty_files = (
            sum(
                1
                for path in _porcelain_paths(dirty_raw)
                if _is_scan_relevant(path, scan.focus_dirs, scan.exclude_patterns)
            )
            if dirty_raw
            else 0
        )

        is_fresh = head_moved == 0 and dirty_files == 0
        raw_freshness: Freshness = "fresh" if is_fresh else "stale"

        if policy == "off":
            return ProviderStatus(
                available=True,
                freshness="fresh",
                indexed_at=indexed_at,
                detail=(
                    f"policy=off: trusting index unconditionally "
                    f"(indexed_at={indexed_at}, head_moved={head_moved} commits, "
                    f"dirty_files={dirty_files})"
                ),
            )

        detail = (
            f"indexed_at={indexed_at}, head_moved={head_moved} commits, "
            f"dirty_files={dirty_files}, policy={policy}"
        )
        if policy == "strict" and not is_fresh:
            return ProviderStatus(
                available=False,
                freshness="stale",
                indexed_at=indexed_at,
                detail=f"{detail}: stale index, unavailable under strict policy",
            )

        return ProviderStatus(
            available=True,
            freshness=raw_freshness,
            indexed_at=indexed_at,
            detail=detail if raw_freshness == "stale" else f"{detail}: fresh",
        )

    def _find_node_ids(self, conn: sqlite3.Connection, symbol: str) -> list[str]:
        rows = conn.execute("SELECT id FROM nodes WHERE qualified_name = ?", (symbol,)).fetchall()
        if not rows:
            rows = conn.execute(
                "SELECT id FROM nodes WHERE name = ?", (_short_symbol(symbol),)
            ).fetchall()
        return [row["id"] for row in rows]

    def callers_of(self, symbol: str) -> list[CodeRef]:
        conn = _open_db(self._db_path())
        if conn is None:
            return []
        try:
            ids = self._find_node_ids(conn, symbol)
            if not ids:
                return []
            placeholders = ",".join("?" for _ in ids)
            rows = conn.execute(
                f"""
                SELECT src.file_path AS path, e.line AS eline, src.start_line AS sline,
                       src.qualified_name AS sym
                FROM edges e JOIN nodes src ON e.source = src.id
                WHERE e.kind IN ({",".join("?" for _ in _CALL_KINDS)})
                  AND e.target IN ({placeholders})
                """,
                (*_CALL_KINDS, *ids),
            ).fetchall()
            return [
                CodeRef(
                    path=row["path"],
                    line=row["eline"] or row["sline"],
                    symbol=row["sym"],
                    kind="call",
                    confidence="exact",
                    provider=self.name,
                )
                for row in rows
            ]
        finally:
            conn.close()

    def callees_of(self, symbol: str) -> list[CodeRef]:
        conn = _open_db(self._db_path())
        if conn is None:
            return []
        try:
            ids = self._find_node_ids(conn, symbol)
            if not ids:
                return []
            placeholders = ",".join("?" for _ in ids)
            rows = conn.execute(
                f"""
                SELECT tgt.file_path AS path, e.line AS eline, tgt.start_line AS sline,
                       tgt.qualified_name AS sym
                FROM edges e JOIN nodes tgt ON e.target = tgt.id
                WHERE e.kind IN ({",".join("?" for _ in _CALL_KINDS)})
                  AND e.source IN ({placeholders})
                """,
                (*_CALL_KINDS, *ids),
            ).fetchall()
            return [
                CodeRef(
                    path=row["path"],
                    line=row["eline"] or row["sline"],
                    symbol=row["sym"],
                    kind="call",
                    confidence="exact",
                    provider=self.name,
                )
                for row in rows
            ]
        finally:
            conn.close()

    def importers_of(self, module: str) -> list[CodeRef]:
        conn = _open_db(self._db_path())
        if conn is None:
            return []
        try:
            file_guess = _module_to_file_guess(module)
            dotted_guess = file_guess[: -len(".py")].replace("/", ".")
            rows = conn.execute(
                "SELECT id FROM nodes WHERE kind = 'import' "
                "AND (qualified_name = ? OR qualified_name = ? OR name = ?)",
                (dotted_guess, module, _short_symbol(module)),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if not ids:
                return []
            placeholders = ",".join("?" for _ in ids)
            rows = conn.execute(
                f"""
                SELECT src.file_path AS path, e.line AS eline, src.start_line AS sline,
                       src.qualified_name AS sym
                FROM edges e JOIN nodes src ON e.source = src.id
                WHERE e.kind = 'imports' AND e.target IN ({placeholders})
                """,
                ids,
            ).fetchall()
            return [
                CodeRef(
                    path=row["path"],
                    line=row["eline"] or row["sline"],
                    symbol=row["sym"] or dotted_guess,
                    kind="import",
                    confidence="exact",
                    provider=self.name,
                )
                for row in rows
            ]
        finally:
            conn.close()

    def defines(self, path: str) -> list[CodeRef]:
        conn = _open_db(self._db_path())
        if conn is None:
            return []
        try:
            rows = conn.execute(
                "SELECT kind, name, start_line FROM nodes "
                "WHERE file_path = ? AND kind NOT IN ('file', 'import')",
                (path,),
            ).fetchall()
            return [
                CodeRef(
                    path=path,
                    line=row["start_line"],
                    symbol=row["name"],
                    kind=row["kind"],
                    confidence="exact",
                    provider=self.name,
                )
                for row in rows
            ]
        finally:
            conn.close()

    def references(self, symbol: str) -> list[CodeRef]:
        conn = _open_db(self._db_path())
        if conn is None:
            return []
        try:
            ids = self._find_node_ids(conn, symbol)
            if not ids:
                return []
            placeholders = ",".join("?" for _ in ids)
            rows = conn.execute(
                f"""
                SELECT src.file_path AS path, e.line AS eline, src.start_line AS sline
                FROM edges e JOIN nodes src ON e.source = src.id
                WHERE e.kind IN ({",".join("?" for _ in _REFERENCE_KINDS)})
                  AND e.target IN ({placeholders})
                """,
                (*_REFERENCE_KINDS, *ids),
            ).fetchall()
            short = _short_symbol(symbol)
            return [
                CodeRef(
                    path=row["path"],
                    line=row["eline"] or row["sline"],
                    symbol=short,
                    kind="reference",
                    confidence="exact",
                    provider=self.name,
                )
                for row in rows
            ]
        finally:
            conn.close()

    def impact_of(self, paths: list[str], depth: int = 2) -> list[CodeRef]:
        raise Unsupported(
            "codegraph provider has no edge kind mapping to impact_of; "
            "use the fallback provider for this query"
        )
