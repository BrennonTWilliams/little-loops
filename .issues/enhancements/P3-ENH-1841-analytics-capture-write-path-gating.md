---
id: ENH-1841
type: ENH
priority: P3
status: done
discovered_date: 2026-06-01
completed_at: 2026-06-01 06:52:16+00:00
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
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
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

## Current Behavior

`write_file_event()` (called from `post_tool_use.py`) and `record_correction()` (called from
`user_prompt_submit.py`) execute unconditionally whenever the top-level `analytics.enabled`
flag is true. There is no way to disable individual capture write paths (file events vs.
corrections) without disabling all analytics.

## Expected Behavior

Each write path is gated by its own `analytics.capture.*` flag:
- `analytics.capture.file_events: false` suppresses `write_file_event()` at both the hook and
  session-store level
- `analytics.capture.corrections: false` suppresses `record_correction()` at both the hook and
  session-store level
- When the `capture` key is absent from config, all writes proceed (safe default — no behavior change)

## Motivation

ENH-1840 added the `AnalyticsCaptureConfig` schema and `feature_enabled_for()` helper but left the
actual call-site gating unimplemented. Users who want fine-grained control over what analytics data
is written cannot yet exercise those config flags — this issue wires the config layer into the write
paths to make it operational.

## Scope Boundaries

- **In scope**: `file_events` and `corrections` gates in hook handlers and `session_store.py`
- **Out of scope**: `analytics.capture.skills` and `analytics.capture.cli_commands` gates — these
  depend on ENH-1833/ENH-1834 (skill/CLI event infrastructure not yet implemented); only TODO
  markers are placed at those call sites
- **Out of scope**: Changes to the config schema, `AnalyticsCaptureConfig` class, or `BRConfig` — those
  are already complete in ENH-1840

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

## Integration Map

### Files to Modify

| File | What changes |
|------|-------------|
| `scripts/little_loops/hooks/post_tool_use.py` | After `analytics.enabled` early-return at line 99, add `analytics.capture.file_events` gate before the `write_file_event()` call (Block 2, line ~135) |
| `scripts/little_loops/hooks/user_prompt_submit.py` | Inside the `analytics.enabled` positive guard (line 69), add `analytics.capture.corrections` check before `record_correction()` at line 73 |
| `scripts/little_loops/session_store.py` | `write_file_event()` (line 304) — activate its existing `config` param. `record_correction()` (line 332) — **add** `config: dict \| None = None` param (it does not have one yet), then implement the gate |

### Dependent Files (Callers of write path functions)

- `scripts/little_loops/hooks/post_tool_use.py` — calls `write_file_event()` at ~line 140
- `scripts/little_loops/hooks/user_prompt_submit.py` — calls `record_correction()` at line 73

### Config Layer (ENH-1840, already merged)

- `scripts/little_loops/config/features.py` — defines `AnalyticsCaptureConfig` (line 404) with `file_events: bool = True` and `corrections: bool = True`; also `feature_enabled_for()` (line 38) and `feature_enabled()` (line 14)
- `scripts/little_loops/config/core.py` — `BRConfig.analytics_capture` property (line 306) wraps `AnalyticsCaptureConfig.from_dict()`

### Similar Patterns

- `scripts/little_loops/hooks/post_tool_use.py:99` — existing `analytics.enabled` guard, same early-return idiom
- `scripts/little_loops/hooks/user_prompt_submit.py:69` — existing `analytics.enabled` positive-guard, different structure (prompt optimization still runs after)
- `scripts/tests/test_config.py:TestFeatureEnabledForHelper` (line 1107) — tests `feature_enabled_for()` with `analytics.capture.skills` patterns

### Tests

