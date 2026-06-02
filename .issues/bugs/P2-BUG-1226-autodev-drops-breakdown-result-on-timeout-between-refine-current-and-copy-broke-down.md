---
discovered_date: 2026-04-21
completed_at: 2026-04-21T15:26:02Z
discovered_by: analyze-loop
source_loop: autodev
source_state: copy_broke_down
confidence_score: 100
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
status: done
---

# BUG-1226: autodev drops breakdown result on timeout between refine_current and copy_broke_down

## Summary

When the `autodev` loop's 8-hour wall-clock timeout fires in the narrow window between a
`refine_current` sub-loop completing and the `copy_broke_down` state starting, the breakdown
result is silently discarded. The sub-loop correctly wrote `1` to
`.loops/tmp/recursive-refine-broke-down`, but the parent loop timed out before
`copy_broke_down` could copy that flag into `.loops/tmp/autodev-broke-down`. As a result,
`check_broke_down` never ran, child detection never ran, and the issue (`FEAT-1201`) was
left off both the passed and skipped lists — effectively lost from the session.

## Loop Context

- **Loop**: `autodev`
- **State**: `copy_broke_down` (never executed)
- **Signal type**: timeout before routing completes
- **Occurrences**: 1 (observed 2026-04-21 session)
- **Last observed**: `2026-04-21T09:10:36+00:00`

## Root Cause

The sub-loop (`refine-to-ready-issue`) for `FEAT-1201` exhausted its two refine attempts
without passing `check_readiness`, hit the `check_refine_limit` → `breakdown_issue` path,
ran `/ll:issue-size-review FEAT-1201 --auto` (117s), and wrote the `recursive-refine-broke-down`
flag. The sub-loop then completed normally (`terminated_by: terminal`). The parent `autodev`
loop issued a `route from=refine_current to=copy_broke_down` at 09:10:36.552491 — but the
8-hour timeout fired at 09:10:36.552553, 62 µs later, before the state could enter.

## History Excerpt

Events leading to this signal:

```json
[
  {"event": "state_enter",    "ts": "2026-04-21T09:08:39.526042+00:00", "state": "breakdown_issue", "iteration": 15},
  {"event": "action_complete","ts": "2026-04-21T09:10:36.547092+00:00", "exit_code": 0, "duration_ms": 117005, "is_prompt": true},
  {"event": "route",          "ts": "2026-04-21T09:10:36.547319+00:00", "from": "breakdown_issue", "to": "write_broke_down"},
  {"event": "state_enter",    "ts": "2026-04-21T09:10:36.547572+00:00", "state": "write_broke_down", "iteration": 16},
  {"event": "action_complete","ts": "2026-04-21T09:10:36.551770+00:00", "exit_code": 0, "duration_ms": 3, "is_prompt": false},
  {"event": "route",          "ts": "2026-04-21T09:10:36.551959+00:00", "from": "write_broke_down", "to": "done"},
  {"event": "loop_complete",  "ts": "2026-04-21T09:10:36.552034+00:00", "final_state": "done", "iterations": 16, "terminated_by": "terminal", "depth": 1},
  {"event": "route",          "ts": "2026-04-21T09:10:36.552491+00:00", "from": "refine_current", "to": "copy_broke_down"},
  {"event": "loop_complete",  "ts": "2026-04-21T09:10:36.552553+00:00", "final_state": "copy_broke_down", "iterations": 236, "terminated_by": "timeout"}
]
```

## Expected Behavior

When the loop times out while `final_state` is `copy_broke_down` (i.e. the state was
targeted but never executed), the executor should either:

1. **Execute the pending state before honoring the timeout** when the timeout fires
   between a sub-loop return and the next shell action (a safe, fast-path guarantee
   for non-prompt states like `copy_broke_down`).
2. **Or emit a resume hint** in `loop_complete` that names the interrupted issue ID so
   a subsequent `ll-loop run autodev` with the same input can skip already-processed
   issues and retry the one that was mid-flight.

At minimum, the `done` state's summary should flag that `FEAT-1201` was neither passed
nor skipped, so the user knows to re-queue it.

## Proposed Fix

Two-part fix: a scoped executor change (closes the race) plus a lightweight
autodev-local signal (covers timeouts outside the race window). Full resume
support was considered and rejected as premature — the autodev queue state
(baseline IDs, broke-down flag, pre-ids) is not yet designed for durability.

