---
id: ENH-3426
type: ENH
title: Harden cli_event_context history writer so JSON CLIs fail loudly, never silently
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T20:18:42Z'
---

# ENH-3426: Harden cli_event_context history writer so JSON CLIs fail loudly, never silently

## Summary

Every `ll-*` CLI entry point wraps its body in `cli_event_context` (`scripts/little_loops/session_store/writers.py:505-548`), which opens `.ll/history.db`, inserts a `cli_events` row, and updates it with exit code and duration on exit. When `history.db` is very large (the live source checkout's is 7.6 GB) or held by a concurrent writer, a machine consumer of a JSON-emitting command (`ll-queue list --json`, `ll-loop show -j`, `ll-issues ... --json`) can observe the failure mode the ll-console agent reported on 2026-09-09: the process dies with empty stdout. ll-console tolerates it (non-zero exit maps to its `QueueError`), but the contract for a JSON-emitting CLI should be explicit: exit non-zero **and** print a diagnostic to stderr, never a silent empty stdout.

## What Is Verified

- On this checkout, with the same 7.6 GB `history.db`, `ll-queue list --json` returned exit 0 with `[]` on stdout in 0.2 s. The crash **did not reproduce** here. The likely trigger was a concurrent writer holding the SQLite lock while the ll-console session ran it.
- `cli_event_context` already catches `sqlite3.Error` on the insert (writers.py:528) and logs a warning rather than raising, so the insert path is not the hole. Unhandled surfaces remain: `resolve_history_db` / `_pkg.connect` (schema migration or WAL checkpoint on a huge file, writers.py:520-521 runs inside the try but `connect` may block on `busy_timeout` rather than raise), the `finally` UPDATE (writers.py:543 onward), and any non-`sqlite3.Error` exception (e.g. `OSError` from disk-full, `MemoryError`) escaping either.

## Proposed Hardening

1. Establish the failure contract first: ask the ll-console side for the exact stderr and exit code from the observed failure before changing behavior. If stderr was empty on a non-zero exit, that is the defect; if stdout was empty on exit 0, that is a different and worse defect.
2. Make the history writer best-effort on every path: wrap `connect` and the `finally` UPDATE in the same `sqlite3.Error`/`OSError` guard as the insert, with a bounded `busy_timeout` (e.g. 2 s) so a locked or slow DB degrades to "no analytics row" instead of stalling or killing the command.
3. Consider a size guard: when `history.db` exceeds a configurable threshold, skip the `cli_events` write and emit a one-line stderr warning pointing at the compaction command. Do **not** auto-compact or prune (see project rule: raw_events deletion is manual-only).
4. Add a test that simulates a locked DB (second connection holding an exclusive lock) and asserts the wrapped command still emits its JSON on stdout with exit 0, plus a warning on stderr.

## Context

Belongs with the in-flight session-store lifecycle work (FEAT-3417, ENH-3420). Flagged by the ll-console agent as a concern to route here rather than PR themselves.

## Acceptance Criteria

- [ ] Any exception raised by the history writer (connect, insert, finally-update) is caught and logged; the wrapped command's stdout and exit code are unaffected.
- [ ] `busy_timeout` on the `cli_events` connection is bounded and documented.
- [ ] Test: locked `history.db` → `ll-queue list --json` prints valid JSON, exits 0, warning on stderr.
- [ ] If a size guard is added, it is opt-in via config with a documented default and never deletes data.


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

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

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Current Pain Point

## Success Metrics

## Scope Boundaries

## Backwards Compatibility

## API/Interface

```python
# Example interface/signature
```


## Session Log
- `/ll:capture-issue` - 2026-09-09T20:18:50 - `c67d0e9c-2f18-4a69-ac01-c129392655e2.jsonl`
