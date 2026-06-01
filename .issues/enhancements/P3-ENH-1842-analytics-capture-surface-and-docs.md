---
id: ENH-1842
type: ENH
priority: P3
status: open
discovered_date: 2026-06-01
parent: ENH-1835
relates_to:
- ENH-1835
- ENH-1840
labels:
- enhancement
size: Small
---

# ENH-1842: Analytics capture surface layer — ll-doctor reporting and documentation

## Summary

Expose `analytics.capture` config state in `ll-doctor`, fix misleading error strings in
`ctx_stats.py`, and update all documentation references (`CONFIGURATION.md`, `CLI.md`,
`API.md`, `HOST_COMPATIBILITY.md`). This child can be worked in parallel with ENH-1841
after ENH-1840 (the config layer) lands.

## Parent Issue

Decomposed from ENH-1835: Make tracked skills and CLI commands configurable in ll-config.json

## Prerequisites

ENH-1840 (config layer) must be merged first — `BRConfig.analytics_capture` property
is consumed here.

## Implementation Steps

### Tests first (TDD mode enabled)

1. **`scripts/tests/test_cli_doctor.py`** — Add test methods to `TestMainDoctor` (create if absent)
   covering the new analytics capture-state reporting block:
   - Configure mock `BRConfig` with `analytics_capture` returning an `AnalyticsCaptureConfig` instance
   - Assert the capture state section appears in output with correct enabled/disabled labels
   - Test both "all enabled" (defaults) and "file_events disabled" states

### Implementation

2. **`scripts/little_loops/cli/doctor.py::main_doctor()`** — Add new reporting block that:
   - Loads raw config using the existing `_load_config` pattern from hooks
   - Reads `BRConfig.analytics_capture` (or `AnalyticsCaptureConfig.from_dict(raw)`)
   - Prints capture category state using existing `_STATUS_SYMBOLS` dict:
     ```
     Analytics Capture:
       skills:        ✓ ["*"]
       cli_commands:  ✓ ["*"]
       corrections:   ✓ enabled
       file_events:   ✗ disabled
     ```
   - Note: `main_doctor()` currently delegates to `runner.describe_capabilities()` only — this
     is a new section added after that existing output.

3. **`scripts/little_loops/cli/ctx_stats.py::main_ctx_stats()`** — Update error strings at
   ~lines 220 and ~286 that read `"set analytics.enabled: true in .ll/ll-config.json"` to also
   mention `analytics.capture.file_events` as a second reason data may be absent. Suggested:
   `"Enable analytics (analytics.enabled: true) and ensure analytics.capture.file_events is not disabled"`

### Documentation

4. **`docs/reference/CONFIGURATION.md`** — Add `analytics.capture` keys section documenting
   `skills`, `cli_commands`, `corrections`, `file_events` with their defaults, types, and examples.

5. **`docs/reference/CLI.md`** — Update `### ll-doctor` section (~lines 115–143) to reflect the
   new "Capture Config" section in `ll-doctor` output format.

6. **`docs/reference/API.md`** — `main_ctx_stats` docstring (~line 3496) reads
   `"Enable per-tool byte tracking by setting \"analytics\": {\"enabled\": true}"` — supplement
   to mention `analytics.capture` as the per-category control.

7. **`docs/reference/HOST_COMPATIBILITY.md`** — ~line 214 states `ll-doctor` "prints a
   `CapabilityReport`"; add note that it also reports config-state when `analytics.capture` is
   configured.

## Acceptance Criteria

- `ll-doctor` output includes a "Analytics Capture" section showing per-category state
- `ctx_stats.py` error strings mention both `analytics.enabled` and `analytics.capture.file_events`
- `CONFIGURATION.md` documents all four new keys with defaults
- `CLI.md` `ll-doctor` section reflects the new output
- `TestMainDoctor` capture-state tests pass

## Files to Modify

- `scripts/little_loops/cli/doctor.py`
- `scripts/little_loops/cli/ctx_stats.py`
- `docs/reference/CONFIGURATION.md`
- `docs/reference/CLI.md`
- `docs/reference/API.md`
- `docs/reference/HOST_COMPATIBILITY.md`
- `scripts/tests/test_cli_doctor.py`

## Depends On

- ENH-1840 (config layer — `BRConfig.analytics_capture` property)

## Can run in parallel with

- ENH-1841 (write-path gating) — both depend on ENH-1840 but are otherwise independent

## Impact

- **Priority**: P3
- **Effort**: Small — doctor block + error string fixes + doc updates
- **Risk**: Low — purely surface/documentation changes

## Session Log
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c1325861-5c8a-40ab-90ee-ac4727f376b5.jsonl`
