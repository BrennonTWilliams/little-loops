---
id: ENH-1752
type: ENH
priority: P2
status: done
completed_at: '2026-05-29T23:30:00Z'
parent: EPIC-1707
discovered_date: 2026-05-27
captured_at: "2026-05-27T20:37:30Z"
discovered_by: capture-issue
labels:
  - enhancement
  - captured
relates_to: [EPIC-1707]
---

# ENH-1752: history.db Read API — history_reader module

## Summary

Add a small, well-typed read-only query module (`little_loops/history_reader.py`, or methods on `session_store.py`) exposing the common queries that ll skills and agents need to consume `.ll/history.db`. This is the foundational prerequisite for all EPIC-1707 consumer work — ENH-1708 and every subsequent skill wiring depends on this API existing before implementing call sites.

## Current Behavior

No consumer-facing read API exists. `session_store.py` is write-oriented; the only readers are CLI tools (`ll-session`, `ll-history`, `ll-ctx-stats`) that are human-facing, not agent-callable. Skills cannot query history.db in any structured way.

## Expected Behavior

A typed Python module exposes at minimum:

```python
find_user_corrections(topic: str, limit: int = 10) -> list[UserCorrection]
recent_file_events(path: str, limit: int = 10) -> list[FileEvent]
search(query: str, kind: str | None = None, limit: int = 10) -> list[SearchResult]
related_issue_events(issue_id: str, limit: int = 20) -> list[IssueEvent]
```

All functions degrade gracefully when `.ll/history.db` is missing, empty, or has no rows newer than 30 days — returning empty lists, never raising.

A CLI wrapper (e.g., `ll-session search --fts <query>` or a new thin subcommand) is defined so skill prompt files can invoke reads via Bash and inject results into context without importing Python directly.

## Motivation

Without a read API, all EPIC-1707 child issues (ENH-1708, ENH-1711, FEAT-1712) must invent their own ad-hoc queries. That leads to inconsistent staleness handling, duplicated connection logic, and prompt bloat from unfiltered results. Centralizing here makes the degradation contract testable once, and every consumer inherits it automatically.

## Proposed Solution

Add `scripts/little_loops/history_reader.py` as a read-only module:
- Opens DB in `PRAGMA journal_mode=WAL; PRAGMA query_only=ON` (safe for concurrent writers)
- Defines return dataclasses (`UserCorrection`, `FileEvent`, `SearchResult`, `IssueEvent`)
- Implements the four query functions with staleness filter (>30d rows excluded by default, overridable)
- Wraps all calls in a try/except that returns `[]` on `OperationalError` (missing DB, locked)

Expose via CLI: extend `ll-session` with a `search --fts <query> [--kind KIND] [--limit N]` subcommand that prints JSON to stdout, so skill prompts can call it with Bash and parse the output.

## Integration Map

### Files to Modify

- `scripts/little_loops/history_reader.py` — new module (primary deliverable)
- `scripts/little_loops/session_store.py` — optionally re-export or delegate if preferred over a separate module
- `scripts/ll_session.py` — add `search` subcommand (or extend existing `search --fts`)

### Dependent Files (Callers/Importers)

- `scripts/little_loops/` consumers: ENH-1708 (refine/ready/confidence skills) will import directly
- Skill prompt files: will call `ll-session search --fts ...` via Bash

### Similar Patterns

- `scripts/little_loops/session_store.py` — existing write-path pattern to follow for DB connection setup
- `ll-session` CLI — existing subcommand pattern to extend

### Tests

- `scripts/tests/test_history_reader.py` — new test file covering:
  - Missing DB → empty list (no raise)
  - Empty tables → empty list
  - Stale rows (>30d) → excluded by default, included when `include_stale=True`
  - FTS5 search returns ranked results
  - `find_user_corrections` with topic filter

### Documentation

- `docs/reference/API.md` — document the read API surface (see ENH-1753)
- `docs/ARCHITECTURE.md` — producer→consumer flow (see ENH-1753)

### Configuration

- N/A — reads from `.ll/history.db` (path from config, defaulting to `.ll/history.db`)

## Implementation Steps

1. Create `scripts/little_loops/history_reader.py` with the four query functions and graceful-degradation wrapper
2. Define return dataclasses and staleness filter logic
3. Extend `ll-session` with `search --fts` subcommand (JSON output)
4. Write `scripts/tests/test_history_reader.py` with missing-DB, empty-table, and stale-row coverage
5. Verify ENH-1708 can import and call the API without modification

## API/Interface

```python
from little_loops.history_reader import (
    find_user_corrections,   # topic: str -> list[UserCorrection]
    recent_file_events,      # path: str -> list[FileEvent]
    search,                  # query: str, kind=None -> list[SearchResult]
    related_issue_events,    # issue_id: str -> list[IssueEvent]
)
```

## Impact

- **Priority**: P2 — Blocks all EPIC-1707 consumer work; should land before ENH-1708
- **Effort**: Small-Medium — New module + tests; no schema changes required
- **Risk**: Low — Read-only, graceful degradation, no changes to existing writers
- **Breaking Change**: No — additive only

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-05-27T20:37:30Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b49625e3-8e47-4c6d-9fa3-75d4dde31106.jsonl`

---

**Open** | Created: 2026-05-27 | Priority: P2
