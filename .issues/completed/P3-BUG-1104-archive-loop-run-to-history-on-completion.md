---
discovered_date: 2026-04-13
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1104: Archive loop run to history on completion

## Summary

`PersistentExecutor.run()` never archives the current run to `.loops/.history/` upon completion. Archival only fires at the **start** of the next run via `clear_all()`, so a standalone completed run (the last run, or the only run) leaves no history folder — its state and events sit unarchived in `.loops/.running/` indefinitely.

## Context

**Direct mode** — captured from plan `~/.claude/plans/glittery-yawning-fog.md`.

The `svg-textgrad` run at `20260413-221128` produced artifacts but produced no `.loops/.history/` entry because it was the last run and no subsequent invocation triggered `clear_all()`. The state file sits at `.loops/.running/svg-textgrad.state.json` with `status: "completed"` but was never moved to history.

## Motivation

Without immediate archival on completion, loop runs leave no history entry unless a subsequent run triggers cleanup. This affects:
- **Observability**: `ll-history` and `ll-analyze-loop` cannot surface the last (or only) run's data
- **Debugging**: State files sitting in `.loops/.running/` indefinitely makes it harder to distinguish stale vs. active runs
- **Correctness**: The archival contract should hold regardless of whether another run follows

## Root Cause

**File**: `scripts/little_loops/fsm/persistence.py`  
**Location**: `PersistentExecutor.run()` — line 430

Execution order:
1. `clear_all()` at **start** → archives the *previous* run's files, clears `.running/`
2. FSM executes
3. `save_state(final_state)` → writes final state to `.running/`
4. `return result` — **archive step is missing**

The current run is only archived when step 1 fires on the *next* invocation.

## Steps to Reproduce

1. Run any loop: `ll-loop run svg-textgrad --input description="test"`
2. Observe run completes successfully
3. `ls .loops/.history/` — no entry for this run
4. `ls .loops/.running/` — state and events still present

## Expected Behavior

After `PersistentExecutor.run()` completes, the run's state and events are immediately available in `.loops/.history/<run_id>-<loop_name>/`.

## Current Behavior

Files remain in `.loops/.running/` and no history entry is created unless another run starts.

## Proposed Solution

**File**: `scripts/little_loops/fsm/persistence.py`  
**Line**: 467, after `self.persistence.save_state(final_state)` and before `return result`

```python
self.persistence.save_state(final_state)
self.persistence.archive_run()   # ← add this line
return result
```

`archive_run()` is already idempotent (`exist_ok=True`, `shutil.copy2` overwrites). When the next run starts and calls `clear_all()`, it will call `archive_run()` again (harmless overwrite) then delete `.running/` files.

## Implementation Steps

1. Add `self.persistence.archive_run()` call in `PersistentExecutor.run()` after `save_state(final_state)` and before `return result`
2. Write test `test_run_archives_to_history_on_completion` in `TestPersistentExecutor` following the pattern in `test_clear_all_archives_before_clearing`
3. Run `python -m pytest scripts/tests/test_fsm_persistence.py` to verify fix and no regressions

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Update `docs/guides/LOOPS_GUIDE.md:1781` — change "when a new run starts" to "immediately on completion" to reflect the new archival trigger
5. Update `docs/reference/API.md` — add `archive_run()` row to the `StatePersistence` methods table (currently absent despite being a public method now called directly by `run()`)

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/persistence.py` — add `archive_run()` call in `PersistentExecutor.run()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — instantiates and calls `PersistentExecutor.run()` (ll-loop run / resume CLI)
- `scripts/little_loops/cli/loop/lifecycle.py` — imports `PersistentExecutor` and `StatePersistence` (ll-loop stop / resume lifecycle)
- `scripts/little_loops/cli/loop/info.py` — imports `get_archived_events`, `list_running_loops` from persistence (ll-loop history subcommand)
- `scripts/little_loops/cli/history.py` — implements `ll-history` CLI; reads `.loops/.history/` directly
- `scripts/little_loops/fsm/__init__.py` — re-exports `PersistentExecutor`, `get_loop_history`, `list_run_history`
- `scripts/little_loops/extension.py` — imports from persistence module

### Similar Patterns
- `clear_all()` in `persistence.py` — the existing archive-then-clear pattern to follow

### Tests
- `scripts/tests/test_fsm_persistence.py` — add `test_run_archives_to_history_on_completion` to `TestPersistentExecutor` (class at line 554; insert near end of class, around line 873)

