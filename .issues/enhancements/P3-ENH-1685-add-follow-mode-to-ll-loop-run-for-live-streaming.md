---
captured_at: '2026-05-24T21:32:58Z'
discovered_date: 2026-05-24
discovered_by: capture-issue
status: open
decision_needed: true
confidence_score: 95
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
implementation_order_risk: true
---

# ENH-1685: Add `--follow` mode to `ll-loop run` for live streaming

## Summary

`ll-loop run` terminates once the loop exits, giving no in-progress view while a long-running loop is executing. Add a `--follow` flag (mirroring `ll-loop history --follow`) that streams FSM transitions to stdout in real time — printing the current state, active variables, and evaluator output as each transition fires. For low-level byte streaming, `ll-logs tail` remains the right tool; `--follow` targets structured loop introspection.

## Current Behavior

`ll-loop run <loop>` launches the loop, waits for termination, then reports the final outcome. There is no way to watch in-progress state transitions, variable snapshots, or evaluator verdicts without manually tailing the underlying JSONL with `ll-logs tail` and parsing raw events. `ll-loop history --follow` exists for post-run log replay but does not attach to a live run.

## Expected Behavior

`ll-loop run <loop> [--follow]` accepts an optional `--follow` flag. When set:

1. The loop is launched as normal.
2. While the loop runs, each state transition is printed to stdout as it fires, including:
   - Transition label (e.g., `[diagnose → propose]`)
   - Active state variables (key/value snapshot)
   - Evaluator name + output for the transition that just completed
3. The command exits when the loop terminates, printing the final outcome summary.
4. Without `--follow`, current silent-until-done behavior is preserved.

## Motivation

Long-running loops (e.g., `general-task`, `autodev`) are opaque during execution. The operator must either wait for completion or tail raw JSONL with no structure. A structured follow mode would make it practical to monitor loops that run for tens of iterations, catch mis-evaluations early, and understand why a loop chose a particular transition — without adding any new persistent infrastructure.

## Implementation Steps

1. Identify where `ll-loop run` dispatches to the FSM executor (`scripts/little_loops/cli/loop_cli.py` or equivalent).
2. Wire a `--follow` flag to the `run` subcommand parser.
3. Have `FSMExecutor` emit structured transition events to a subscriber interface (or expose a callback hook per transition).
4. In follow mode, register a stdout formatter that prints each transition as it fires.
5. Reuse the event/payload schema that `ll-loop history` already renders so the two views stay consistent.
6. Add tests: `--follow` output contains expected transition labels; without `--follow`, no streaming output is produced.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Concrete implementation steps with file/function anchors:**

1. **Add `--follow` flag to `run_parser`** in `scripts/little_loops/cli/loop/__init__.py` at ~line 131 (alongside `--quiet` / `--verbose`):
   ```python
   run_parser.add_argument(
       "--follow", "-f", action="store_true",
       help="Stream FSM state transitions to stdout as they fire"
   )
   ```

2. **Register the follow callback in `run_foreground()`** in `scripts/little_loops/cli/loop/_helpers.py` at lines 951-956 — add after the existing `display_progress` registration:
   ```python
   follow = getattr(args, "follow", False)
   if follow:
       from little_loops.cli.loop.info import _format_history_event
       tw = terminal_width()
       def _follow_callback(event: dict) -> None:
           line = _format_history_event(event, verbose=verbose, width=tw)
           if line is not None:
               print(line, flush=True)
       executor.event_bus.register(_follow_callback)
   ```
   No changes needed to `run.py`, `executor.py`, or `persistence.py`.

3. **No FSMExecutor changes** — `PersistentExecutor._handle_event()` in `persistence.py` already calls `self.event_bus.emit(event)` after persisting each event. The callback fires synchronously in-process.

4. **Reference implementation** — `scripts/little_loops/cli/logs.py:_cmd_tail()` already imports and uses `_format_history_event()` from `info.py` for live-tail formatting. The same import pattern applies here.

5. **Context variable note** — The proposed format `var_a=1  var_b=hello` in the API/Interface section is NOT available from event payloads; `state_enter` carries only `{state, iteration}`. If context snapshots are desired, read `executor.fsm.context` inside the callback closure (executor is in scope). Otherwise align with what `_format_history_event()` already renders for `route` (`from → to`) and `evaluate` (`verdict`, `confidence`, `reason`).

