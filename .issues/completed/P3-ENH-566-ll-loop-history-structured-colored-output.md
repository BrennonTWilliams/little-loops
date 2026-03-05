---
discovered_date: 2026-03-05T00:00:00Z
discovered_by: manual
---

# ENH-566: Structured, Colored Output for `ll-loop history`

## Summary

`ll-loop history <name>` printed raw Python dict representations for every event, making output
noisy and hard to scan. This enhancement replaces the raw-dict renderer with a structured,
per-event-type formatter using the existing `colorize` and `terminal_width` utilities, and adds
a `--verbose/-v` flag to show `action_output` streaming lines on demand.

## Problem

Before this change, every event rendered as:

```
2026-03-05 20:32:10 loop_start: {'loop': 'issue-refinement'}
2026-03-05 20:32:10 state_enter: {'state': 'evaluate', 'iteration': 1}
2026-03-05 20:32:10 action_output: {'line': 'ID        Pri   Title...'}
2026-03-05 20:32:36 evaluate: {'type': 'llm_structured', 'verdict': 'failure', ...}
```

Problems:
- Raw Python dict format (`{k: v}`) is hard to scan and visually noisy
- `action_output` events (one per output line) dominated history of any non-trivial run
- Timestamp included date despite history typically being same-day
- `colorize` and `terminal_width` were imported but never used

## Solution

### Files Modified

1. **`scripts/little_loops/cli/loop/__init__.py`** — Added `--verbose/-v` flag to the `history`
   subparser (after existing `--tail`)

2. **`scripts/little_loops/cli/loop/info.py`** — Added:
   - `from typing import Any` import
   - `_EVENT_TYPE_WIDTH = 16` constant
   - `_truncate(text, max_len)` helper for ellipsis truncation
   - `_format_history_event(event, verbose, width) -> str | None` — per-event-type structured
     formatter; returns `None` to suppress `action_output` events when not verbose
   - Replaced `cmd_history()` body: reads `verbose` from args, calls `_format_history_event`,
     prints only non-`None` lines

3. **`scripts/tests/test_cli_output.py`** — Updated `TestLoopHistoryTimestamp`:
   - `test_iso_timestamp_formatted_as_readable`: assertion updated from
     `"2026-03-04 14:30:00"` → `"14:30:00"` (timestamps now render as `HH:MM:SS`)
   - `test_invalid_timestamp_falls_back_to_truncated`: assertion updated from
     `"not-a-timestamp"` → `"not-a-ti"` (fallback now takes 8-char slice)
   - All three test fixtures updated with `verbose=False` in `argparse.Namespace`

### Event Type Rendering

| Event | Color | Detail format |
|-------|-------|---------------|
| `loop_start` | bold | loop name |
| `loop_complete` | bold | `{final_state}  {iterations} iter  [{terminated_by}]` |
| `loop_resume` | bold | `from={from_state}  iter={iteration}` |
| `state_enter` | blue (34) | `{state}  (iter {iteration})` — state name in bold |
| `action_start` | default | first line of action truncated to terminal width + `[shell]` or `[prompt]` |
| `action_output` | dim (2) | `│ {line}` — suppressed by default, shown with `--verbose` |
| `action_complete` | dim/orange | `✓  {ms}ms` or `✗ exit={N}  {ms}ms` |
| `evaluate` | green/orange | `✓ success` or `✗ {verdict}` + confidence + truncated reason |
| `route` | dim (2) | `{from} → {to}` — destination in blue |
| `handoff_detected` | yellow (33) | `state={state}  iter={iteration}` |
| unknown | default | `key=value` pairs |

### Example Output (default mode)

```
20:32:10  loop_start        issue-refinement
20:32:10  state_enter       evaluate  (iter 1)
20:32:10  action_start      ll-issues refine-status --no-key  [shell]
20:32:10  action_complete   ✓  72ms
20:32:36  evaluate          ✗ failure  confidence=1.0  All 10 issues have fmt=✗…
20:32:36  route             evaluate → fix
20:32:36  state_enter       fix  (iter 2)
20:32:36  loop_complete     done  3 iter  [success]
```

## Relation to FEAT-543

FEAT-543 (`ll-loop history` filtering) calls for `--event`, `--state`, `--json`, and `--since`
flags on top of this structured output foundation. This ENH delivers the structured renderer;
FEAT-543 filtering flags remain open.

## Impact

- **Priority**: P3 — Immediate UX improvement for loop debugging
- **Effort**: Small — ~120 lines added to `info.py`; 3 test assertions updated
- **Risk**: Low — Purely presentation layer; no changes to persistence or event emission
- **Breaking Change**: No — `action_output` suppression is default-safe; existing behavior
  (no flags → last 50 events) preserved

## Labels

`enhancement`, `ll-loop`, `ux`, `cli`, `output-styling`

## Session Log

- `manual` — 2026-03-05 — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2d766fe-2cc3-467b-a046-6a331a5941d9.jsonl` — Planned and implemented structured history output

---

## Resolution

Implemented `_format_history_event()` with per-event-type structured rendering and ANSI color
support. Added `--verbose/-v` to suppress `action_output` lines by default. Timestamps shortened
to `HH:MM:SS`. Updated 3 test assertions in `test_cli_output.py`. All 19 tests pass.

**Resolved**: 2026-03-05 | manual implementation

---

## Status

**Completed** | Created: 2026-03-05 | Resolved: 2026-03-05 | Priority: P3
