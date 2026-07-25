---
id: ENH-2772
status: open
priority: P2
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24T22:31:26Z
discovered_by: audit-architecture
focus_area: large-files
labels: [enhancement, architecture, refactoring, auto-generated]
parent: EPIC-2789
---

# ENH-2772: Split session_store.py god module into a subpackage

## Summary

Architectural issue found by `/ll:audit-architecture`. `session_store.py` is the
largest file in the codebase and its most heavily depended-on module at the same
time — a god module whose blast radius covers most of the package.

## Location

- **File**: `scripts/little_loops/session_store.py`
- **Line(s)**: 1-5154 (entire file)
- **Module**: `little_loops.session_store`

## Finding

### Current State

- 5,154 lines, 89 top-level defs/classes in a single module.
- Fan-in of **70 modules** import from it — the second-highest in the package
  (after `little_loops.config` at 78).
- It carries at least four separable concerns already named by the CLI surface
  (`ll-session` subcommands): SQL migrations (`_MIGRATIONS`), the
  `_KIND_TABLE` kind registry, the query/read API (search, recent, expand,
  describe), and the retention lifecycle (compact, prune, recompress, backfill).
- A circular dependency with `little_loops.compaction` is broken via deferred
  imports at `session_store.py:4119` and `:4136` — a symptom of concerns that
  belong in separate modules.

### Impact

- **Development velocity**: any change to session storage touches a 5k-line file
  with 70 dependents; reviews and merges routinely conflict here (it is the
  most-edited source file over the last 7 days).
- **Maintainability**: migrations, schema registry, queries, and retention are
  interleaved; finding the right seam requires reading most of the file.
- **Risk**: high — wide blast radius means a regression here breaks history,
  analytics, compaction, and several CLIs at once.

## Proposed Solution

Convert to a `session_store/` subpackage with the module split along the
existing seams, keeping `little_loops.session_store` as the public import path
(re-export via `__init__.py` so none of the 70 importers change).

### Suggested Approach

1. Create `session_store/` package; move `_MIGRATIONS` + `_KIND_TABLE` into
   `schema.py` (this is also what `ll-verify-kinds` inspects — update its
   import).
2. Move the read/query API (search/FTS, recent, expand, describe, grep) into
   `queries.py`; move backfill/compact/prune/recompress into `lifecycle.py`.
3. Keep the connection/db-path resolution (`LL_HISTORY_DB` → config → default)
   in `__init__.py` or `db.py`; re-export the existing public names from
   `__init__.py` and confirm `python -m pytest scripts/tests/` passes with no
   importer changes.

## Impact Assessment

- **Severity**: High
- **Effort**: Large
- **Risk**: Medium
- **Breaking Change**: No (public import path preserved via re-exports)

---

## Status

**Open** | Created: 2026-07-24 | Priority: P2
