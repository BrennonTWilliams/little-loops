# Implementation Plan: FEAT-543 — ll-loop history filtering

**Date**: 2026-03-21
**Issue**: FEAT-543
**Action**: implement

## Summary

Add `--event`, `--state`, and `--since` filtering flags to `ll-loop history`. Implement a shared `parse_duration()` utility in `text_utils.py` for the `--since` duration parsing.

## Files to Modify

1. `scripts/little_loops/text_utils.py` — add `parse_duration()`
2. `scripts/little_loops/cli/loop/__init__.py` — add 3 new args to `history_parser`
3. `scripts/little_loops/cli/loop/info.py` — add filtering in `cmd_history()`
4. `scripts/tests/test_ll_loop_parsing.py` — add `TestParseDuration` class
5. `scripts/tests/test_ll_loop_commands.py` — add `TestHistoryFiltering` class

## Phase 0: Write Tests (Red)

### TestParseDuration (test_ll_loop_parsing.py)

- `parse_duration("1h") == 3600`
- `parse_duration("30m") == 1800`
- `parse_duration("2d") == 172800`
- `parse_duration("45s") == 45`
- Invalid string raises `ValueError`

### TestHistoryFiltering (test_ll_loop_commands.py)

`mixed_events_file` fixture: JSONL with state_enter, evaluate, route, action_start events with varied states and timestamps.

- `test_event_filter_evaluate` — `--event evaluate` returns only evaluate events
- `test_state_filter_check` — `--state check` returns events where state/from/to == "check"
- `test_since_filter_excludes_old_events` — `--since 1h` excludes events older than 1h
- `test_combined_event_and_state_filter` — `--event route --state check` combinator
- `test_tail_applied_after_filter` — `--event state_enter --tail 1` returns last 1 of filtered
- `test_no_filter_behavior_unchanged` — no flags shows all events (behavior unchanged)

## Phase 1: parse_duration() in text_utils.py

```python
_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}

def parse_duration(s: str) -> int:
    """Parse a duration string like '1h', '30m', '2d' into seconds."""
    m = re.match(r"^(\d+)([smhd])$", s)
    if not m:
        raise ValueError(f"Invalid duration: {s!r}. Use e.g. 1h, 30m, 2d, 45s")
    return int(m.group(1)) * _DURATION_UNITS[m.group(2)]
```

## Phase 2: history_parser args in __init__.py

After line 247 (`--json` arg), add:

```python
history_parser.add_argument("--event", "-e", type=str, help="Filter by event type (e.g. evaluate, route)")
history_parser.add_argument("--state", "-s", type=str, help="Filter by state name (matches state, from, or to fields)")
history_parser.add_argument("--since", type=str, metavar="DURATION", help="Filter to events within duration window (e.g. 1h, 30m, 2d)")
```

## Phase 3: Filtering in cmd_history() in info.py

After the `action_output` pre-filter (line 429), before `events[-tail:]`:

```python
# Apply event-type filter
event_filter = getattr(args, "event", None)
if event_filter:
    events = [e for e in events if e.get("event") == event_filter]

# Apply state filter (matches state, from, or to fields)
state_filter = getattr(args, "state", None)
if state_filter:
    events = [e for e in events if (
        e.get("state") == state_filter
        or e.get("from") == state_filter
        or e.get("to") == state_filter
    )]

# Apply since (time window) filter
since_str = getattr(args, "since", None)
if since_str:
    from little_loops.text_utils import parse_duration
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(seconds=parse_duration(since_str))
    events = [
        e for e in events
        if datetime.fromisoformat(e["ts"].replace("Z", "+00:00")).replace(tzinfo=None) >= cutoff
    ]
```

Then existing `events[-tail:]` applies as final limit.

## Success Criteria

- [x] `parse_duration("1h") == 3600`
- [ ] `--event evaluate` on mixed events shows only evaluate rows
- [ ] `--state check` on mixed events shows only events touching state "check"
- [ ] `--since 1h` excludes events older than 1 hour
- [ ] Combined `--event route --state check` works
- [ ] `--tail` still applies as the final limit after filters
- [ ] No-flag behavior unchanged
- [ ] All existing tests pass (Green)
- [ ] Lint and type checks pass
