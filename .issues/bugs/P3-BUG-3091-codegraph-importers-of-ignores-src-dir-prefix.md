---
id: BUG-3091
title: CodegraphProvider.importers_of/impact_of can't resolve paths nested under project.src_dir
type: BUG
priority: P3
captured_at: '2026-08-06T20:15:36Z'
discovered_date: 2026-08-06
discovered_by: session
status: open
testable: true
labels:
- bug
- codequery
- codegraph
relates_to:
- ENH-3092
decision_needed: false
---

# BUG-3091: `CodegraphProvider.importers_of`/`impact_of` can't resolve paths nested under `project.src_dir`

## Summary

`CodegraphProvider.importers_of()` guesses a dotted module name from a repo-relative
file path (`_module_to_file_guess` / the `dotted_guess` local in `importers_of()`,
`scripts/little_loops/codequery/codegraph.py:194-198,395-432`) by taking the path
verbatim relative to the **repo root**. But the `codegraph` tool indexes import
`qualified_name`s relative to the project's **source root** (this repo's
`project.src_dir: "scripts/"`), so every lookup for a path under `src_dir` fails to
match and silently returns no results.

`impact_of()` (added this session, wired on top of `importers_of()`) inherits this
gap directly, since it's a transitive walk of the same relation.

## Current Behavior

```
$ sqlite3 .codegraph/codegraph.db "select qualified_name from nodes where kind='import' and qualified_name like '%issue_manager%'"
little_loops.issue_manager
```

But:

```
$ ll-code --json importers-of scripts/little_loops/issue_manager.py
{"provider": "codegraph", "freshness": "stale", "query": "importers_of", "results": []}
$ ll-code --json impact-of scripts/little_loops/issue_manager.py --depth 1
{"provider": "codegraph", "freshness": "stale", "query": "impact_of", "results": []}
```

despite `issue_manager` being imported by many files in this repo (confirmed via
`edges.kind='imports'` count and direct grep). `_module_to_file_guess("scripts/little_loops/issue_manager.py")`
produces the dotted guess `scripts.little_loops.issue_manager`, which never matches
the index's `little_loops.issue_manager` (indexed relative to `scripts/`, the
project's `src_dir`).

## Steps to Reproduce

1. In a project with `project.src_dir` set to a non-root package directory (this
   repo: `"scripts/"`), build/refresh the `codegraph` index.
2. Run `ll-code --json importers-of <path under src_dir>` for a module known to
   have importers (e.g. `scripts/little_loops/issue_manager.py`).
3. Observe `results: []` even though `edges.kind='imports'` rows referencing that
   module exist in `.codegraph/codegraph.db`.
4. Run `ll-code --json impact-of <same path>` — also `results: []`, since
   `impact_of()` is a transitive walk of `importers_of()`.

## Expected Behavior

`importers_of()` (and transitively `impact_of()`) should strip the configured
`project.src_dir` prefix before computing the dotted-module guess, so file paths
that are valid arguments to `defines`/`callers-of`/etc. also resolve correctly here.

## Root Cause

- **File**: `scripts/little_loops/codequery/codegraph.py:194-198` (`_module_to_file_guess`)
  and `:395-432` (`importers_of`) — both operate on the path as given (repo-relative),
  with no knowledge of `BRConfig(...).project.src_dir`.
- The `codegraph` external tool indexes files/imports relative to whatever root it
  was pointed at (this repo's project root), but Python import statements are
  naturally relative to the *package* root (`scripts/`), not the repo root — so the
  qualified names in the index never carry the `scripts.` prefix.

## Proposed Solution

In `importers_of()` (and the shared guess helper), read `project.src_dir` from
`self._config()`'s owning `BRConfig` (already fetched via `self._config()` for
other methods) and strip it from the front of the repo-relative path before
building `dotted_guess`. Should also try the un-stripped guess as a fallback for
providers/repos where `src_dir` is unset or `"."`, so behavior is unchanged for
projects with no src layout.

## Impact

- **Priority**: P3 — degrades an already-optional acceleration path (`ll-code`
  always has a working, if slower, `fallback` provider); not user-facing breakage,
  but silently makes `importers_of`/`impact_of` return false negatives (empty
  results, not errors) for any project using a `src_dir` layout — including this
  repo.
- **Effort**: Small — one path-prefix-stripping fix, localized to `codegraph.py`.
- **Risk**: Low — additive resolution attempt; existing successful lookups keep
  working.

## Related Key Documentation

- [[ENH-3090]] — added `impact_of` to `CodegraphProvider`; this bug was discovered
  while verifying that change against this repo's real `.codegraph/codegraph.db`
  index.

## Labels

`bug`, `codequery`, `codegraph`

---

**Open** | Created: 2026-08-06 | Priority: P3
