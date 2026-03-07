---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
confidence_score: 93
outcome_confidence: 93
---

# FEAT-543: `ll-loop history` Has No Event-Type Filter, State Filter, or Structured Output Mode

## Summary

`ll-loop history <name>` accepts only `--tail N` and renders all events as raw dict strings. The executor emits 8 distinct event types (`loop_start`, `state_enter`, `action_start`, `action_complete`, `evaluate`, `route`, `loop_complete`, `handoff_detected`) with different fields. There is no way to filter by event type, state name, timestamp range, or emit structured JSON output for piping.

## Location

- **File**: `scripts/little_loops/cli/loop/info.py`
- **Line(s)**: 62–84 (at scan commit: 47c81c8)
- **Anchor**: `in function cmd_history()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/cli/loop/info.py#L62-L84)

- **File**: `scripts/little_loops/cli/loop/__init__.py`
- **Line(s)**: 127–131 (at scan commit: 47c81c8)
- **Anchor**: `history_parser` argument definition
- **Code**:
```python
history_parser.add_argument("loop", ...)
history_parser.add_argument("--tail", "-n", type=int, default=50, ...)
# No --event, --state, --json, --since flags
```

## Current Behavior

`ll-loop history my-loop` prints the last 50 events as:
```
2026-03-03T21:00:00 state_enter: {'state': 'check', ...}
2026-03-03T21:00:01 action_start: {'state': 'check', ...}
...
```

All 8 event types are mixed together with no filtering. Output is human-readable only — not parseable for scripting.

## Expected Behavior

```bash
# Show only evaluate events (see all verdicts):
ll-loop history my-loop --event evaluate

# Show only route events for a specific state:
ll-loop history my-loop --event route --state check

# JSON output for scripting:
ll-loop history my-loop --json | jq '.[] | select(.event=="evaluate")'

# Limit to recent time window:
ll-loop history my-loop --since 1h
```

## Motivation

`ll-loop history` is a diagnostic tool. When debugging a loop with 200+ events, users need to filter to just the `evaluate` events to see all verdicts, or just `route` events to trace the state path. Without filtering, the output requires manual grep piping — and even then the raw dict format is hard to parse.

## Use Case

A user runs `ll-loop history issue-fixer --event evaluate --tail 20` to review the last 20 evaluation verdicts of a convergence loop, quickly identifying why the loop isn't converging without scrolling through interleaved `action_start`/`action_complete` noise.

## Acceptance Criteria

- `--event <type>` filters output to only events of the given type (e.g., `evaluate`, `route`, `loop_complete`)
- `--state <name>` filters to events where the `state` field matches (applicable to `state_enter`, `action_start`, `action_complete`, `evaluate`, `route`)
- `--json` emits newline-delimited JSON (one event object per line) instead of the current human-readable format
- `--since <duration>` accepts values like `1h`, `30m`, `2d` and filters to events within that window from now
- All flags are combinable
- `--tail` still applies as the final limit after filtering
- Existing behavior (no flags → last 50 events, human-readable) is unchanged

## API/Interface

```bash
# Updated history_parser in __init__.py:
history_parser.add_argument("--event", "-e", help="Filter by event type")
history_parser.add_argument("--state", "-s", help="Filter by state name")
history_parser.add_argument("--json", "-j", action="store_true", help="JSON output")
history_parser.add_argument("--since", help="Time window (e.g. 1h, 30m, 2d)")
```

## Proposed Solution

In `cmd_history()`:
1. Load all events from JSONL history file
2. Apply `--event` filter: `[e for e in events if e.get("event") == args.event]`
3. Apply `--state` filter: `[e for e in events if e.get("state") == args.state or e.get("from") == args.state]`
4. Apply `--since` filter: parse duration string → subtract from `datetime.now()` → filter by `e["ts"]`
5. Apply `--tail` limit
6. Render: if `--json`, emit `json.dumps(e)` per line; otherwise keep current human-readable format

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `cmd_history()`, add filtering logic
- `scripts/little_loops/cli/loop/__init__.py` — `history_parser`, add `--event`, `--state`, `--json`, `--since` args

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py` — routes `history` subcommand; update argument definition

### Similar Patterns
- `ll-messages` (`scripts/little_loops/cli/messages.py`) — time window and filter argument patterns to reference
- `ll-history` (`scripts/little_loops/cli/history.py`) — filtering patterns