### Part 1 — Flush one pending non-prompt state on timeout (executor)

In `scripts/little_loops/fsm/executor.py` around the timeout check at the top
of the run loop (`executor.py:237-240`), when the timeout fires *and* a `route`
event was just emitted to a non-terminal state whose action is `shell` (not
`slash_command`, not a sub-loop), execute that one state before finishing with
`terminated_by: "timeout"`. Single-step only — no cascade; if the flushed
state routes to another non-prompt state, honor the timeout there.

Why bounded to shell actions: `copy_broke_down` and similar handshake states
run in ~5 ms, so running one after timeout detection is safe. Slash commands
and sub-loops can take minutes and would violate the timeout budget.

### Part 2 — Record mid-flight issue for the done summary (autodev.yaml)

- `dequeue_next` writes the popped issue ID to `.loops/tmp/autodev-inflight`.
- `enqueue_or_skip` and `enqueue_children` clear that file when the issue is
  resolved or decomposed.
- `done` checks `autodev-inflight`; if non-empty it prints a warning alongside
  the passed/skipped lists naming the interrupted issue.

This catches timeouts Part 1 cannot — e.g. timeout fires while a sub-loop's
slash command is running — so the user always knows which issue to re-queue.

### Rejected — persistent resume

Storing dequeued-but-not-finished state so `ll-loop run autodev` can prepend
it automatically would require snapshotting queue state, baseline IDs, and
handshake flags, plus defining stale-resume semantics. Not justified for a
race that's been observed once; revisit if timeouts become common.

## Integration Map

_Populated by `/ll:refine-issue` — all line numbers verified against current source._

### Files to Modify

**Part 1 — Executor flush**
- `scripts/little_loops/fsm/executor.py` — insert flush logic at the top of the run loop between the timeout check and `_finish("timeout")`. The race window is bounded by:
  - `executor.py:237-240` — wall-clock timeout check (runs at top of every iteration, BEFORE `state_enter`)
  - `executor.py:336-342` — `route` event emission at end of previous iteration
  - `executor.py:344-345` — `self.current_state = resolved_next` (pending state is already stored here)
  - `executor.py:303-309` — `state_enter` emission (what the timeout prevents from running)
  - `executor.py:851-864` — `_action_mode(state)` dispatch; use branch 3 (`action_type == "shell"`) to gate the flush
  - `executor.py:1095-1113` — `_finish()` emits `loop_complete` with `terminated_by` and `final_state = self.current_state`

**Part 2 — autodev `inflight` handshake**
- `scripts/little_loops/loops/autodev.yaml:53-83` — `dequeue_next`: after `echo "$CURRENT"`, also write `printf '%s' "$CURRENT" > .loops/tmp/autodev-inflight`
- `scripts/little_loops/loops/autodev.yaml` — `enqueue_or_skip` and `enqueue_children` states: clear the flag (`rm -f .loops/tmp/autodev-inflight`) on success paths
- `scripts/little_loops/loops/autodev.yaml:379-398` — `done`: read `autodev-inflight`; if non-empty, emit a warning line alongside Passed/Skipped summaries (follow the existing `$${VAR:-none}` escaping convention)
- `scripts/little_loops/loops/autodev.yaml:33-51` — `init`: add `rm -f .loops/tmp/autodev-inflight` to the reset block alongside the existing `rm -f .loops/tmp/autodev-broke-down`

### Dependent Files (Callers / Integration)
- `scripts/little_loops/fsm/executor.py:366-430` — `_execute_sub_loop()`; the sub-loop returns `terminated_by == "terminal"`, `final_state == "done"` → routes to `state.on_yes` (`copy_broke_down`), triggering the race window on return from `refine-to-ready-issue`
- `scripts/little_loops/fsm/executor.py:444-447` — `_execute_state()` sub-loop dispatch
- `scripts/little_loops/fsm/types.py:32` — `ExecutionResult.terminated_by` field (values: `terminal`, `timeout`, `signal`, `max_iterations`, `error`)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:232-236` — `write_broke_down` (child's counterpart that writes `recursive-refine-broke-down`; do NOT modify — Part 1 exists precisely to flush the parent's `copy_broke_down` without touching the child)
- `scripts/little_loops/loops/autodev.yaml:100-113` — `copy_broke_down` state (unchanged; it's the flushed state itself)
- `scripts/little_loops/loops/autodev.yaml:248-271` — `check_broke_down` (downstream reader; unaffected by fix)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/persistence.py:417-418` — `PersistentExecutor._handle_event` calls `_save_state()` on every `state_enter` event; after Part 1 the flush emits `state_enter` for `copy_broke_down` before `_finish("timeout")`, triggering an extra `_save_state()` call during the timeout path. The double-save is safe (final `loop_complete` handler overwrites status to `"timed_out"` via `persistence.py:483-484`), but verify the ordering is correct during implementation.

