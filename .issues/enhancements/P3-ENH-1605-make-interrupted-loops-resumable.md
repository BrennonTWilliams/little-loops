---
id: ENH-1605
title: Make interrupted loops resumable
type: ENH
priority: P3
status: done
captured_at: '2026-05-18T05:35:25Z'
completed_at: '2026-05-18T10:30:28Z'
discovered_date: '2026-05-18'
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-1605: Make interrupted loops resumable

## Summary

`ll-loop stop` and clean Ctrl-C (SIGINT) write `status = "interrupted"`, which `ll-loop resume` currently refuses to pick up. Only `"running"` and `"awaiting_continuation"` are treated as resumable. This creates a counterintuitive inversion: a hard kill/crash leaves a loop in `"running"` status (resumable), while a graceful stop produces `"interrupted"` (not resumable). The fix is to add `"interrupted"` to the resumable-status set so a clean pause is at least as recoverable as a crash.

## Current Behavior

In `scripts/little_loops/fsm/persistence.py:607`:

```python
if state.status not in ("running", "awaiting_continuation"):
    return None  # not resumable
```

`ll-loop stop` and first-Ctrl-C write `status = "interrupted"` and then archive the run. `ll-loop resume` silently declines to resume it.

A crash/SIGKILL leaves `status = "running"` on disk, which IS resumable — meaning the accidental path is more recoverable than the intentional one.

## Expected Behavior

`ll-loop resume <name>` should resume a loop that was stopped via `ll-loop stop` or Ctrl-C, re-entering the FSM at `current_state` exactly as it does for `"running"` and `"awaiting_continuation"` loops.

## Motivation

Users who stop a loop intentionally (to free resources, handle a distraction, or end a session) should be able to pick it up later. The current behavior punishes clean shutdowns. The graceful stop is the right path — it should be the most recoverable one.

## Proposed Solution

