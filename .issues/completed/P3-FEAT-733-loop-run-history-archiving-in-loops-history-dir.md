---
id: FEAT-733
type: FEAT
priority: P3
discovered_date: 2026-03-13
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 83
---

# FEAT-733: Loop Run History Archiving in `.loops/.history/`

## Summary

When `ll-loop run` starts, it calls `clear_all()` on the previous run's state and events files before execution begins. This permanently destroys the completed run's logs — there is no way to review past loop runs after a new run has started.

## Current Behavior

`PersistentExecutor.run(clear_previous=True)` calls `StatePersistence.clear_all()` at the start of every new run (`persistence.py:StatePersistence.clear_all`), deleting both:
- `.loops/.running/<name>.state.json` — final status, iteration count, duration, captured vars
- `.loops/.running/<name>.events.jsonl` — full event stream (state transitions, evaluations, signals)

Once a loop re-runs, the prior run's data is unrecoverable.

## Expected Behavior

Before clearing `.running/` files, the system archives the completed run's logs to a `.loops/.history/` directory. Each archived run gets a timestamped subdirectory or filename so multiple runs can coexist for review and analysis.

## Motivation

- Debugging loop behavior requires comparing what happened across runs — currently impossible once a second run starts.
- Loop runs can be expensive (multi-hour LLM-driven automation); losing the event log makes post-mortem analysis impossible.
- Future skills like `analyze_log` and `ll:loop-suggester` would benefit from a persistent history of loop runs as a data source.
- Complements FEAT-543 (ll-loop history filtering) and FEAT-724 (session linking) — those features assume history exists.

## Proposed Solution

Archive before clear in `StatePersistence.clear_all()` (or in `PersistentExecutor.run` before calling `clear_all`):

```python
# Proposed archive path scheme:
# .loops/.history/<loop-name>/<started_at_iso>/{state.json, events.jsonl}
# OR flat files:
# .loops/.history/<loop-name>-<started_at_compact>.state.json
# .loops/.history/<loop-name>-<started_at_compact>.events.jsonl

def archive_run(self) -> Path | None:
    """Archive current state+events to .history/ before clearing."""
    state = self.load_state()
    if state is None:
        return None
    ts = state.started_at.replace(":", "").replace(".", "")[:19]  # compact ISO
    archive_dir = self.loops_dir / ".history" / self.loop_name / ts
    archive_dir.mkdir(parents=True, exist_ok=True)
    if self.state_file.exists():
        shutil.copy2(self.state_file, archive_dir / "state.json")
    if self.events_file.exists():
        shutil.copy2(self.events_file, archive_dir / "events.jsonl")
    return archive_dir
```

`clear_all()` should call `archive_run()` first (or `PersistentExecutor.run` should call it before `clear_all`).

Also extend the existing `ll-loop history` subcommand (currently reads `.running/` events for the active run) to list/inspect archived runs from `.loops/.history/` (see FEAT-543).

## Use Case

A developer runs `ll-loop run issue-refinement` overnight. In the morning it completed, but a bug was introduced — the loop made a wrong decision at iteration 12. They run `ll-loop run issue-refinement` again to retry. Without archiving, the first run's events are gone. With archiving, they can inspect `.loops/.history/issue-refinement/<ts>/events.jsonl` to trace what happened at iteration 12.

## Acceptance Criteria

- [x] Before `clear_all()` destroys existing files, the state and events are archived to `.loops/.history/<loop-name>/<run-id>/`
- [x] Archive only occurs when there are files to archive (no empty dirs created for fresh runs)
- [x] The archive directory structure is documented
- [x] `.loops/.history/` is listed in `.gitignore` (or at least documented as a local artifact)
- [x] `ll-loop history <name>` (or similar) can list available archived runs with status/duration
- [x] No change to existing `ll-loop run` CLI interface

## API/Interface

```python
# StatePersistence additions
def archive_run(self) -> Path | None:
    """Archive current run files to .history/ before clearing. Returns archive path."""

# New utility function
def list_run_history(loop_name: str, loops_dir: Path | None = None) -> list[LoopState]:
    """List archived runs for a loop, newest first."""
```