### Similar Patterns to Follow

**Existing handshake flag YAML** (models for Part 2):
- `refine-to-ready-issue.yaml:232-236` — single-line flag write: `printf '1' > .loops/tmp/recursive-refine-broke-down`
- `autodev.yaml:100-113` — flag copy with fallback (`if [ -f … ]; then cp …; else printf '0' > …; fi`)
- `autodev.yaml:248-271` — flag read with fallback: `cat … 2>/dev/null || echo 0`
- `autodev.yaml:33-51` (`init`) and `autodev.yaml:53-83` (`dequeue_next`) — both use `rm -f` to reset flags at start of each iteration; `autodev-inflight` should be reset alongside `autodev-broke-down`

**`done` summary conventions** (`autodev.yaml:379-398`):
- Aggregates via `cat .loops/tmp/autodev-passed.txt 2>/dev/null | grep -v '^[[:space:]]*$' | sort -u`
- Escapes `${VAR:-none}` as `$${VAR:-none}` (YAML interpolation → shell)
- Uses `printf` (not `echo`) for deterministic formatting
- Emits `=== Autodev Summary ===` header, then `Passed`, `Skipped`. New warning should slot in as an optional line (e.g. `printf 'WARNING: mid-flight issue not recorded: %s\n' "$INFLIGHT"`)

### Tests

**Primary** — `scripts/tests/test_fsm_executor.py`
- `TestTimeoutHandling` class at lines 1918-2113 is the home for the new repro test
- `test_loop_timeout_preserves_state` (lines 2074-2113) is the closest template — it already asserts `final_state == "step2"` after a timeout fires between `route` and `state_enter`. The new flush test inverts that expectation: after flush, `final_state` should be `"step2"` but an additional `state_enter` event should have been emitted AND the `step2.sh` action should have run
- `MockActionRunner` fixture (lines 30-92) supports `use_indexed_order=True` with a `.results` list — use this to give different results to `refine_current` (sub-loop) vs `copy_broke_down` (shell) in the repro
- Time injection pattern: `patch("little_loops.fsm.executor.time.time", side_effect=mock_time)` with a `time_values` list + `call_count` closure — size the list to match the exact number of `time.time()` calls the executor makes (start + one check per iteration top + one for flush)
- Event extraction idiom: `next(e for e in events if e["event"] == "state_enter" and e["state"] == "step2")` confirms the flushed state entered before `loop_complete`

