---
id: ENH-2617
type: ENH
priority: P3
status: open
captured_at: 2026-07-12T19:49:49Z
discovered_date: 2026-07-12
discovered_by: scope-epic
parent: EPIC-2616
---

# Shared queue entry read/prune helper

## Summary

Extract a shared helper for reading `.loops/.queue/*.json` entries with
dead-PID pruning, so `ll-loop queue list`/`ll-loop queue remove` and the
existing `_is_earliest_waiter()` (`scripts/little_loops/cli/loop/_helpers.py:172`)
share one implementation of "what's actually in the queue right now."

## Implementation

Factor the entry-loading loop currently inline in `_is_earliest_waiter()`
(glob `*.json`, parse, check `context.pid` liveness via `_process_alive()`,
`f.unlink(missing_ok=True)` on dead PIDs, sort by `enqueuedAt`) into a
standalone function, e.g. `read_queue_entries(queue_dir: Path) -> list[dict]`,
that returns the live, sorted entries and prunes dead ones as a side effect.
Update `_is_earliest_waiter()` to call it instead of duplicating the loop.

## Session Log
- `/ll:scope-epic` - 2026-07-12T19:49:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8999ce06-5d43-4dd5-bc03-841f57c28bf2.jsonl`
