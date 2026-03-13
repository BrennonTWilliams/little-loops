---
id: FEAT-733
type: FEAT
priority: P3
discovered_date: 2026-03-13
discovered_by: capture-issue
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

Also add a `ll-loop history` subcommand to list/inspect archived runs (see FEAT-543).

## Use Case

A developer runs `ll-loop run issue-refinement` overnight. In the morning it completed, but a bug was introduced — the loop made a wrong decision at iteration 12. They run `ll-loop run issue-refinement` again to retry. Without archiving, the first run's events are gone. With archiving, they can inspect `.loops/.history/issue-refinement/<ts>/events.jsonl` to trace what happened at iteration 12.

## Acceptance Criteria

- [ ] Before `clear_all()` destroys existing files, the state and events are archived to `.loops/.history/<loop-name>/<run-id>/`
- [ ] Archive only occurs when there are files to archive (no empty dirs created for fresh runs)
- [ ] The archive directory structure is documented
- [ ] `.loops/.history/` is listed in `.gitignore` (or at least documented as a local artifact)
- [ ] `ll-loop history <name>` (or similar) can list available archived runs with status/duration
- [ ] No change to existing `ll-loop run` CLI interface

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
- `scripts/little_loops/cli/loop/lifecycle.py` — calls `persistence.clear_state/events` directly in some paths; review for consistency
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
4. Add `ll-loop history` subcommand in CLI (list + show)
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

## Session Log

- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/62cb2f0e-8b9d-493f-88c2-0873e713ce70.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P3