**Secondary** — `scripts/tests/test_builtin_loops.py`
- `TestAutodevLoop` class at lines 1009-1243 is the home for YAML structural tests
- Template: `test_init_references_autodev_queue` (pattern for asserting substring-in-action-string)
- Template: `test_broke_down_flag_copied_to_autodev_namespace` (pattern for asserting cross-state handshake)
- New tests should assert: `dequeue_next` writes `autodev-inflight`; `enqueue_or_skip` and `enqueue_children` clear it; `init` resets it; `done` references it

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py:2074-2113` (`test_loop_timeout_preserves_state`) — **WILL BREAK after Part 1**: the test's `step2` state is a shell-action state; the flush WILL execute `step2.sh` before `_finish("timeout")`. Must update: (a) add an extra value to `time_values` list for the flush's `time.time()` call, (b) assert `mock_runner.calls` includes `step2.sh`, (c) assert `state_enter` for `step2` appears in events before `loop_complete`, (d) update docstring. Consider splitting into two tests: one for shell-action states (flushed) and one for slash_command/sub-loop states (not flushed).
- `scripts/tests/test_fsm_persistence.py:847-871` (`test_final_status_timed_out_on_timeout`) — **review needed**: uses `elapsed_offset_ms = 999_999_999` to force timeout before any routing event is emitted. The flush guard must explicitly check "a `route` event was emitted this iteration" (not just "current_state is a shell-action state") or this test will false-break. Verify the guard condition during implementation; likely safe but must be confirmed.

### Configuration / Schema
- No schema changes required — `action_type: shell` and `_action_mode` branches already exist
- No `config-schema.json` changes — Part 2 uses only tmp file conventions

### Documentation
- `docs/reference/EVENT-SCHEMA.md` — `loop_complete` event documentation may want a note that `final_state` can name a state that never had a `state_enter` (current behavior) vs. after Part 1, the flushed state will have one

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:458` — autodev Notes section describes tmp file conventions (`autodev-broke-down`, `autodev-queue.txt`, etc.); after Part 2, add description of `autodev-inflight` — written by `dequeue_next`, cleared by `enqueue_or_skip`/`enqueue_children`/`init`, read by `done` for mid-flight warning output
- `docs/reference/schemas/loop_complete.json` — generated JSON schema for the `loop_complete` event (referenced by `docs/reference/EVENT-SCHEMA.md`); the `final_state` field description should note the semantics change after Part 1: before the fix, `final_state` could name a state that never had `state_enter` emitted; after Part 1, the flushed state will always have `state_enter` before `loop_complete`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Verify `persistence.py:417-418` interaction — after Part 1, `PersistentExecutor._handle_event` will call `_save_state()` for the flushed `state_enter` event immediately before `loop_complete`. Confirm the save ordering is safe (status must end as `"timed_out"`, not `"running"`). No code change expected, but trace through the event sequence during implementation.
2. Update `tests/test_fsm_executor.py:2074-2113` (`test_loop_timeout_preserves_state`) — this test models pre-flush behavior and will break after Part 1. Update `time_values`, `mock_runner` call expectations, event sequence assertions, and docstring. Consider splitting into separate tests for flushed (shell-action) vs. non-flushed (slash_command/sub-loop) pending states.
3. Review `tests/test_fsm_persistence.py:847-871` (`test_final_status_timed_out_on_timeout`) — confirm flush guard activates only after a `route` event is emitted in the current iteration; this test forces timeout before routing so it should be unaffected, but verify explicitly.
4. Update `docs/guides/LOOPS_GUIDE.md:458` — add description of `autodev-inflight` convention to the autodev Notes section after Part 2 is implemented.
5. Update `docs/reference/schemas/loop_complete.json` — add note to `final_state` field description clarifying the pre/post-flush semantics change.

## Acceptance Criteria

- [ ] Executor flushes a single pending shell-action state when a timeout fires between `route` and `state_enter`; repro test covers the `refine_current → copy_broke_down` case
- [ ] Flush is bounded: only one state, only `shell` action_type, no cascade into further non-prompt states
- [ ] `dequeue_next` writes `.loops/tmp/autodev-inflight`; `enqueue_or_skip` and `enqueue_children` clear it
- [ ] `done` state emits a warning listing the mid-flight issue ID when `autodev-inflight` is non-empty
- [ ] Running `autodev` against an issue that hits the timeout mid-`refine_current` no longer silently drops the breakdown result — either the flag is flushed (Part 1) or the summary names the issue (Part 2)

## Labels

`bug`, `loops`, `autodev`, `captured`

## Status

**Completed** | Created: 2026-04-21 | Completed: 2026-04-21 | Priority: P2

## Resolution

**Both parts implemented exactly as designed.** Plan in `thoughts/shared/plans/` was
not needed — the issue's Integration Map already served as the plan.

### Part 1 — Executor flush (scripts/little_loops/fsm/executor.py)

- Added `_just_routed: bool` instance flag; set to `True` after emitting a
  `route` event (both the normal path and the maintain-mode route), cleared
  before `state_enter`.
- At the top-of-iteration timeout check, when `_just_routed` is `True` and the
  pending `current_state` is a non-terminal, non-sub-loop, shell-action state
  with a defined action, call the new `_flush_pending_shell_state(pending)`
  before `_finish("timeout")`.
- `_flush_pending_shell_state` increments iteration, emits `state_enter` with
  `flushed: true`, runs the action once, and swallows any action exception
  (timeout is being honored regardless).
- Bounded to shell actions: slash commands and sub-loops can take minutes and
  would violate the timeout budget. Single-step: the flushed state's routing
  is not followed, so `final_state` stays as the flushed state.

