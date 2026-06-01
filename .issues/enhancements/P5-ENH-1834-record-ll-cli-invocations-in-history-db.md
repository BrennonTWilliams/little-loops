---
id: ENH-1834
type: ENH
priority: P5
status: open
discovered_date: 2026-06-01
captured_at: "2026-06-01T01:10:54Z"
discovered_by: capture-issue
relates_to:
  - EPIC-1707
  - ENH-1833
labels:
  - enhancement
  - captured
parent: EPIC-1707
---

# ENH-1834: Record `ll-` CLI command invocations in history.db

## Summary

When a user runs `ll-loop run`, `ll-auto`, `ll-parallel`, `ll-sprint`, or any other
`ll-` CLI tool, the invocation itself (binary name, args, start timestamp, exit code,
duration) is not persisted to `history.db`. Downstream events (loop state transitions,
issue lifecycle changes) are recorded, but the top-level CLI call that caused them is
not. This makes it impossible to correlate "how many times was `ll-loop run` invoked
this month" or "what was the exit code of the last `ll-sprint` run" from the DB.

## Current Behavior

CLI invocations are not recorded in `history.db`. When a user runs `ll-loop run`,
`ll-auto`, `ll-parallel`, `ll-sprint`, or any other `ll-` CLI tool, the top-level
invocation — binary name, args, start timestamp, exit code, duration — is silently
dropped. Only downstream events (loop state transitions, issue lifecycle changes) are
captured; the triggering CLI call that caused them is absent from the DB.

## Expected Behavior

Each `ll-` CLI invocation writes a row to a new `cli_events` table in `history.db`
containing: `ts`, `binary`, `args` (JSON array, truncated), `exit_code`, and
`duration_ms`. The `ll-session recent --kind cli` subcommand queries and returns
these rows.

## Motivation

CLI invocation history enables usage analytics and debugging. Combined with
`loop_events` and `issue_events`, it provides a complete audit trail: what was
invoked, what states it transitioned through, and what issues it affected.

## Scope Boundaries

- **In scope**: `ll-` CLI entry points, new `cli_events` table, `ll-session recent --kind cli` query support
- **Out of scope**: Skill and agent invocations (tracked separately in ENH-1833), hook events (ENH-1832), non-`ll-` tools, sub-process invocations within a CLI run

## Acceptance Criteria

- A new `cli_events` table records: `ts`, `binary`, `args` (JSON array, truncated),
  `exit_code`, `duration_ms`
- Each `ll-` CLI entry point writes a row at startup (with `exit_code=NULL`) and
  updates it on exit with the actual exit code and duration
- `ll-session recent --kind cli` returns the captured rows
- The write path is a thin wrapper around the existing CLI entry points — no
  changes to core logic required

## API/Interface

```python
@contextmanager
def cli_event_context(
    db_path: Path, binary: str, args: list[str]
) -> Generator[None, None, None]:
    """Insert cli_events row on enter; update exit_code and duration_ms on exit."""
```

Table schema:

```sql
CREATE TABLE cli_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    binary TEXT NOT NULL,
    args TEXT NOT NULL,  -- JSON array, truncated to reasonable length
    exit_code INTEGER,
    duration_ms INTEGER
);
```

## Implementation Steps

1. New migration adding `cli_events` table to `session_store.py`
2. Add `kind='cli'` to `_VALID_KINDS` and `_KIND_TABLE`
3. Add a `cli_event_context(db_path, binary, args)` context manager to
   `session_store.py` that inserts on enter and updates exit_code/duration on exit
4. Wrap `main()` in each CLI entry point with the context manager (or add to a
   shared `cli_main()` wrapper)
5. Tests for the context manager (normal exit, exception exit, duration accuracy)

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — `cli_events` table migration, `cli_event_context()` context manager, `kind='cli'` in `_VALID_KINDS`/`_KIND_TABLE`
- `scripts/little_loops/cli/*.py` — wrap `main()` entry points with `cli_event_context`

### Dependent Files (Callers/Importers)
- TBD — use grep to find entry points: `grep -r "def main" scripts/little_loops/cli/`

### Similar Patterns
- `scripts/little_loops/session_store.py` — existing `loop_events` and `issue_events` tables follow the same write-on-enter/update-on-exit pattern

### Tests
- `scripts/tests/test_session_store.py` — CLI event tests: normal exit, exception exit, duration accuracy

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P5 — Usage analytics improvement; does not block any existing feature
- **Effort**: Small — Thin wrapper reusing existing `session_store.py` infrastructure
- **Risk**: Low — Additive write path only; no changes to core CLI logic required
- **Breaking Change**: No

## Session Log
- `/ll:format-issue` - 2026-06-01T01:23:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ccce6dd-ca36-49fd-8bf7-a050f93f3840.jsonl`
- `/ll:capture-issue` - 2026-06-01T01:10:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

**Open** | Created: 2026-06-01 | Priority: P5
