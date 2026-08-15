---
id: BUG-3181
type: BUG
title: ll-mcp history_search reads .ll/history.db from cwd, ignoring the resolved
  project root
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T16:15:00Z'
parent: EPIC-3127
labels:
- mcp
- multi-host
completed_at: '2026-08-15T16:31:35Z'
---

# BUG-3181: ll-mcp history_search reads .ll/history.db from cwd, ignoring the resolved project root

## Summary

`_tool_history_search` accepts `project_root` and never uses it: it calls
`history_reader.search(query, kind=kind, limit=limit)`, whose `db` parameter defaults to
`DEFAULT_DB_PATH` — the cwd-relative `Path(".ll/history.db")` (`session_store/db.py:15`).
The handler's docstring asserts "`history.db` is process-global, not project-rooted, so
`project_root` is accepted (for dispatch uniformity with the other handlers) but unused",
which is false.

Verified: `history_reader.search("issue", limit=5)` returns 5 rows from the project cwd
and 0 from `/tmp`.

ENH-3171's own Summary names this surface as a symptom of the bug it was closing
("`issues_query` returns `[]`, `deps_check` reports a clean graph, `resources/list` is
empty, `history_search` finds nothing"), so this call site was in scope and was missed.

Note the shared resolver cannot fix this as-is: `resolve_history_db(project_root /
DEFAULT_DB_PATH)` discards the passed path because it is *default-shaped*
(`_is_default_shaped`), then re-derives the root from `resolve_ll_dir()`, which walks up
from `Path.cwd()`. The root must be threaded into that resolution rather than passed as a
path.

## Expected Behavior

`history_search` reads the DB for the resolved project root, honoring the established
precedence `LL_HISTORY_DB` -> `history.db_path` config -> `<project_root>/.ll/history.db`,
with the root anchored explicitly rather than derived from cwd.


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]
