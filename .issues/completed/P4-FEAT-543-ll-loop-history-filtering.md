---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 93
---

# FEAT-543: `ll-loop history` Has No Event-Type Filter, State Filter, or Structured Output Mode

## Summary

`ll-loop history <name>` now accepts `--tail N`, `--verbose`, `--full`, and `--json` (added via ENH-740). However, there is still no way to filter by event type (`--event`), state name (`--state`), or timestamp range (`--since`). The executor emits 8 distinct event types with different fields, and filtering still requires manual grep piping.

## Location

- **File**: `scripts/little_loops/cli/loop/info.py`
- **Line(s)**: 399– (updated from 397–)
- **Anchor**: `in function cmd_history()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/cli/loop/info.py#L62-L84)

- **File**: `scripts/little_loops/cli/loop/__init__.py`
- **Line(s)**: 225–247 (updated from 213–235)
- **Anchor**: `history_parser` argument definition
- **Code**:
```python
history_parser.add_argument("loop", ...)                                  # line 229
history_parser.add_argument("run_id", nargs="?", default=None, ...)       # line 230-235
history_parser.add_argument("--tail", "-n", type=int, default=50, ...)    # line 236-238
history_parser.add_argument("--verbose", "-v", action="store_true", ...)  # Added (ENH-740) line 239-241
history_parser.add_argument("--full", action="store_true", ...)           # Added (ENH-740) line 243-246
history_parser.add_argument("--json", action="store_true", ...)           # Added (ENH-740) line 247
# No --event, --state, --since flags
```

## Current Behavior

`ll-loop history my-loop` prints the last 50 events with optional `--verbose`/`--full` detail and `--json` output (the latter two added via ENH-740). However, all event types are still mixed together with no filtering:
```
2026-03-03T21:00:00 state_enter: {'state': 'check', ...}
2026-03-03T21:00:01 action_start: {'state': 'check', ...}
...
```

There is still no way to filter to a specific event type or state name, or filter by time window.

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

- `--event <type>` filters output to only events of the given type (e.g., `evaluate`, `route`, `loop_complete`) — **not yet implemented**
- `--state <name>` filters to events where the `state` field matches (applicable to `state_enter`, `action_start`, `action_complete`, `evaluate`, `route`) — **not yet implemented**
- `--json` emits events as a JSON array — **already implemented (ENH-740)**
- `--since <duration>` accepts values like `1h`, `30m`, `2d` and filters to events within that window from now — **not yet implemented**
- All flags are combinable
- `--tail` still applies as the final limit after filtering
- Existing behavior (no flags → last 50 events, human-readable) is unchanged

## API/Interface

```bash
# Remaining flags to add to history_parser in __init__.py (--json already exists):
history_parser.add_argument("--event", "-e", help="Filter by event type")
history_parser.add_argument("--state", "-s", help="Filter by state name")
history_parser.add_argument("--since", help="Time window (e.g. 1h, 30m, 2d)")
```

## Proposed Solution

In `cmd_history()`:
1. Load all events from JSONL history file
2. Apply `--event` filter: `[e for e in events if e.get("event") == args.event]`
3. Apply `--state` filter: `[e for e in events if e.get("state") == args.state or e.get("from") == args.state or e.get("to") == args.state]`
4. Apply `--since` filter: parse duration string → subtract from `datetime.now()` → filter by `e["ts"]`
5. Apply `--tail` limit (after all filters, consistent with existing tail behavior)
6. Render: if `--json`, emit `json.dumps(e)` per line; otherwise keep current human-readable format

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Filter insertion point:** The existing non-verbose pre-filter at `info.py:428-429` strips `action_output` events _before_ `[-tail:]`. The new `--event`/`--state`/`--since` filters should be applied in the same pre-`[-tail:]` position so `--tail` acts as the final limit on the filtered result.

**`--state` filter must cover `from`, `to`, and `state` fields:** `route` events use `from` and `to` but have no `state` field. `state_enter`, `evaluate`, `action_start`, `action_complete` use `state`. Matching all three fields ensures `--state check` catches both `{"event": "state_enter", "state": "check"}` and `{"event": "route", "from": "check", "to": "done"}`.

**Duration parser — no shared utility exists:** No `parse_duration("1h")` function exists anywhere in `scripts/little_loops/`. The closest patterns are `datetime.timedelta(days=N)` in `analysis.py:181` and `summary.py:214`. A new `parse_duration(s: str) -> int` (seconds) function needs to be created. The Tradeoff Review recommends placing it in `scripts/little_loops/text_utils.py` for sharing with `ll-messages` and `ll-history`. Implementation:
```python
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
def parse_duration(s: str) -> int:
    """Parse '1h', '30m', '2d' into seconds."""
    m = re.match(r"^(\d+)([smhd])$", s)
    if not m:
        raise ValueError(f"Invalid duration: {s!r}. Use e.g. 1h, 30m, 2d")
    return int(m.group(1)) * _UNITS[m.group(2)]