6. **Tests** — Add to `scripts/tests/test_ll_loop_display.py` using the existing `MockExecutor` pattern (line 34). Follow the `test_ll_loop_commands.py:TestHistoryTail` pattern for integration tests and `test_ll_logs.py:TestTailSubcommand` for the `capsys` / mock approach.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `run_background()` in `scripts/little_loops/cli/loop/_helpers.py` (lines 556–587) — decide whether `--follow --background` is supported; if yes, add `follow` to the forwarded-flag block; if no, document/warn that the combination silently drops `--follow`
8. Update `docs/reference/CLI.md` — add `--follow` / `-f` row to the flags table at lines 375–395
9. Update `docs/guides/LOOPS_GUIDE.md` — add `--follow` / `-f` row to the run flags table at lines 2550–2565
10. Add `follow=False` to `_make_args()` helpers in: `test_cli_loop_lifecycle.py` (lines 840, 928), `test_cli_loop_queue.py` (line 12), `test_cli_loop_worktree.py` (line 562)
11. Add parser registration test in `test_ll_loop_parsing.py` — assert `args.follow` defaults to `False` and becomes `True` with `--follow` (follow `test_handoff_threshold_registered_on_real_run_parser` at line 260)
12. Write follow callback tests in `test_ll_loop_display.py` using a `MockExecutorWithEventBus` variant that has a real `event_bus` with `.register()`

## Scope Boundaries

- **In scope**: `--follow` flag on `ll-loop run`; stdout printing of state transitions, active variables, and evaluator verdicts as they fire; exit when loop terminates.
- **Out of scope**: Byte-level streaming (use `ll-logs tail`); historical log replay (use `ll-loop history --follow`); modifying FSM execution behavior or variable values during follow mode; persistent subscription or webhook delivery of events; changes to the non-follow `run` output format.

## API/Interface

```
ll-loop run <loop> [--follow] [--max-iterations N] [--quiet] ...
```

Per-transition stdout line format (mirrors `ll-loop history` rendering):

```
[diagnose → propose]  verdict=ok  var_a=1  var_b=hello
```

Fields: transition label (`[from → to]`), active state variables as `key=value` pairs, evaluator name + output for the completed transition. Final outcome summary printed on loop exit (same as current silent-mode output).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — add `--follow` argument to `run_parser`
- `scripts/little_loops/cli/loop/run.py` — pass `follow=True` to executor when flag is set
- `scripts/little_loops/fsm/executor.py` — register a stdout-formatter callback via the existing `event_callback` interface when follow mode is active

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/_helpers.py` — primary implementation file (per refinement research); register follow callback in `run_foreground()` via `executor.event_bus.register()`; also update `run_background()` (lines 556–587) to decide whether `--follow` should be forwarded to re-exec subprocess (currently absent from forwarded-flag block, so `--follow --background` silently drops the flag)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py` — already imports `cmd_run` from `run.py`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` at ~line 549 calls `run_foreground()`; `resume_parser` doesn't define `--follow`; safe because `getattr(args, "follow", False)` returns `False` for resume calls without crashing
- `scripts/little_loops/cli/loop/next_loop.py` — line 328 calls `cmd_run()` dynamically; `args.follow` absent on its constructed `Namespace`; safe only if `cmd_run` reads `follow` via `getattr` fallback

### Similar Patterns
- `scripts/little_loops/cli/loop/info.py` — `cmd_history` follow mode and `_render_event()` define the event rendering schema; reuse the same rendering logic

### Tests
- `scripts/tests/test_fsm_executor.py` — add tests: `--follow` output contains expected transition labels; silent without `--follow`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_parsing.py` — add parser registration test: assert `args.follow` defaults to `False` and is `True` with `--follow` (follow `test_handoff_threshold_registered_on_real_run_parser` pattern at line 260) — **new test to write**
- `scripts/tests/test_ll_loop_display.py` — add `follow=False` to `_make_args()` at lines 1648, 2586, 2638; write new follow callback tests using `MockExecutorWithEventBus` variant (real `event_bus` with `.register()`) — **update + new tests**
- `scripts/tests/test_cli_loop_lifecycle.py` — `_make_args()` at lines 840 and 928 need `follow=False` added for structural completeness — **update existing helpers**
- `scripts/tests/test_cli_loop_queue.py` — module-level `_make_args()` at line 12 needs `follow=False` — **update existing helper**
- `scripts/tests/test_cli_loop_worktree.py` — `TestCmdRunWorktree._make_args()` at line 562 needs `follow=False` — **update existing helper**

### Documentation
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `ll-loop run` flags table at lines 375–395 lists all flags; add `--follow` / `-f` row with description
- `docs/guides/LOOPS_GUIDE.md` — `### Run Flags` table at lines 2550–2565 lists run flags; add `--follow` / `-f` row with description

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical correction — primary modification point is `_helpers.py`, not `executor.py`:**

The follow callback should be registered in `_helpers.py:run_foreground()` at lines 951-956, alongside the existing `display_progress` registration:

```python
# existing pattern (lines 952-956):
if not quiet or show_diagrams:
    if hasattr(executor, "event_bus"):
        executor.event_bus.register(display_progress)
```