1. Add `"interrupted"` to the resumable-status check in `PersistentExecutor.resume()` (`persistence.py:607`).
2. Stop archiving the run in `PersistentExecutor.run()` when `terminated_by == "signal"` — or defer archiving until after the user has had a chance to resume. Currently `persistence.archive_run()` is called immediately after writing `"interrupted"`, which moves the state file to `.loops/.history/` and makes it invisible to `_find_instances()` (which only scans `.loops/.running/`).
3. Optionally surface `"interrupted"` loops in the `ll-loop list` output with a distinct `[paused]` label to hint that `resume` is available.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor.resume()` line 607 (resumable-status check), `PersistentExecutor.run()` (archive-on-signal logic near line 569)
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_stop()` may need to skip or defer `archive_run()` so the state file stays in `.loops/.running/` for `_find_instances()` to find

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` calls `_find_instances()` then `executor.resume()`
- `scripts/little_loops/fsm/persistence.py` — `_reconcile_stale_runs()` treats `"interrupted"` as terminal; needs updating if we want stale interrupted runs kept longer
- `scripts/little_loops/cli/loop/run.py` — calls `_reconcile_stale_runs()` directly at line 208; every `ll-loop run` invocation triggers the startup sweep, so changing `terminal_statuses` behavior affects this call site [Agent 1 finding]
- `scripts/little_loops/fsm/__init__.py` — re-exports `PersistentExecutor`, `StatePersistence`, `LoopState`; if `RESUMABLE_STATUSES` is introduced as a public constant, it must be added to this module's exports [Agent 1 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical: There is a SECOND status filter in `cmd_resume()` that also needs updating.**

`lifecycle.py` lines 330–332 has its own filter that runs before `executor.resume()`:
```python
resumable = [
    (iid, s) for iid, s in instances if s.status in ("running", "awaiting_continuation")
]
```
If `resumable` is empty (which it will be for `"interrupted"` loops), `cmd_resume()` may silently pass a `None` state to `executor.resume()`. Both this filter AND `persistence.py:607` must be updated.

**`archive_run()` is a copy, not a move.**

The issue states archive moves files out of `.running/`, but `StatePersistence.archive_run()` (persistence.py lines 304–341) uses `shutil.copy2()` — it copies to `.loops/.history/` and leaves the originals in `.running/`. The actual cleanup of `.running/` source files happens in `clear_all()` → `clear_state()` + `clear_events()`. `PersistentExecutor.run()` calls `archive_run()` directly (not `clear_all()`), so state files remain in `.running/` after a stop.

**The real discovery problem is `_reconcile_stale_runs()`, not `archive_run()`.**

`_reconcile_stale_runs()` (persistence.py lines 350–409) has:
```python
terminal_statuses = {"completed", "failed", "interrupted", "timed_out"}
```
Any `"interrupted"` file in `.running/` is treated as unconditionally stale — `clear_all()` is called on it without checking PIDs or whether the user might want to resume. This sweeps interrupted state files away on the **next loop startup**, which is the real reason they become invisible to `_find_instances()`.

**`"interrupted"` is also set for `terminated_by == "max_iterations"` (persistence.py line 569).**

Consider whether max-iterations-exhausted loops should also be resumable, or only signal-stopped loops. This is a design decision for the implementer. If only signal-interrupted loops should be resumable, a finer-grained distinction (e.g., a new `"paused"` status for signal stops vs. `"interrupted"` for max_iterations) may be warranted. The simpler path is to make all `"interrupted"` resumable.

**No named `RESUMABLE_STATUSES` constant exists yet.**

The API section proposes `RESUMABLE_STATUSES = {"running", "awaiting_continuation", "interrupted"}` but currently both locations use inline tuple literals. Introducing the named constant is a good refactor but is additive; the check can also just be extended inline.

### Similar Patterns
- `"awaiting_continuation"` is already resumable and uses the same restore path — the interrupted resume follows the same code path

### Tests
- `scripts/tests/test_persistence.py` (or equivalent) — add test: stop a loop, assert `_find_instances()` returns it, assert `resume()` succeeds
- `scripts/tests/test_loop_lifecycle.py` — add test for the Ctrl-C → resume round-trip
- `scripts/tests/test_fsm_persistence.py:726` — `test_resume_returns_none_for_interrupted` explicitly tests the current broken behavior (returns None for interrupted); **must be inverted** to assert resume succeeds after this fix
- `scripts/tests/test_fsm_persistence.py:1649` — `test_signal_interrupted_loop_can_be_resumed` currently patches `state.status = "running"` before calling resume; **remove the manual patch** after the fix so the test exercises the real path
- `scripts/tests/test_cli_loop_lifecycle.py` — `TestCmdResumeMultiInstance` (line 1765) covers multi-instance guard; add a parallel test for a single interrupted instance being successfully resumed via `cmd_resume()`
- `scripts/tests/test_ll_loop_state.py:167` — `test_stop_interrupted_loop_returns_error` tests that stopping an already-interrupted loop returns exit 1; verify this still passes (stop behavior unchanged)
- `scripts/tests/test_fsm_persistence.py:2036` — `TestReconcileStaleRuns.test_terminal_status_file_is_archived` asserts `count == 4` with `"interrupted"` in the swept set; **WILL BREAK** when `"interrupted"` is removed from `terminal_statuses` — update status list to `("completed", "failed", "timed_out")` and expected count to 3; add a new `test_interrupted_status_file_not_swept` test following the `_write_state()` helper pattern in that class [Agent 1 + 3 finding]
- `scripts/tests/test_cli_loop_queue.py` — patches `_reconcile_stale_runs` to a no-op during `cmd_run` tests; verify it still passes after `terminal_statuses` set change (no assertion changes expected, but confirm no indirect breakage) [Agent 3 finding]

### Documentation
- `docs/reference/API.md` — update status value table if it documents resumability
- Any `ll-loop` man page / help text that lists resumable statuses
- `docs/reference/CLI.md` — `ll-loop resume` section (~line 431): currently implies resumable means running/awaiting_continuation; add explicit mention of `"interrupted"` as a resumable status [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md` — "Scope conflict blocks `ll-loop run` after an interrupted loop" (~line 712): describes `_reconcile_stale_runs` sweeping `"interrupted"` files at next startup; behavior changes once interrupted files no longer get swept — update this section to reflect the new path [Agent 2 finding]
- `skills/cleanup-loops/SKILL.md` — `NEEDS CLEANUP — stale-interrupted` section: currently categorizes interrupted loops as cleanup-only targets; after fix they are resumable — update to offer `ll-loop resume` as the first option before cleanup [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. In `persistence.py:607`, extend the inline tuple (or introduce `RESUMABLE_STATUSES`) to include `"interrupted"`: `state.status not in ("running", "awaiting_continuation", "interrupted")`.
2. In `lifecycle.py:330-332`, update `cmd_resume()`'s own filter from `s.status in ("running", "awaiting_continuation")` to also include `"interrupted"`. Both the CLI filter and the executor guard must match.
3. Update `_reconcile_stale_runs()` (persistence.py lines 350–409): remove `"interrupted"` from `terminal_statuses` (or add a live-PID check before sweeping), so interrupted state files survive to the next startup and remain discoverable by `_find_instances()`.
4. Decide whether `terminated_by == "max_iterations"` loops should also be resumable (currently also sets `"interrupted"`). If not, consider a distinct status (e.g. `"paused"`) for signal-only stops — or accept that max-iterations loops are also resumable.
5. Invert `test_resume_returns_none_for_interrupted` (`test_fsm_persistence.py:726`) to assert that resume now succeeds for interrupted state.
6. Remove the manual status patch in `test_signal_interrupted_loop_can_be_resumed` (`test_fsm_persistence.py:1649`) and verify the round-trip passes without it.
7. Add a `cmd_resume()` CLI-level test for a single interrupted instance (model after `TestCmdResumeMultiInstance` in `test_cli_loop_lifecycle.py:1765`).
8. Optionally update `info.py` to render `[paused]` instead of `[interrupted]` in `ll-loop list` to hint that resume is available — coloring already uses yellow (`"33"`), so this is a label-only change at `cmd_list()` line 67.
9. Update `docs/guides/LOOPS_GUIDE.md` troubleshooting section and `docs/reference/API.md` status value table to reflect that `"interrupted"` is now resumable.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `test_fsm_persistence.py:2036` (`test_terminal_status_file_is_archived`): change status list to `("completed", "failed", "timed_out")`, adjust expected count to 3; add `test_interrupted_status_file_not_swept` following the `_write_state()` + `monkeypatch._process_alive` pattern in `TestReconcileStaleRuns`
11. Update `docs/reference/CLI.md` `ll-loop resume` section (~line 431) to explicitly list `"interrupted"` as a resumable status
12. Update `docs/development/TROUBLESHOOTING.md` "Scope conflict" section (~line 712) to reflect that `_reconcile_stale_runs` no longer sweeps `"interrupted"` files at startup
13. Update `skills/cleanup-loops/SKILL.md` `stale-interrupted` category to present `ll-loop resume` as the first recommended action
14. If `RESUMABLE_STATUSES` constant is introduced and made public, add it to `scripts/little_loops/fsm/__init__.py` exports
15. Verify `scripts/tests/test_cli_loop_queue.py` still passes unchanged after the `terminal_statuses` set modification

## Scope Boundaries

**In scope:**
- Adding `"interrupted"` to the resumable-status set in `PersistentExecutor.resume()`
- Fixing archive timing so interrupted loops remain in `.loops/.running/` for `_find_instances()` to discover
- Updating `_reconcile_stale_runs()` to not treat `"interrupted"` + dead-PID as stale (keep available for resume)
- Optionally surfacing `"interrupted"` loops in `ll-loop list` with a `[paused]` label

**Out of scope:**
- Changing crash/SIGKILL recovery behavior (already handled via `"running"` status)
- Introducing new loop status values beyond adding `"interrupted"` to the resumable set
- Modifying FSM state-transition logic or execution behavior during the loop run
- Changing semantics of terminal statuses (`"completed"`, `"failed"`, `"cancelled"`)

## API/Interface

```python
# persistence.py — updated resumable check
RESUMABLE_STATUSES = {"running", "awaiting_continuation", "interrupted"}

def resume(self) -> ExecutionResult | None:
    state = self.persistence.load_state()
    if state is None or state.status not in RESUMABLE_STATUSES:
        return None
    ...
```

## Impact

- **Priority**: P3 - Quality-of-life fix; no data loss, but frustrating when discovered
- **Effort**: Small - Two-line logic change + archive-timing adjustment + tests
- **Risk**: Low - Additive change; existing resumable paths unchanged
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`fsm-loops`, `loop-lifecycle`, `captured`

## Resolution

Implemented in commit `improve(fsm): make interrupted loops resumable (ENH-1605)`.

Changes made:
- `persistence.py`: Introduced `RESUMABLE_STATUSES` constant; updated `PersistentExecutor.resume()` to include `"interrupted"`; removed `"interrupted"` from `_reconcile_stale_runs()` terminal_statuses so interrupted state files survive to the next startup
- `lifecycle.py`: Updated `cmd_resume()` filter to use `RESUMABLE_STATUSES`
- `fsm/__init__.py`: Exported `RESUMABLE_STATUSES`
- `info.py`: `ll-loop list` now displays `[paused]` instead of `[interrupted]`
- Tests: Inverted `test_resume_returns_none_for_interrupted` → `test_resume_succeeds_for_interrupted`; removed manual status patch from `test_signal_interrupted_loop_can_be_resumed`; updated `test_terminal_status_file_is_archived` (count 4→3); added `test_interrupted_status_file_not_swept` and `TestCmdResumeInterrupted`
- Docs: Updated `CLI.md`, `TROUBLESHOOTING.md`, and `skills/cleanup-loops/SKILL.md`

## Status

**Done** | Created: 2026-05-18 | Completed: 2026-05-18 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-05-18T10:26:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/35aa2cdf-82c0-4afe-a7e1-9ac197eb4e1c.jsonl`
- `/ll:confidence-check` - 2026-05-18T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/51846938-a454-4013-b926-e1337eda99a7.jsonl`
- `/ll:wire-issue` - 2026-05-18T10:21:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/65061985-d2a5-47c2-8a86-4d4faf8aca60.jsonl`
- `/ll:refine-issue` - 2026-05-18T10:16:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/59ae7671-b0eb-46e6-99f8-da6fab58992a.jsonl`
- `/ll:format-issue` - 2026-05-18T05:38:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3ddc6287-f781-4278-a8a4-03871998cfc3.jsonl`

- `/ll:capture-issue` - 2026-05-18T05:35:25Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a80e31cf-a675-4c97-bce5-05347c0aadf2.jsonl`
- `/ll:manage-issue` - 2026-05-18T10:30:28Z - implemented all 15 wiring steps; 180 tests pass