```

**`--since` timestamp format in events:** Events store `"ts"` as ISO 8601 with `Z` suffix (e.g., `"2026-03-03T21:00:00Z"`). Use `.replace("Z", "+00:00")` before `datetime.fromisoformat()` — the same normalization used in `user_messages.py:521`. Then strip tzinfo for naive comparisons: `ts.replace(tzinfo=None)`.

**`--json` current implementation:** `print_json(events[-tail:])` at `info.py` (after ENH-740). The new filter sequence must be applied _before_ passing to `print_json`: `print_json(filtered_events[-tail:])`.

**Dispatcher location:** `__init__.py:319-320` — `cmd_history(args.loop, getattr(args, "run_id", None), args, loops_dir)`. New args will be auto-available via `args` namespace once added to `history_parser`.

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
- `scripts/tests/test_ll_loop_commands.py:324` (`TestCmdHistory` class) — add: `--event evaluate` filters to only evaluate events
- `scripts/tests/test_ll_loop_commands.py:371` (`TestHistoryTail` class) — add: `--state check` filters to check-state events; `--since 1h` time-window filter; combined flag tests
- `scripts/tests/test_ll_loop_commands.py:731+` — add a `TestHistoryFiltering` class for the new filters; follow `TestHistoryTail` pattern (monkeypatch.chdir + patch sys.argv + capsys)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`many_events_file` fixture location:** It is at `test_ll_loop_commands.py:374` (inside `TestHistoryTail`), NOT `conftest.py:296` as previously noted. The fixture creates 10 `transition`-typed events with `{"event": "transition", "from": "stateN", "to": "stateN+1"}` — no `state` field. This fixture cannot test `--event evaluate` or `--state check` filtering without modification.

**New fixture needed for filter tests:** Create a `mixed_events_file` fixture that writes a variety of event types including `state_enter` (with `state` field), `evaluate` (with `verdict` field), `route` (with `from`/`to` fields), and `action_start`. This is the fixture needed to test `--event` and `--state` filtering meaningfully.

**`--since` test pattern:** Follow `test_user_messages.py:225-249` pattern — write events with specific timestamps, call `cmd_history()` with a `--since` value that cuts out older events, assert on filtered count. Use `datetime.now() - timedelta(hours=2)` as the timestamp for "old" events.

**JSON output assertion pattern:** Follow `test_ll_loop_commands.py:661` (`test_history_json_output`) — call `cmd_history()` directly with `argparse.Namespace(tail=50, verbose=False, json=True, full=False)`, capture output via `capsys`, parse with `json.loads()`.

**`parse_duration` unit tests:** Add a dedicated test class (e.g., in `test_ll_loop_parsing.py`) testing `parse_duration("1h") == 3600`, `parse_duration("30m") == 1800`, `parse_duration("2d") == 172800`, and that an invalid string raises `ValueError`.

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. **Add `parse_duration()` to `scripts/little_loops/text_utils.py`** — regex-based parser for `"1h"`, `"30m"`, `"2d"` → seconds; raises `ValueError` on bad input; unit tests in `test_ll_loop_parsing.py`
2. **Add `--event`, `--state`, `--since` to `history_parser` in `__init__.py:247+`** — append after existing `--json` at line 247; `type=str` for all three; `--event`/`-e`, `--state`/`-s`, `--since` with metavar `"DURATION"`
3. **Implement filtering in `cmd_history()` in `info.py:419+`** — apply `--event` → `--state` → `--since` filters in sequence, after loading events via `get_archived_events()` but before the `[-tail:]` slice; insert after line 427 (before existing `action_output` pre-filter which stays for non-verbose mode)
4. **Add `mixed_events_file` fixture to `test_ll_loop_commands.py`** — JSONL with `state_enter`, `evaluate`, `route`, `action_start` events with varied timestamps and states
5. **Add `TestHistoryFiltering` class in `test_ll_loop_commands.py`** — tests for `--event`, `--state`, `--since`, combined flags; follow `TestHistoryTail` pattern (monkeypatch.chdir + sys.argv patch + capsys)

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

_(ENH-537 completed — extracted `process_alive` utility)_
_(ENH-538 completed — added maintain-mode executor tests)_
_(ENH-539 removed — completed as duplicate of ENH-626)_

## Verification Notes

**Verdict**: NEEDS_UPDATE — 2026-03-20

- `cmd_history()` is at `info.py:399` (updated). `history_parser` args span `__init__.py` lines **225–247** (updated). `--json`, `--verbose`, `--full` already implemented (via ENH-740); `--event`, `--state`, `--since` still absent. `many_events_file` fixture confirmed at `test_ll_loop_commands.py:374` (not `conftest.py:296`). No shared duration parser exists — new `parse_duration()` needed in `text_utils.py`.

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
- `/ll:ready-issue` - 2026-03-21T05:12:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6094f1ed-fc91-436b-b28b-8b1cc75631f6.jsonl`
- `/ll:verify-issues` - 2026-03-21T05:10:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1082d080-3f73-4dbb-aa8e-13649c83fe55.jsonl`
- `/ll:confidence-check` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:refine-issue` - 2026-03-21T00:21:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5299772f-969e-4905-ae98-f9ec59c250bf.jsonl`
- `/ll:verify-issues` - 2026-03-15T17:23:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7c4b6f16-1629-4fbe-91ed-e715b7a19026.jsonl`
- `/ll:verify-issues` - 2026-03-15T00:11:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/623195d5-5e50-40d6-b2b9-5b105ad77689.jsonl`
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: no --event, --state, --json, --since flags
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: filters still absent; removed stale Blocked By ENH-539 (completed as duplicate of ENH-626)
- `/ll:ready-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7bc8b254-8ac0-409d-b79d-9795de6dc39e.jsonl` — BLOCKED: ENH-537 and ENH-538 still active; corrected line numbers (info.py 62-84→215-237, __init__.py 127-131→189-197, test classes 135/182→251/298)
- `/ll:ready-issue` - 2026-03-09T01:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74f9e39e-c3bf-48c6-aaac-9fe47e01c93e.jsonl` — CORRECTED: ENH-537 and ENH-538 confirmed completed; removed from Blocked By
- `/ll:verify-issues` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9511adcf-591f-4199-b7c1-7ff5d368c8f0.jsonl` — DEP_ISSUES: removed completed ENH-668 from Blocked By
- `/ll:ready-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b127a26e-89b4-4ff9-9b9c-bfe355a44c02.jsonl` — BLOCKED: ENH-541 still active; corrected line numbers (info.py 215-237→297-325, __init__.py 189-197→205-220, tests 251/298→324/371); noted --json/--verbose/--full already implemented via ENH-740

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

## Resolution

**Implemented** on 2026-03-21 by `/ll:manage-issue feature implement FEAT-543`

### Changes

- `scripts/little_loops/text_utils.py`: Added `parse_duration(s: str) -> int` — parses `"1h"`, `"30m"`, `"2d"`, `"45s"` into seconds; raises `ValueError` on bad input
- `scripts/little_loops/cli/loop/__init__.py`: Added `--event`/`-e`, `--state`/`-s`, `--since` args to `history_parser`
- `scripts/little_loops/cli/loop/info.py`: Implemented `--event`, `--state`, `--since` filtering in `cmd_history()` — filters applied after `action_output` pre-filter and before `--tail` slice
- `scripts/tests/test_ll_loop_parsing.py`: Added `TestParseDuration` class (8 tests)
- `scripts/tests/test_ll_loop_commands.py`: Added `TestHistoryFiltering` class with `mixed_events_file` fixture (6 tests)

### Verification

- 3810 tests passed, 4 skipped — full suite clean
- `ruff check` — all checks passed
- `mypy` — no issues found in 3 source files

## Session Log
- `/ll:manage-issue` - 2026-03-21T05:18:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d1483dac-eb16-416c-b40a-40b278600abf.jsonl`

## Status

**Completed** | Created: 2026-03-03 | Completed: 2026-03-21 | Priority: P4
