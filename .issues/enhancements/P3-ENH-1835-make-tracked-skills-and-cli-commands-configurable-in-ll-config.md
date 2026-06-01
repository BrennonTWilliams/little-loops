---
id: ENH-1835
type: ENH
priority: P3
status: open
discovered_date: 2026-06-01
captured_at: "2026-06-01T01:10:54Z"
discovered_by: capture-issue
relates_to:
  - ENH-1833
  - ENH-1834
  - ENH-1831
labels:
  - enhancement
  - captured
---

# ENH-1835: Make tracked skills and CLI commands configurable in ll-config.json

## Summary

Once skill invocations (ENH-1833), CLI invocations (ENH-1834), and user corrections
(ENH-1831) are being captured in `history.db`, users should be able to control
which events are tracked via `ll-config.json`. The config schema (`config-schema.json`
in the repo root) should be updated to reflect these options.

## Motivation

Not all projects need full capture. A project-level allowlist/blocklist for tracked
skill names, CLI binaries, and correction heuristics prevents unwanted data collection
and keeps the DB from growing unbounded on high-volume projects.

## Acceptance Criteria

- `ll-config.json` accepts a new `analytics.capture` section with sub-keys:
  - `skills: ["*"]` — glob/list of skill names to capture (default: all)
  - `cli_commands: ["*"]` — list of CLI binaries to capture (default: all)
  - `corrections: true` — enable/disable user correction capture (default: true)
  - `file_events: true` — enable/disable file_events capture (default: true)
- `config-schema.json` is updated with the new keys and their types/defaults
- All capture write paths (ENH-1831, ENH-1832, ENH-1833, ENH-1834) consult
  `analytics.capture` before writing
- `ll-doctor` reports which capture categories are enabled/disabled
- Documentation in `docs/reference/CONFIGURATION.md` covers the new keys

## Implementation Steps

1. Add `analytics.capture` block to `config-schema.json` with JSON Schema types
2. Add `feature_enabled_for(config, "analytics.capture.skills", skill_name)`
   helper to `config_loader.py` that handles glob matching
3. Thread the config check into each capture write path added by ENH-1831–1834
4. Update `ll-doctor` to report capture config state
5. Update `docs/reference/CONFIGURATION.md`

## Files to Modify

- `config-schema.json` — new `analytics.capture` block
- `scripts/little_loops/config_loader.py` — `feature_enabled_for()` helper
- Capture write-path files from ENH-1831, ENH-1832, ENH-1833, ENH-1834
- `scripts/little_loops/cli/doctor.py` — capture config reporting
- `docs/reference/CONFIGURATION.md` — new keys documentation

## Depends On

- ENH-1831, ENH-1832, ENH-1833, ENH-1834 (the write paths this configures)

## Session Log
- `/ll:capture-issue` - 2026-06-01T01:10:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