```
# CLI (new subcommand on ll-loop)
ll-loop history <loop-name>          # list archived runs
ll-loop history <loop-name> <run-id> # show events for a specific run
```

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/persistence.py` — add `archive_run()` to `StatePersistence`, call it from `clear_all()` or `PersistentExecutor.run`
- `scripts/little_loops/cli/loop/run.py` — no change if archiving is in persistence layer

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/lifecycle.py` — uses `persistence.load_state()`/`save_state()` but does NOT call `clear_state`/`clear_events` directly; no consistency concern here
- `scripts/little_loops/cli/loop/_helpers.py` — uses `StatePersistence`

### Similar Patterns
- `ll-auto`, `ll-parallel` log to `.claude/projects/` — different approach, not directly reusable

### Tests
- `scripts/tests/` — add tests for `archive_run()`, `list_run_history()`
- Test that `run(clear_previous=True)` archives before clearing
- Test that fresh runs (no existing files) don't create empty archive dirs

### Documentation
- `docs/` — update loop docs to mention `.loops/.history/`

### Configuration
- `.gitignore` — add `.loops/.history/` if logs are considered ephemeral

## Implementation Steps

1. Add `archive_run()` to `StatePersistence` — copy state+events to `.loops/.history/<name>/<ts>/`
2. Call `archive_run()` from `clear_all()` before deleting files
3. Add `list_run_history()` utility function (reads archived state files)
4. Extend existing `ll-loop history` subcommand in CLI to list archived runs from `.history/` (currently reads `.running/` events for current run only)
5. Update `.gitignore` and docs
6. Write tests

## Impact

- **Priority**: P3 - Valuable for debugging and analysis, not blocking any current workflow
- **Effort**: Small - Core archiving is a copy-before-delete; CLI subcommand adds moderate surface
- **Risk**: Low - Additive only; existing `clear_previous=True` behavior is preserved, just augmented
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `fsm-loops`, `persistence`, `captured`

## Verification Notes

- `/ll:verify-issues` - 2026-03-13 - **NEEDS_UPDATE** (corrections applied)
- `StatePersistence.clear_all()` confirmed at `persistence.py:222`; `PersistentExecutor.run()` calls it at line 349
- `archive_run()` and `list_run_history()` confirmed absent — feature not yet implemented
- **Corrected**: `ll-loop history` subcommand already exists (`cli/loop/__init__.py:206-210`); it reads `.running/` events for the current run only — step 4 updated to "extend" rather than "add"
- **Corrected**: `lifecycle.py` only calls `load_state()`/`save_state()`, not `clear_state/clear_events` directly — integration note updated

## Session Log

- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/62cb2f0e-8b9d-493f-88c2-0873e713ce70.jsonl`
- `/ll:format-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/78cb24e4-1ece-44e7-8ec9-f08350ad008b.jsonl`
- `/ll:format-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/371cab6e-a538-4133-b755-4913bc7438c4.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/371cab6e-a538-4133-b755-4913bc7438c4.jsonl`
- `/ll:confidence-check` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/78cb24e4-1ece-44e7-8ec9-f08350ad008b.jsonl`
- `/ll:ready-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/13d273a4-bdb3-4c08-85db-9d7893a38c32.jsonl`

## Resolution

Implemented in full. Core changes:

- `persistence.py`: Added `archive_run()` to `StatePersistence` — copies `.state.json` and `.events.jsonl` to `.loops/.history/<loop_name>/<run_id>/` (run_id is compact ISO from `started_at`). Modified `clear_all()` to call `archive_run()` before deleting. Added `list_run_history()` and `get_archived_events()` utility functions.
- `cli/loop/__init__.py`: Extended `history` subcommand with optional positional `run_id` argument.
- `cli/loop/info.py`: `cmd_history()` now lists archived runs when no `run_id` given, or shows events for a specific archived run.
- `.gitignore`: Added `.loops/.history/` entry.
- Tests: 14 new tests in `TestArchiveRun` class covering all acceptance criteria.

---

**Completed** | Created: 2026-03-13 | Completed: 2026-03-14 | Priority: P3
