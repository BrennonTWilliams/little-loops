# Spike Plan: FEAT-3524 — session_store backend dialect abstraction

## Context

FEAT-3524 has no `## Confidence Check Notes` / `### Outcome Risk Factors` section
yet (issue is freshly refined, not yet run through `/ll:confidence-check`). Per
`/ll:spike` Phase 2 fallback, this plan is derived from standalone analysis of
the issue's `## Proposed Solution` and `### Codebase Research Findings`.

The riskiest unprecedented **internal** mechanism, scoped by the user to exclude
backend choice and driver connectivity:

> "No dialect abstraction exists anywhere in the codebase today: a repo-wide
> search for `dialect` as a code identifier and for any `*Dialect` class found
> zero hits. `little_loops.session_store.backend` (the module this issue
> proposes) has no current counterpart in the tree." (Codebase Research Findings)

Two canonical low-confidence drivers both apply:

- **(a) Zero precedent**: `_apply_migrations` (`session_store/schema.py:1492`)
  takes a live `sqlite3.Connection` directly, `_MIGRATIONS` is an unconditional
  `list[str]` of raw SQL with no per-dialect branch, and locking is
  SQLite-specific (`BEGIN IMMEDIATE`, manual `isolation_level = None`, the
  custom `_split_sql_statements()` helper that exists specifically to avoid
  `executescript()`'s implicit `COMMIT`, which would release the write lock
  mid-migration). Nothing in the codebase proves this sequence still holds
  once a second dialect exists behind the same call.
- **(b) No existing test exercises the risky core**: no test anywhere invokes
  `_apply_migrations`/`_configure_connection` through anything but a raw
  `sqlite3.Connection`, and no test exercises a capability-flag-gated feature
  (FTS5/WAL/VACUUM) degrading rather than crashing.

The Postgres-vs-libSQL Open Question and `psycopg`/`libsql` driver
connectivity (`learning_tests_required` in frontmatter) are **excluded** from
this spike — those are external-API risk (`/ll:explore-api` territory) and an
unresolved Option A/B choice (`/ll:decide-issue` territory), not an
unprecedented internal mechanism.

## Approach

Build a standalone `Backend` protocol with two dialect implementations that
both run on real `sqlite3.Connection`s but differ in declared capabilities —
proving the abstraction shape (chokepoint + capability flags + per-dialect
migration DDL + degradation) without needing a real network driver:

- **`sqlite` dialect**: full capability set (`fts5`, `wal`, `vacuum`),
  migrations use today's DDL shape (`AUTOINCREMENT`).
- **`stub_remote` dialect**: a second sqlite3-backed dialect with a
  *reduced* capability set (no `fts5`, no `wal`) and *different* migration
  DDL for one table (no `AUTOINCREMENT`, since most non-SQLite dialects
  reject SQLite's `AUTOINCREMENT` syntax) — standing in for "a real remote
  dialect" without opening a network connection. This is real enough to prove
  the per-dialect DDL branch and the capability-gated degradation path fire
  correctly; a genuine Postgres/libSQL DDL dialect is `/ll:explore-api` work
  deferred to implementation.

What's faked: the *network* aspect of a remote backend (still sqlite3
under the hood). What's real: the `Backend` protocol, the chokepoint that
routes `connect()`/`ensure_schema()` through dialect-specific migration DDL,
the `supports()` capability check, and the graceful-degradation message path
for an unsupported feature — the actual unprecedented mechanism.

## Critical files

Production files whose contract the spike must honor (not modified by this
skill):

- `scripts/little_loops/session_store/schema.py` — `_apply_migrations`
  (line 1492), `_configure_connection` (line 1443), `_split_sql_statements`
  (line 1462), `ensure_db` (line 1570): the exact locking sequence
  (`BEGIN IMMEDIATE` / manual `isolation_level` / statement-split, never
  `executescript`) must survive being driven through a dialect-parameterized
  migration list.
- `scripts/little_loops/host_runner.py` — `resolve_host()` (line 2535) and
  `HostCapabilities` (line 294): eager-registry + frozen-dataclass-of-booleans
  precedent for capability flags.