### Documentation
- `docs/ARCHITECTURE.md` — documents `persistence.py` as loop state persistence layer
- `docs/reference/API.md` — `little_loops.fsm.persistence` module reference

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:1781` — states "archived to `.loops/.history/` when a new run starts"; becomes stale after fix — update to "immediately on completion" [Agent 2 finding]
- `docs/reference/API.md:4263–4273` — `archive_run()` absent from `StatePersistence` methods table despite being a public method now called directly by `run()`; add entry [Agent 2 finding]

### Configuration
- N/A

## Impact

- **Priority**: P3 - History entries missing for the last/only completed run; affects observability but does not block loop execution
- **Effort**: Small - Single line addition (`archive_run()`) plus one regression test; no new patterns required
- **Risk**: Low - `archive_run()` is already idempotent (`exist_ok=True`, `shutil.copy2` overwrites); double-archive on next run start is harmless
- **Breaking Change**: No

## Test

**File**: `scripts/tests/test_fsm_persistence.py`  
**Class**: `TestPersistentExecutor` (line 554)  
**Pattern**: Follow `test_clear_all_archives_before_clearing` (line 431) for fixture setup

```python
def test_run_archives_to_history_on_completion(self, simple_fsm: FSMLoop, tmp_loops_dir: Path) -> None:
    """Completed run should be immediately archived without needing a second invocation."""
    mock_runner = MockActionRunner()
    executor = PersistentExecutor(simple_fsm, loops_dir=tmp_loops_dir, action_runner=mock_runner)

    executor.run()

    history_base = tmp_loops_dir / ".history"
    assert history_base.exists()
    run_dirs = [d for d in history_base.iterdir() if d.name.endswith("-test-loop")]
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "state.json").exists()
    assert (run_dirs[0] / "events.jsonl").exists()
```

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`TestPersistentExecutor` class**: `scripts/tests/test_fsm_persistence.py:554` — use existing `simple_fsm` fixture (line 558) and `tmp_loops_dir` fixture (line 578) directly; no new fixtures needed
- **`MockActionRunner`**: `scripts/tests/test_fsm_persistence.py:528` — stand-in for real action runner; default (no `results` arg) returns `ActionResult(output="ok", exit_code=0)`
- **History assertion pattern**: follows `test_clear_all_archives_before_clearing` at `scripts/tests/test_fsm_persistence.py:431` (in `TestArchiveRun`); that test is the canonical pattern for checking history dir contents after archive
- **History dir naming**: `tmp_loops_dir / ".history" / "<run_id>-test-loop"` where `run_id` = `state.started_at` with `:`, `.`, `+` stripped, first 17 chars (e.g., `"2024-01-15T103000"`); using `d.name.endswith("-test-loop")` avoids hardcoding the timestamp

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Documents `persistence.py` as loop state persistence layer |
| architecture | docs/reference/API.md | `little_loops.fsm.persistence` module reference and `StateManager` event docs |

## Labels

`bug`, `fsm`, `persistence`, `captured`

---

## Resolution

**Fixed**: Added `self.persistence.archive_run()` call in `PersistentExecutor.run()` immediately after `save_state(final_state)` and before `return result`. Loop runs are now archived to `.loops/.history/` on completion without requiring a subsequent run to trigger cleanup.

**Changes**:
- `scripts/little_loops/fsm/persistence.py` — added `archive_run()` call after `save_state(final_state)`
- `scripts/tests/test_fsm_persistence.py` — added `test_run_archives_to_history_on_completion` to `TestPersistentExecutor`
- `docs/guides/LOOPS_GUIDE.md:1781` — updated archival trigger description from "when a new run starts" to "immediately on completion"
- `docs/reference/API.md` — added `archive_run()` row to `StatePersistence` methods table

**Verification**: `python -m pytest scripts/tests/test_fsm_persistence.py` — 83 passed

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-14T01:21:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/84dc902b-402a-43d6-a374-4025a88e2ad6.jsonl`
- `/ll:manage-issue` - 2026-04-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/84dc902b-402a-43d6-a374-4025a88e2ad6.jsonl`
- `/ll:ready-issue` - 2026-04-14T01:16:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a31971bd-2eea-42a3-a276-0d2248db490b.jsonl`
- `/ll:confidence-check` - 2026-04-13T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6025c90-d732-4cf7-b6fd-1111edb0a5ba.jsonl`
- `/ll:wire-issue` - 2026-04-13T22:55:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/498e9917-9a07-457d-803c-2e36b312d26c.jsonl`
- `/ll:refine-issue` - 2026-04-13T22:50:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ce8d4e76-d3a9-4651-bf27-c7e9ba762147.jsonl`
- `/ll:format-issue` - 2026-04-13T22:47:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5b03462f-ca2d-4a13-bcdc-c2792cb789a5.jsonl`
- `/ll:capture-issue` - 2026-04-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

## Status

**Completed** | Created: 2026-04-13 | Resolved: 2026-04-13 | Priority: P3
