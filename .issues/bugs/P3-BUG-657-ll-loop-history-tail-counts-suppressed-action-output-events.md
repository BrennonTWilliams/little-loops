---
discovered_date: 2026-03-08T00:00:00Z
discovered_by: capture-issue
---

# BUG-657: `ll-loop history` `--tail` Counts Suppressed `action_output` Events, Hiding Earlier Iterations

## Summary

`ll-loop history` slices the raw event list with `--tail N` (default 50) *before* filtering out `action_output` events in non-verbose mode. Shell-type states emit one `action_output` event per stdout line. When a shell action produces many output lines (e.g., a table), those events consume most of the tail budget, leaving no room for events from earlier iterations. The result: the user sees far fewer iterations than actually ran and has no indication the history is incomplete.

## Location

- **File**: `scripts/little_loops/cli/loop/info.py`
- **Line(s)**: 229–234
- **Anchor**: `in function cmd_history()` — `events[-tail:]` slice then `_format_history_event` None-check
- **Code**:
```python
tail = getattr(args, "tail", 50)
...
for event in events[-tail:]:          # slices ALL events, including action_output
    line = _format_history_event(event, verbose, w)
    if line is None:                  # action_output returns None when not verbose
        continue
    print(line)
```

## Root Cause

`cmd_history()` in `info.py` applies the `--tail` slice to the complete raw event list returned by `read_events()`. The `_format_history_event()` call that silently drops `action_output` events (line 122–123) happens *after* the slice. Since `action_output` events are never displayed in default (non-verbose) mode, they consume tail budget without producing any visible output.

- **File**: `scripts/little_loops/cli/loop/info.py`, line 232 — tail slice applied to raw list
- **File**: `scripts/little_loops/cli/loop/info.py`, lines 122–123 — `action_output` suppressed post-slice

## Steps to Reproduce

1. Run a loop where the shell evaluate step produces 10+ lines of stdout (e.g., `ll-issues refine-status --no-key`)
2. Run 10+ iterations
3. Run `ll-loop history <name>` (default `--tail 50`)
4. Observe: only the last 2–3 iterations appear in history; earlier iterations are invisible

**Why**: 10 iterations × ~15 raw events each (including ~10 `action_output` per evaluate) = ~150 raw events. `--tail 50` takes only the last ~3 iterations' raw events. After dropping `action_output`, only ~15 visible lines remain — all from the final few iterations.

## Expected Behavior

`--tail N` should limit to the last N *visible* (displayable) events. In default non-verbose mode, `action_output` events do not count toward the tail. Users running `ll-loop history <name>` with the default `--tail 50` should see events from the last ~50 significant moments across all iterations.

## Current Behavior

`--tail 50` limits to the last 50 raw events regardless of display mode. With verbose shell output, the effective visible history covers only the last 1–3 iterations, with no indication that earlier iterations are hidden.

## Workaround

Pass a large explicit tail: `ll-loop history <name> --tail 500`

## Proposed Solution

Apply the tail slice *after* filtering suppressed events:

```python
# In cmd_history():
tail = getattr(args, "tail", 50)
verbose = getattr(args, "verbose", False)

all_events = get_loop_history(loop_name, loops_dir)
visible_events = [
    e for e in all_events
    if not (e.get("event") == "action_output" and not verbose)
]
for event in visible_events[-tail:]:
    line = _format_history_event(event, verbose, w)
    if line is None:
        continue
    print(line)
```

Alternatively, raise the default `--tail` to 500 as a minimal fix, though that does not address the conceptual mismatch.

## Implementation Steps

1. In `cmd_history()` (`info.py`), filter out `action_output` events before applying the `--tail` slice
2. Preserve `--verbose` behavior: when `verbose=True`, skip the filter so `action_output` events count toward tail as before
3. Verify existing `TestHistoryTail` tests (`test_ll_loop_commands.py:182`) pass without modification
4. Add regression test covering the multi-line stdout scenario (10+ `action_output` events, confirm tail counts visible events only)

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `cmd_history()` function: reorder filter before slice

### Dependent Files (Callers/Importers)
- N/A — `cmd_history()` is a CLI entry point, not imported by other modules

### Similar Patterns
- N/A — tail-after-filter pattern is unique to this command

### Tests
- `scripts/tests/test_ll_loop_commands.py` — `TestHistoryTail` class (line 182): verify existing tests pass; add new test for multi-line shell output scenario

### Documentation
- N/A — no docs reference the `--tail` behavior explicitly

### Configuration
- N/A

## Acceptance Criteria

- `ll-loop history <name>` with default `--tail 50` shows events spanning all iterations (not just the last 1–3) when shell actions produce multi-line stdout
- `action_output` events do not count toward `--tail N` unless `--verbose` is passed
- `ll-loop history <name> --verbose` continues to include `action_output` events, and `--tail` counts them as before (consistent with verbose mode intent)
- Existing tests in `TestHistoryTail` (`test_ll_loop_commands.py:182`) still pass

## Impact

- **Priority**: P3 — The history command is the primary diagnostic tool for loop debugging; incorrect output causes real confusion (as seen in user report where 10 iterations appeared to be only 2–3)
- **Effort**: Tiny — Reorder two operations (filter before slice) in `cmd_history()`
- **Risk**: Low — No behavioral change when `action_output` is absent; `--verbose` mode unaffected
- **Breaking Change**: No

## Related Issues

- FEAT-543 — `ll-loop history` filter flags (`--event`, `--state`, `--json`, `--since`). When implemented, `--tail` will naturally apply after `--event` filtering; this bug should be fixed independently or as a prerequisite so the filter implementation has correct ordering semantics to build on.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | FSM executor event model and persistence layer design |

## Labels

`bug`, `ll-loop`, `ux`, `cli`

## Session Log
- `/ll:capture-issue` - 2026-03-08T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`
- `/ll:format-issue` - 2026-03-08T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6406d067-9f2b-4081-b0e0-1751ae6a7a77.jsonl`

---

## Status

**Open** | Created: 2026-03-08 | Priority: P3