### Part 2 — autodev-inflight handshake (scripts/little_loops/loops/autodev.yaml)

- `init` resets `.loops/tmp/autodev-inflight` alongside `autodev-broke-down`.
- `dequeue_next` writes the popped issue ID to `.loops/tmp/autodev-inflight`.
- `enqueue_or_skip` and `enqueue_children` remove the file on resolution.
- `done` reads the file; if non-empty, prints a warning naming the issue:
  `WARNING: in-flight issue not resolved: %s (re-queue to retry)`.

### Tests

- `scripts/tests/test_fsm_executor.py::TestTimeoutHandling`:
  - Updated `test_loop_timeout_preserves_state` to assert flush runs `step2.sh`
    before `_finish("timeout")`.
  - Added `test_loop_timeout_flushes_pending_shell_state` — the canonical
    BUG-1226 repro (state_enter for flushed state emitted before loop_complete).
  - Added `test_loop_timeout_does_not_flush_slash_command_state` — guards the
    shell-only boundary.
  - Added `test_loop_timeout_does_not_flush_before_first_route` — guards the
    `_just_routed` precondition (covers the `test_final_status_timed_out_on_timeout`
    scenario where elapsed_offset_ms forces timeout before any route).
- `scripts/tests/test_builtin_loops.py::TestAutodevLoop`: added five structural
  tests asserting each of init / dequeue_next / enqueue_or_skip /
  enqueue_children / done references `autodev-inflight`.

### Docs

- `docs/guides/LOOPS_GUIDE.md`: autodev Notes block gains an "In-flight
  tracking" paragraph describing the `autodev-inflight` convention.
- `docs/reference/EVENT-SCHEMA.md` (and regenerated
  `docs/reference/schemas/loop_complete.json`): `final_state` description now
  documents the pre/post-flush semantics.
- `scripts/little_loops/generate_schemas.py`: updated the `loop_complete`
  `final_state` description.

### Verification

- `python -m pytest scripts/tests/` — 5012 passed, 5 skipped (unchanged from
  baseline).
- `ruff check scripts/` — clean.
- `python -m mypy scripts/little_loops/fsm/executor.py
  scripts/little_loops/generate_schemas.py` — clean.
- `ll-loop validate autodev` — valid.

### Deviations from plan

None. Also implicitly covered the wiring-phase concern at `persistence.py:417-418`
(double `_save_state()` on flush's `state_enter` before `loop_complete`): safe
because the final `loop_complete` handler overwrites status to `"timed_out"`
and the existing `test_final_status_timed_out_on_timeout` still passes.

### Acceptance criteria

- [x] Executor flushes a single pending shell-action state when a timeout
      fires between `route` and `state_enter`; repro test covers the
      `refine_current → copy_broke_down` case (`step1 → copy_flag` analog in
      `test_loop_timeout_flushes_pending_shell_state`).
- [x] Flush is bounded: only one state, only `shell` action_type, no cascade
      (covered by `test_loop_timeout_does_not_flush_slash_command_state` and
      the single-step `_flush_pending_shell_state` implementation).
- [x] `dequeue_next` writes `.loops/tmp/autodev-inflight`; `enqueue_or_skip`
      and `enqueue_children` clear it.
- [x] `done` state emits a warning listing the mid-flight issue ID when
      `autodev-inflight` is non-empty.
- [x] Running `autodev` against an issue that hits the timeout mid-
      `refine_current` no longer silently drops the breakdown result — either
      the flag is flushed (Part 1) or the summary names the issue (Part 2).


## Session Log
- `/ll:manage-issue bug fix BUG-1226` - 2026-04-21T15:26:02 - `92c83aba-8a81-42c9-8b48-b8a7811ab67e.jsonl`
- `/ll:ready-issue` - 2026-04-21T15:13:24 - `07ecd60f-10dd-4826-ba2c-3492aff7b9ce.jsonl`
- `/ll:wire-issue` - 2026-04-21T15:09:29 - `98e78901-55c8-44ae-a3c5-a92989d93e4a.jsonl`
- `/ll:refine-issue` - 2026-04-21T15:01:48 - `49b3985b-8519-4ec4-a1cf-c519cd70b905.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `59e885ea-0ce0-4161-8979-5315ee0153a5.jsonl`
