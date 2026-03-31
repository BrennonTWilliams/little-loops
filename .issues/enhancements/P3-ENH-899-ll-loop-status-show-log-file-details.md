---
discovered_date: 2026-03-31
discovered_by: capture-issue
---

# ENH-899: `ll-loop status` Should Show Log File Details

## Summary

The `ll-loop status` command currently shows basic loop state (name, status, current state, iteration, timestamps, PID) but omits useful information available in the loop's log file (`.loops/.running/<name>.log`). Adding log file path, last modified time, and last event would give operators better situational awareness without needing to manually find and tail the log.

## Current Behavior

`ll-loop status <name>` outputs:

```
Loop: eval-refine-auto-cycle
Status: running
Current state: run_eval
Iteration: 7
Started: 2026-03-31T05:19:44.874437+00:00
Updated: 2026-03-31T12:24:26.122628+00:00
PID: 478566 (running)
```

No log file information is shown. Users must know the log path convention and manually inspect it.

## Expected Behavior

`ll-loop status <name>` should additionally show:

```
Log: .loops/.running/eval-refine-auto-cycle.log
Log updated: 3m ago
Last event: [STATE] run_eval → evaluating (iteration 7)
```

Specifically:
- **Log path**: Relative path to the log file
- **Log updated**: Human-readable time since the log file was last modified (e.g., "3m ago", "1h ago")
- **Last event**: The last meaningful log line (state transition, error, or status message)

## Motivation

When monitoring long-running loops, the current status output lacks the most actionable information: what the loop last did and how recently. Users frequently need to `tail` the log manually to check if a loop is stuck or progressing. Surfacing this in `status` saves a step and makes loop monitoring more self-service.

## Proposed Solution

In the `cmd_status` function within the loop CLI info module:

1. Derive the log file path from the loop name using the `.loops/.running/<name>.log` convention
2. If the log file exists:
   - Show its relative path
   - Calculate and display time since last modification using `os.path.getmtime()`
   - Read the last non-empty line and display it as "Last event"
3. If the log file doesn't exist, show `Log: (not found)`

Time formatting should use a helper that produces human-readable relative times (e.g., "2m ago", "1h 23m ago", "3d ago").

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `cmd_status` function

### Dependent Files (Callers/Importers)
- N/A — `cmd_status` is a CLI endpoint

### Similar Patterns
- `cmd_list` in the same module may benefit from log info, but that's out of scope

### Tests
- `scripts/tests/` — add or update tests for `cmd_status` log output

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Locate the log file path derivation logic (already used when starting loops)
2. Add log file info (path, mtime, last line) to `cmd_status` output
3. Add a relative time formatting helper if one doesn't already exist
4. Add tests for the new output fields

## Impact

- **Priority**: P3 - Quality of life improvement for loop monitoring
- **Effort**: Small - Reads an existing file and appends a few output lines
- **Risk**: Low - Additive change to output, no breaking changes
- **Breaking Change**: No

## Scope Boundaries

- Only `ll-loop status` is in scope; `ll-loop list` and `ll-loop show` are not
- No changes to log file format or location
- No interactive/follow mode (that would be a separate feature)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `cli`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-31T12:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/705d8dcf-207a-4293-9698-d61e0449c1de.jsonl`

---

## Status

**Open** | Created: 2026-03-31 | Priority: P3
