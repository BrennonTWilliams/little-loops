---
id: ENH-1704
priority: P4
type: ENH
status: open
parent: ENH-1670
depends_on:
- ENH-1703
---

# ENH-1704: Foreground log capture — config schema and documentation

## Summary

Add `loop.capture_foreground_logs` to `config-schema.json` and document the new `--log`/`--capture` flag and config key in the reference docs. Follows ENH-1703 which implements and ships the feature.

## Parent Issue

Decomposed from ENH-1670: Optional log capture for foreground runs (tee to `{instance_id}.log`)

## Proposed Solution

### Config schema

In `config-schema.json`, add `loop.capture_foreground_logs` as a boolean property with default `false` and a short description, consistent with the existing loop config schema structure.

### Documentation

1. **`docs/reference/CLI.md`** — Document the new `--log`/`--capture` flag on `ll-loop run` and `ll-loop resume` in the flag reference table.

2. **`docs/guides/LOOPS_GUIDE.md`** — Add a note about the `--log` option in the monitoring/debugging section explaining when to use it (post-hoc inspection of foreground run output).

3. **`docs/reference/CONFIGURATION.md`** — In the `### loops` table (~line 479), add a new row for `capture_foreground_logs` (boolean, default `false`, description: tee foreground stdout/stderr to `{instance_id}.log`). Also update the Full Configuration Example block (~line 159) to include the key.

## Acceptance Criteria

- `config-schema.json` validates a config containing `{"loop": {"capture_foreground_logs": true}}` without errors
- `docs/reference/CLI.md` lists `--log`/`--capture` with accurate description
- `docs/reference/CONFIGURATION.md` `### loops` table includes `capture_foreground_logs` row
- Full Configuration Example in CONFIGURATION.md includes the key

## Files to Modify

- `config-schema.json`
- `docs/reference/CLI.md`
- `docs/guides/LOOPS_GUIDE.md`
- `docs/reference/CONFIGURATION.md`

## Session Log
- `/ll:issue-size-review` - 2026-05-25T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/49c875d1-35f0-42f5-a121-41c0c7663183.jsonl`