- `scripts/tests/test_hook_post_tool_use.py` — `_write_config()` helper (line 85) and `TestFileEventsWrite` class to extend
- `scripts/tests/test_hook_user_prompt_submit.py` — `_write_config()` helper (line 30) and test class to extend
- `scripts/tests/test_session_store.py` — for session-store-level gating tests

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_session.py` — calls `record_correction(db, ..., "user_prompt_submit")` with 4-arg form to seed test data in `TestRecentKindFilter.test_recent_correction_kind`; won't break when `config` is added as optional 5th param (default `None`), but confirms the "no config = writes proceed" default must hold

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical: `record_correction()` does not have a `config` param.** The implementation step 5 says "both already have `config: dict | None = None` forward-compat params" — this is only true for `write_file_event()` (line 310). `record_correction()` at line 332 has no `config` param and must have one added as part of this implementation.

**Use `AnalyticsCaptureConfig.from_dict()`, not `feature_enabled_for()`, for boolean gates.** `feature_enabled_for()` is for glob-pattern list matching (`skills`, `cli_commands`); calling it on a boolean value (`file_events: true`) causes a `TypeError`. `feature_enabled()` would work but defaults to `False` for missing keys — violating the acceptance criterion that missing `capture` key leaves writes proceeding. The correct idiom:

```python
from little_loops.config.features import AnalyticsCaptureConfig

capture = AnalyticsCaptureConfig.from_dict(config.get("analytics", {}).get("capture", {}))
if not capture.file_events:   # defaults to True when key absent
    return
```

**Mock strategy for new gating tests.** Existing tests mock `session_store.connect` to exercise the error-suppression path. The new gating tests need to assert that `write_file_event` / `record_correction` are *not called* — patch those functions directly:

```python
monkeypatch.setattr(session_store, "write_file_event", mock_fn)
# assert mock_fn.call_count == 0
```

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **`scripts/tests/test_session_store.py::TestRecordCorrection`** — Add two tests for session-store-level gating (covers the "regardless of call site" acceptance criterion — no corresponding hook is involved):
   - `test_record_correction_gate_disabled`: call `record_correction(db, ..., config={"analytics": {"capture": {"corrections": False}}})` → assert zero rows in `user_corrections`
   - `test_write_file_event_gate_disabled`: call `write_file_event(db, ..., config={"analytics": {"capture": {"file_events": False}}})` → assert zero rows in `file_events`
   
   Note: existing `TestRecordCorrection` tests call `record_correction` with 4 positional args and no `config` — they will continue to pass as long as `config=None` means "gate permissive" (satisfying the "default behavior unchanged" acceptance criterion).

## Depends On

- ENH-1840 (config layer — `feature_enabled_for`, `AnalyticsCaptureConfig`)

## Impact

- **Priority**: P3
- **Effort**: Small-Medium — mechanical threading through ~5 files, tests first
- **Risk**: Low — safe defaults; no behavior change unless user sets `capture.*: false`

## Resolution

Implemented all three write-path gates (ENH-1841):
- `write_file_event()` in `session_store.py`: activated existing `config` param — gates on `analytics.capture.file_events`
- `record_correction()` in `session_store.py`: added `config` param — gates on `analytics.capture.corrections`
- `post_tool_use.py::handle()`: added `AnalyticsCaptureConfig` guard before `write_file_event` block
- `user_prompt_submit.py::handle()`: added `AnalyticsCaptureConfig` guard before `record_correction` call
- TDD: 6 new tests (2 hook-level × 2 write paths + 2 session-store-level), all pass; full suite green (8552 passed)

## Session Log
- `/ll:manage-issue` - 2026-06-01T06:52:16Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:ready-issue` - 2026-06-01T06:45:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c37ab7c3-de9e-4aef-8f6b-474c7023dd06.jsonl`
- `/ll:refine-issue` - 2026-06-01T06:34:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/19a20223-d604-4118-89e8-42bc4ddf3f59.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c1325861-5c8a-40ab-90ee-ac4727f376b5.jsonl`
- `/ll:wire-issue` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2708ad88-2df1-4118-9ecd-5de04215d25e.jsonl`
