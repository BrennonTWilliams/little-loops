---
id: ENH-1841
type: ENH
priority: P3
status: open
discovered_date: 2026-06-01
parent: ENH-1835
relates_to:
- ENH-1835
- ENH-1840
- ENH-1831
- ENH-1832
- ENH-1833
- ENH-1834
labels:
- enhancement
size: Medium
---

# ENH-1841: Analytics capture write-path gating

## Summary

Thread `analytics.capture` config checks into the capture write paths: add a
`file_events` gate in `post_tool_use.py`, a `corrections` gate in
`user_prompt_submit.py`, and implement the actual gating logic inside
`session_store.py::write_file_event()` and `record_correction()` so gating works
even when those functions are called outside a hook context. Includes TDD test
coverage for both gates.

## Parent Issue

Decomposed from ENH-1835: Make tracked skills and CLI commands configurable in ll-config.json

## Prerequisites

ENH-1840 (config layer) must be merged first — this issue consumes `feature_enabled_for()`
and `AnalyticsCaptureConfig`.

Note: `analytics.capture.skills` and `analytics.capture.cli_commands` gates cannot
be wired until ENH-1833 (skill events) and ENH-1834 (CLI events) are implemented.
Place `# TODO(ENH-1835): wire when ENH-1833/ENH-1834 land` markers at those call sites.

## Implementation Steps

### Tests first (TDD mode enabled)

1. **`scripts/tests/test_hook_post_tool_use.py`** — Update `_write_config()` helper to accept
   `analytics_capture: dict | None = None` kwarg that merges into `analytics:` block. Add test methods
   to `TestFileEventsWrite`:
   - `test_file_events_gate_disabled`: analytics enabled at top level, `capture.file_events: false` →
     `write_file_event()` NOT called
   - `test_file_events_gate_enabled_explicitly`: `capture.file_events: true` → `write_file_event()` called

2. **`scripts/tests/test_hook_user_prompt_submit.py`** — Same pattern: extend `_write_config()`, add:
   - `test_corrections_gate_disabled`: `capture.corrections: false` → `record_correction()` NOT called
   - `test_corrections_gate_enabled_explicitly`: `capture.corrections: true` → `record_correction()` called

### Implementation

3. **`scripts/little_loops/hooks/post_tool_use.py::handle()`** — After the existing
   `feature_enabled(config, "analytics.enabled")` guard, add:
   ```python
   if not feature_enabled_for(config, "analytics.capture.file_events", ...):
       return
   ```
   Use `AnalyticsCaptureConfig.from_dict()` or `feature_enabled()` with the nested key path.

4. **`scripts/little_loops/hooks/user_prompt_submit.py::handle()`** — After existing
   `feature_enabled(config, "analytics.enabled")` guard, add `analytics.capture.corrections` gate
   before `record_correction()` call.

5. **`scripts/little_loops/session_store.py`** — Inside `write_file_event()` and `record_correction()`,
   both already have `config: dict | None = None` forward-compat params. Implement the actual gating
   logic inside these functions (not only at hook call sites) using `feature_enabled_for()` /
   `feature_enabled()` so gating works when these functions are called outside hook context.

## Acceptance Criteria

- `write_file_event()` is skipped when `analytics.capture.file_events: false` regardless of call site
- `record_correction()` is skipped when `analytics.capture.corrections: false` regardless of call site
- Default behavior (no `capture` key in config) is unchanged — all writes proceed
- All new test methods pass

## Files to Modify

- `scripts/little_loops/hooks/post_tool_use.py`
- `scripts/little_loops/hooks/user_prompt_submit.py`
- `scripts/little_loops/session_store.py`
- `scripts/tests/test_hook_post_tool_use.py`
- `scripts/tests/test_hook_user_prompt_submit.py`

## Depends On

- ENH-1840 (config layer — `feature_enabled_for`, `AnalyticsCaptureConfig`)

## Impact

- **Priority**: P3
- **Effort**: Small-Medium — mechanical threading through ~5 files, tests first
- **Risk**: Low — safe defaults; no behavior change unless user sets `capture.*: false`

## Session Log
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c1325861-5c8a-40ab-90ee-ac4727f376b5.jsonl`