A `--follow` callback would be registered the same way: `executor.event_bus.register(follow_callback)`. No changes to `fsm/executor.py` are needed — the `event_bus.register()` hook already exists. `run.py:cmd_run()` also does NOT need to pass `follow=True` to the executor; `args` is already passed wholesale to `run_foreground()`, so `args.follow` is accessible there directly.

**Corrected files-to-modify list:**
- `scripts/little_loops/cli/loop/__init__.py:100-192` — add `--follow` to `run_parser` (all other flags are registered here)
- `scripts/little_loops/cli/loop/_helpers.py:run_foreground()` (lines 951-956) — register follow callback on `executor.event_bus` when `args.follow` is set; this is THE key file, currently absent from this integration map
- `scripts/little_loops/cli/loop/info.py` — import `_format_history_event()` for rendering (read-only, no modifications)
- `scripts/little_loops/cli/loop/run.py` — no change needed beyond what `args` already carries

**Rendering function signature (not `_render_event()`):**
The function is `_format_history_event()` at `info.py:271`:
```python
def _format_history_event(event: dict[str, Any], verbose: bool, width: int, full: bool = False) -> str | None:
```
Returns `None` for events that should be skipped (e.g., `action_output` in non-verbose mode). `cmd_history` has **no live `--follow` mode** — it is entirely static replay of archived events.

**Event payload caveat — context variables are NOT in events:**
`state_enter` carries `state` and `iteration` but NOT the full `fsm.context`. The "active state variables (key/value snapshot)" described in the Expected Behavior section would require reading `executor.fsm.context` directly inside the callback (the executor reference is in scope as a closure variable in `run_foreground()`). The event payloads that ARE available: `route` → `{from, to}`, `state_enter` → `{state, iteration}`, `evaluate` → `{verdict, confidence, reason}`.

**FSM event type reference (from `FSMExecutor._emit()`):**

| Event | Key payload fields |
|---|---|
| `loop_start` | `loop` |
| `state_enter` | `state`, `iteration` |
| `route` | `from`, `to` |
| `evaluate` | `type`, `verdict`, `confidence`, `reason` |
| `action_complete` | `exit_code`, `duration_ms` |
| `loop_complete` | `final_state`, `iterations`, `terminated_by` |

**Tests — prefer `test_ll_loop_display.py` for follow output tests:**
- `scripts/tests/test_ll_loop_display.py` — already has `MockExecutor` at line 34 and extensive `display_progress` output tests; follow tests belong here alongside the existing display tests
- `scripts/tests/test_fsm_executor.py` — tests for FSMExecutor internals, less relevant for CLI output testing

## Related

- `ll-loop history --follow` (existing log replay)
- `ll-logs tail` (raw byte streaming for live JSONL)

## Impact

- **Priority**: P3 — useful quality-of-life improvement for long-running loops; not blocking any current work
- **Effort**: Small — `event_callback` interface already exists in `FSMExecutor`; rendering logic already exists in `info.py`; change is additive (new flag, no behavior changes to existing paths)
- **Risk**: Low — `--follow` is opt-in; existing silent-until-done behavior is fully preserved; no changes to FSM execution logic
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `loops`, `captured`

## Status

**Open** | Created: 2026-05-24 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-24_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors

- **Open decision: `--follow --background` combination** — `run_background()` lines 556–587 enumerate forwarded flags; `--follow` is currently absent from that block. Decide whether `--follow --background` is supported (forward the flag to re-exec) or unsupported (document/warn). This open decision should be resolved before starting implementation to avoid rework in `run_background()` and test assertions.
- **Wide file surface (9 sites)** — 5 test helper updates needed (`test_cli_loop_lifecycle.py`, `test_cli_loop_queue.py`, `test_cli_loop_worktree.py`, `test_ll_loop_display.py`, `test_ll_loop_parsing.py`); tests are co-deliverables of the --follow implementation and should be updated alongside the core changes to avoid test suite breakage mid-implementation.
- **Context variable snapshot format** — API interface shows `var_a=1  var_b=hello` but `state_enter` events carry only `{state, iteration}`; format will diverge from `_format_history_event()` output unless callback reads `executor.fsm.context` directly; the issue acknowledges this but leaves the resolution implicit.

## Session Log
- `/ll:confidence-check` - 2026-05-24T22:10:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/51fa1ae1-7bfb-419b-874a-53047c48bfa8.jsonl`
- `/ll:wire-issue` - 2026-05-24T21:54:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6610c4b9-00d0-4e04-aeda-b66222aa4c9b.jsonl`
- `/ll:refine-issue` - 2026-05-24T21:43:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa77648f-bc3c-435e-907c-c7c75f43ac5c.jsonl`
- `/ll:format-issue` - 2026-05-24T21:37:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d35b8392-4d1a-4657-87ba-0bc716fe85cc.jsonl`
- `/ll:capture-issue` - 2026-05-24T21:32:58Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/844eef49-d6af-471d-b715-a770004ddedf.jsonl`