### Tests
- `scripts/tests/test_ll_loop_commands.py:135` (`TestCmdHistory` class) — add: `--event evaluate` filters to only evaluate events
- `scripts/tests/test_ll_loop_commands.py:182` (`TestHistoryTail` class) — add: `--json` emits valid JSON lines; `--state check` filters to check-state events
- Pattern: `many_events_file` fixture at `conftest.py:296` provides 10-event JSONL file; follow `TestHistoryTail` pattern for filter tests

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `--event`, `--state`, `--json`, `--since` arguments to `history_parser` in `__init__.py`
2. Implement filtering in `cmd_history()` in `info.py`
3. Implement duration parser for `--since` (e.g., `1h` → 3600s)
4. Implement JSON output mode
5. Add tests for each filter flag

## Impact

- **Priority**: P4 — Quality-of-life improvement for loop debugging; not blocking
- **Effort**: Small-Medium — ~80 lines including duration parser and filter logic
- **Risk**: Low — Purely additive; existing no-flag behavior unchanged
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/generalized-fsm-loop.md` | Structured events — all 8 event types and their fields (line 1464), CLI history subcommand (line 1381) |
| `docs/guides/LOOPS_GUIDE.md` | CLI Quick Reference — history subcommand (line 398) |

## Labels

`feature`, `ll-loop`, `ux`, `cli`, `scan-codebase`

## Blocked By

- ENH-539 — `docs/generalized-fsm-loop.md` overlap (higher priority; complete first)
- ENH-537 — `docs/generalized-fsm-loop.md` overlap (higher priority; complete first)
- ENH-538 — `docs/generalized-fsm-loop.md` overlap (higher priority; complete first)

## Verification Notes

**Verdict**: VALID — 2026-03-05

- `scripts/little_loops/cli/loop/info.py` exists; `cmd_history()` at lines 65–91 (shifted from issue's 62–84 since scan commit)
- `scripts/little_loops/cli/loop/__init__.py` `history_parser` confirms only `loop` and `--tail` args — no `--event`, `--state`, `--json`, `--since`
- `TestCmdHistory` and `TestHistoryTail` classes confirmed in `test_ll_loop_commands.py` at lines 135 and 182 (updated from 101/148)
- Issue accurately describes the missing filtering capability

## Tradeoff Review Note

**Reviewed**: 2026-03-03 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | HIGH |
| Implementation effort | MEDIUM |
| Complexity added | MEDIUM |
| Technical debt risk | MEDIUM |
| Maintenance overhead | MEDIUM |

### Recommendation
Update first — HIGH utility (debugging 200+ event logs is a real pain point), but the `--since` duration parser is a non-trivial utility that will also be needed by `ll-messages` and `ll-history`. Before implementing, extract the duration string parser (`"1h"` → seconds, `"30m"` → seconds, `"2d"` → seconds) as a shared utility in `little_loops/text_utils.py` or a new `time_utils.py`. This reduces maintenance overhead (one implementation vs three) and makes the feature scope cleaner. Once that utility exists, the filtering implementation is straightforward.

## Session Log
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: no --event, --state, --json, --since flags

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`
- `/ll:refine-issue` — 2026-03-03T23:10:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` — Linked `docs/generalized-fsm-loop.md`; updated test refs to `test_ll_loop_commands.py:101` (TestCmdHistory) and `:148` (TestHistoryTail)
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:verify-issues` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a018087-87e4-41d0-99de-499289e1e675.jsonl` — Removed BUG-529 from Blocked By (completed/satisfied)
- `/ll:format-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2d766fe-2cc3-467b-a046-6a331a5941d9.jsonl` — Merged duplicate Session Log sections, fixed malformed footer structure
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2d766fe-2cc3-467b-a046-6a331a5941d9.jsonl` — VALID; updated test line numbers 101→135 and 148→182
- `/ll:map-dependencies` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2d766fe-2cc3-467b-a046-6a331a5941d9.jsonl` — Added Blocked By ENH-537, ENH-538, ENH-539 (docs/generalized-fsm-loop.md overlap)
- `/ll:confidence-check` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2d766fe-2cc3-467b-a046-6a331a5941d9.jsonl` — readiness: 93/100 PROCEED, outcome: 93/100 HIGH CONFIDENCE
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl`

---

## Status

**Open** | Created: 2026-03-03 | Priority: P4