- `scripts/little_loops/codequery/core.py` — `resolve_provider()` (line 103)
  and `_PROVIDER_MAP` (line 93): lazy-import `@runtime_checkable` Protocol +
  name-keyed registry precedent (used here instead of eager import, since a
  `Backend` module and its dialect implementations would otherwise cycle the
  same way `codequery` providers do).

New spike package: `scripts/tests/spike/session_store_backend_dialect/`.

## Implementation

```
scripts/tests/spike/session_store_backend_dialect/
├── __init__.py
├── backend.py              # Backend Protocol, resolve_backend(), capability flags
├── dialects.py             # sqlite + stub_remote dialect DDL/capability tables
└── test_backend.py         # the AC test class
```

API sketch (`backend.py`):

```python
from typing import Protocol, runtime_checkable

CAPABILITIES = frozenset({"fts5", "wal", "vacuum"})

@runtime_checkable
class Backend(Protocol):
    kind: str

    def connect(self) -> sqlite3.Connection: ...
    def connect_readonly(self) -> sqlite3.Connection: ...
    def ensure_schema(self) -> None: ...
    def supports(self, capability: str) -> bool: ...

_BACKEND_MAP: dict[str, tuple[str, str]] = {
    "sqlite": ("dialects", "SqliteBackend"),
    "stub_remote": ("dialects", "StubRemoteBackend"),
}

def resolve_backend(kind: str, db_path: Path) -> Backend: ...

def apply_migrations(conn: sqlite3.Connection, backend: Backend) -> None:
    """Mirrors schema._apply_migrations's BEGIN IMMEDIATE / manual
    isolation_level / _split_sql_statements sequence, parameterized by
    backend.migrations() instead of the module-level _MIGRATIONS list."""
```

## Acceptance Criteria → Test Table

| Test | Retires (AC / risk) | Kind |
|------|---------------------|------|
| `test_sqlite_backend_migrates_with_existing_locking_sequence` | Risk (a): proves the `BEGIN IMMEDIATE`/manual-isolation/split-statement sequence survives being parameterized by dialect | behavior |
| `test_stub_remote_backend_uses_dialect_specific_ddl` | Risk (a): proves per-dialect DDL branch actually diverges (no `AUTOINCREMENT`) and produces a working schema | behavior |
| `test_capability_check_gates_unsupported_feature` | Risk (b): `supports("fts5")` is `False` on `stub_remote`, and the caller path degrades with a clear message instead of raising | behavior |
| `test_concurrent_migration_race_still_serializes` | Risk (a): two connections racing `ensure_schema()` on the same dialect still serialize under `BEGIN IMMEDIATE` (mirrors the fresh-database race `_apply_migrations`'s docstring calls out) | behavior |
| `test_spike_does_not_import_production_session_store` | isolation guard: AST sniff — spike imports no `little_loops.session_store.*` module | regression |

## Verification

```bash
python -m pytest scripts/tests/spike/session_store_backend_dialect/ -v
python -m pytest scripts/tests/test_session_store_schema.py -v
```

The second command is the named existing regression suite for the production
mechanism this spike stands in for — it must stay green and untouched, proving
the spike didn't require touching production code to reach its result.

## Out of Scope

- Any real Postgres or libSQL connection (`psycopg`, `libsql` drivers) —
  `/ll:explore-api` territory, already tracked via
  `learning_tests_required` in the issue frontmatter.
- Deciding Postgres vs. libSQL as the first non-SQLite backend —
  `/ll:decide-issue` territory (issue's own Open Questions).
- `config-schema.json` changes, `resolve_history_db`/`_resolve_db_path`
  wiring, or routing any of the ~28 real `session_store` call sites through
  the abstraction — that's the real integration point, done at
  implementation time.
- FTS5/WAL/VACUUM's actual SQL bodies — only the capability-gate/degradation
  *mechanism* is spiked, not every gated feature.

## Promotion

On acceptance, fold `backend.py`'s `Backend` protocol shape and
`apply_migrations`'s dialect-parameterized locking sequence into
`little_loops/session_store/backend.py` (new production module) and
`little_loops/session_store/schema.py` (`_apply_migrations` refactored to
delegate to it), with tests promoted into
`scripts/tests/test_session_store_schema.py` /
`scripts/tests/test_session_store_backend.py` (new), in a separate PR. There
is no promotion directory — this is a manual step.
