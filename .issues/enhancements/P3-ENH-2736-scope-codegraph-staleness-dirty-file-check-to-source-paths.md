---
id: ENH-2736
type: enhancement
status: open
priority: P3
captured_at: "2026-07-22T17:06:04Z"
discovered_date: 2026-07-22
discovered_by: capture-issue
---

# ENH-2736: Scope codegraph staleness dirty-file check to source-relevant paths

## Summary

`ll-code status` (via `CodegraphProvider.status()`) reports the codegraph index
as `stale` even when the index content is fully current, because the
staleness check counts *every* line of `git status --porcelain` output
repo-wide — including untracked/dirty files that have nothing to do with
source code (e.g. `.ll/decisions.d/*.json` fragments).

## Current Behavior

In `scripts/little_loops/codequery/codegraph.py`, `status()` computes:

```python
dirty_raw = _git(root, "status", "--porcelain")
dirty_files = len(dirty_raw.splitlines()) if dirty_raw else 0

is_fresh = head_moved == 0 and dirty_files == 0
```

`dirty_files` is a raw count of all porcelain lines with no path filtering.
Observed live: two untracked `.ll/decisions.d/*.json` fragments made
`ll-code status` report `freshness: stale` immediately after a fresh
`codegraph sync` (`head_moved=0`, `indexed_at` current), because
`dirty_files=2`. The index was in fact fully up to date — the signal was a
false positive.

## Expected Behavior

The dirty-file check should only count files that are relevant to the
indexed source tree (i.e. paths that would affect `nodes`/`edges` content —
tracked source files matching the provider's scan scope), not every
untracked/modified file anywhere in the repo. Non-code paths such as
`.ll/`, `.issues/`, `thoughts/`, and other config/metadata directories
should not be able to flip freshness to `stale` on their own.

## Motivation

A staleness signal that can be tripped by unrelated files (decision logs,
scratch notes, issue files) undermines trust in `ll-code status`: users see
`stale` and either ignore it (defeating the point of the check) or waste
time re-syncing an index that was never actually behind. Under
`policy: strict` this is worse — it would make the codegraph provider report
`available: false` and silently fall back to the grep/AST provider for a
reason unrelated to code staleness at all.

## Proposed Solution

Filter `git status --porcelain` output before counting, keeping only paths
that fall under the provider's effective scan scope (e.g. reuse
`scan.focus_dirs`/`scan.exclude_patterns` from `BRConfig`, or restrict to
extensions/paths the codegraph index actually covers per its `files` table
languages). Alternatively, cross-reference dirty paths against
`SELECT path FROM files` in the codegraph DB — only count a dirty file as
staleness-relevant if it's a path the index tracks.

## Impact

- **Priority**: P3 - Not blocking (default `policy: warn` still serves
  results), but produces a persistently misleading signal and would degrade
  functionality under `policy: strict`.
- **Effort**: Small - localized to `CodegraphProvider.status()` in
  `scripts/little_loops/codequery/codegraph.py`.
- **Risk**: Low - read-only status computation, no schema or provider
  interface changes.
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| docs/reference/API.md | Documents `little_loops.codequery` provider protocol and `CodegraphProvider.status()` freshness semantics |

## Session Log
- `/ll:capture-issue` - 2026-07-22T17:06:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cc696539-106a-4954-8d48-1f64b8a112c0.jsonl`

---

## Status

**Open** | Created: 2026-07-22 | Priority: P3
