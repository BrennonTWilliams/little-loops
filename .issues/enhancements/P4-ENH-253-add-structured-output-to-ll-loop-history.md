---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
---

# ENH-253: Add structured output formats to ll-loop history

## Summary

`ll-loop history` only outputs plain text, unlike `ll-history` which supports `--json`, `--format markdown`, and `--format yaml`. Since loop events are already stored as JSONL internally, adding structured output would be trivial and enable piping into analysis tools.

## Location

- **File**: `scripts/little_loops/cli.py`
- **Line(s)**: 1029-1045 (at scan commit: a8f4144)
- **Anchor**: `in function cmd_history inside main_loop`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/cli.py#L1029-L1045)
- **Code**:
```python
def cmd_history(loop_name: str) -> int:
    events = get_loop_history(loop_name)
    tail = getattr(args, "tail", 50)
    for event in events[-tail:]:
        ts = event.get("ts", "")[:19]
        event_type = event.get("event", "")
        details = {k: v for k, v in event.items() if k not in ("event", "ts")}
        print(f"{ts} {event_type}: {details}")
    return 0
```

## Current Behavior

Plain text output only.

## Expected Behavior

Support `--json` and `--format` flags for structured output.

## Proposed Solution

Add `--json` flag and `--format` argument to the history subparser. When `--json` is used, output the events as a JSON array.

## Impact

- **Severity**: Low
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `priority-p4`

---

## Status
**Open** | Created: 2026-02-06T03:41:30Z | Priority: P4
