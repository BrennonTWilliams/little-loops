---
id: BUG-3305
type: BUG
title: Codegraph staleness never clears for unindexed file extensions
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-23'
captured_at: '2026-08-23T20:25:11Z'
completed_at: '2026-08-23T20:25:53Z'
---

# BUG-3305: Codegraph staleness never clears for unindexed file extensions

## Summary

`CodegraphProvider.status()` (`scripts/little_loops/codequery/codegraph.py`) can report
`ll-code status` as permanently `stale` even when the external `codegraph` CLI itself
reports the index fully up to date, because `_content_aware_head_moved()` treats any
scan-relevant touched path missing a `content_hash` entry as "changed" -- with no
distinction between a file codegraph *hasn't indexed yet* and a file whose extension
codegraph *never indexes at all*.

## Current Behavior

Confirmed live: `.codegraph/codegraph.db`'s `files` table has zero rows for `.json` paths
(the index's own "Files by Language" breakdown lists only python/yaml/javascript/
typescript/xml). `scripts/little_loops/session_store/schema_manifest.json` -- a `.json`
file under the `scripts/` focus dir, last touched in commit `8da0a754e` -- has no
`content_hash` row and never will. Every `ll-code status` call recomputes `head_moved=1`
for this one path, permanently. The inline auto-sync in `status()` (`_sync_if_stale`,
gated by `config.staleness`/`auto_sync`, from ENH-2863) runs `codegraph sync --quiet` on
every stale read as designed, but it's a no-op here -- `codegraph sync` itself correctly
reports "Already up to date" since it never tracked this file to begin with. No amount of
syncing can clear the staleness signal.

Note: there is no `SessionStart` hook involved in codegraph refresh at all (checked
`scripts/little_loops/hooks/` and `hooks/` -- neither references `codegraph`); the
auto-sync mechanism ENH-2863 landed is the inline `_sync_if_stale()` call inside
`status()`, not a hook.

## Expected Behavior

A touched path whose extension never appears anywhere in the index's `files` table
(i.e. codegraph structurally cannot index that file type) should not count toward
`head_moved`/staleness -- only paths of extensions codegraph actually indexes, that are
missing or content-mismatched, are genuine staleness.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Root Cause

`scripts/little_loops/codequery/codegraph.py`, `_content_aware_head_moved()`
(originally lines 141-169): for each scan-relevant touched path, `expected_hash =
content_hashes.get(path)` is `None` both for "not yet indexed" and "extension codegraph
never indexes," and both cases increment `changed`.

## Fix Applied

Added `_indexed_extensions()`, deriving the set of extensions actually present in the
index's `files` table from the same `content_hashes` dict `status()` already loads.
`_content_aware_head_moved()` now skips a touched path with no `content_hash` entry when
its extension isn't in that set -- it's unindexable, not unindexed.

## Related

Same staleness-detection code path as ENH-2865 (which fixed a different scope --
never-clearing commit-count heuristic) and ENH-2736 (scoped the dirty-file check to
focus_dirs, but not by extension). Auto-sync trigger itself is ENH-2863.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-23 | Priority: P3
