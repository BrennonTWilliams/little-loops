---
id: ENH-3658
type: ENH
title: Handle hand-built history.db paths and context-monitor under a remote history
  backend
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T05:29:44Z'
---

# ENH-3658: Handle hand-built history.db paths and context-monitor under a remote history backend

## Summary

Four sites build `<root>/.ll/history.db` by hand and test `is_file()` / `.exists()` instead of calling `resolve_history_db()`. Under `history.backend.provider: libsql` they silently act on a nonexistent local file. `hooks/scripts/context-monitor.sh` also silently drops its handoff and context-pressure rows under a remote backend. Split out of BUG-3652 (these are not `resolve_history_db()` callers, so its grep-based audit never sees them).

## Current Behavior

- `cli/artifact/serve.py:92`, `cli/artifact/dashboard.py:438`, `cli/doctor_trim.py:373`, `workflow_sequence/io.py:44` build the local path directly and treat a missing file as "no history".
- `hooks/scripts/context-monitor.sh`: `record_handoff_needed()` / `record_context_pressure()` swallow the `HistoryBackendNotLocal` raise with `>/dev/null 2>&1 || true`, so the rows never reach the remote store.

## Expected Behavior

Class (c)-shaped sites refuse or skip explicitly instead of silently reading a nonexistent file: `doctor_trim` calls `refuse_on_remote(db, "trim")`; the artifact and workflow-sequence sites skip with a stated reason on a `RemoteTarget`. Decide per site whether the `context-monitor.sh` rows should reach the remote store (route via the target-aware seam) or stay a documented silent drop.

## Motivation

These sites fail quietly rather than aborting, so they were missed by BUG-3652's `resolve_history_db()` grep audit; under a remote backend they read a nonexistent local file or drop rows without saying so.

## Proposed Solution

Classify each site as class (c) (needs a local file): resolve via `resolve_history_target`, then refuse (`refuse_on_remote`) or skip with a stated reason on a `RemoteTarget`. For `context-monitor.sh`, either route the two `record_*` calls through the target-aware seam or document the silent drop.

## Scope Boundaries

- In scope: the four hand-built `.ll/history.db` paths and `hooks/scripts/context-monitor.sh`.
- Out of scope: `resolve_history_db()` callers (BUG-3652 for startup/write paths, ENH-3657 for readers).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/artifact/serve.py`, `cli/artifact/dashboard.py`, `cli/doctor_trim.py`, `workflow_sequence/io.py`, `hooks/scripts/context-monitor.sh`, `session_store/backend.py` (`_REMOTE_REFUSALS` entry for `trim`).

### Dependent Files (Callers/Importers)
- Callers of the four functions above; `hooks/scripts/context-monitor.sh` calls the `record_*` writers.

### Similar Patterns
- Inline `isinstance(<store>, RemoteTarget)` skips in `worktree_utils.py:export_history_db_env`, `hooks/session_start.py`, `cli/session.py`; `cli/doctor.py:_remote_target()`.

### Tests
- `scripts/tests/test_remote_doctor.py`, `test_remote_operation_matrix.py` (`_REJECTED`), `test_remote_hooks.py` (fixture shape).

### Documentation
- `docs/reference/CONFIGURATION.md` (Remote history backend), `docs/reference/CLI.md`.

### Configuration
- N/A

## Implementation Steps

1. Route the four hand-built paths through `resolve_history_target` / `resolve_history_store`; refuse or skip on a `RemoteTarget` (`doctor_trim` uses `refuse_on_remote(db, "trim")`).
2. Decide the `context-monitor.sh` behavior under remote (route via the target-aware seam, or document the silent drop).
3. Add remote-stub tests and local twins; run `python -m pytest scripts/tests/` with `ruff check` and `mypy` clean.

## Impact

- **Priority**: P4 - these sites fail quietly (no startup abort), so impact is low.
- **Effort**: Small - four sites plus one hook script.
- **Risk**: Low - local behavior unchanged.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] Each of the four hand-built sites resolves through `resolve_history_target` / `resolve_history_store` and handles a `RemoteTarget` explicitly (refuse or skip, with a message).
- [ ] `context-monitor.sh` behavior under remote is decided and documented or implemented.
- [ ] Remote-stub tests cover each site; local behavior unchanged; `python -m pytest scripts/tests/` passes.

## Related

- BUG-3652 (caller audit that surfaced these).
- FEAT-3535 (remote libSQL history backend).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-29 | Priority: P4
