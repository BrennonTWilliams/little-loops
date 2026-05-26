---
id: ENH-1704
priority: P4
type: ENH
status: open
parent: ENH-1670
depends_on:
- ENH-1703
---

# ENH-1704: Foreground log capture — documentation

## Summary

Document the always-on foreground log capture introduced in ENH-1703. Foreground runs now always write to `{instance_id}.log`; users should know where to find it and what it contains.

No config schema changes — the opt-in `capture_foreground_logs` key was dropped when the design shifted to always-on.

## Parent Issue

Decomposed from ENH-1670: Automatic log capture parity for foreground runs

## Proposed Solution

1. **`docs/reference/CLI.md`** — Add a note under `ll-loop run` and `ll-loop resume` that foreground runs always tee stdout/stderr to `{instance_id}.log` in the running directory, with ANSI codes stripped.

2. **`docs/guides/LOOPS_GUIDE.md`** — In the monitoring/debugging section, explain that foreground run output is preserved in `{instance_id}.log` for post-hoc inspection (`tail -f`, `grep`).

## Acceptance Criteria

- `docs/reference/CLI.md` describes the automatic log file for foreground runs
- `docs/guides/LOOPS_GUIDE.md` references `{instance_id}.log` in its debugging guidance

## Files to Modify

- `docs/reference/CLI.md`
- `docs/guides/LOOPS_GUIDE.md`

## Session Log
- `/ll:issue-size-review` - 2026-05-25T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/49c875d1-35f0-42f5-a121-41c0c7663183.jsonl`
- Design revised to always-on (dropped config schema and CONFIGURATION.md changes) - 2026-05-26
