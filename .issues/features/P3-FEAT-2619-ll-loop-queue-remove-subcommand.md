---
id: FEAT-2619
type: FEAT
priority: P3
status: open
captured_at: 2026-07-12T19:49:49Z
discovered_date: 2026-07-12
discovered_by: scope-epic
parent: EPIC-2616
depends_on: [ENH-2617]
---

# `ll-loop queue remove <id>` subcommand

## Summary

Add `ll-loop queue remove <id>` to cancel a queued waiter: verify the
tracked PID's identity (not just liveness) before signaling it, terminate
the waiting process, and delete its `.loops/.queue/<id>.json` entry. Must
not affect the currently-running (lock-holding) loop, only a waiter blocked
in `--queue`.

## Session Log
- `/ll:scope-epic` - 2026-07-12T19:49:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8999ce06-5d43-4dd5-bc03-841f57c28bf2.jsonl`
