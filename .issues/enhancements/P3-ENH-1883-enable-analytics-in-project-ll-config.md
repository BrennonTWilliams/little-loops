---
id: ENH-1883
type: ENH
priority: P3
status: done
discovered_date: 2026-06-02
captured_at: '2026-06-02T23:39:38Z'
completed_at: '2026-06-03T01:01:44Z'
discovered_by: capture-issue
relates_to:
- EPIC-1707
- ENH-1833
- ENH-1835
- ENH-1832
- ENH-1831
- BUG-1881
labels:
- enhancement
- captured
confidence_score: 100
outcome_confidence: 86
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1883: Enable `analytics.enabled` in project's own `.ll/ll-config.json`

## Summary

The project's `.ll/ll-config.json` has no `analytics` key. The `analytics.enabled` flag defaults to `False`, so `skill_events`, `file_events`, and `user_corrections` writes in `user_prompt_submit.py` and `post_tool_use.py` are gated out. EPIC-1707 consumer features (ENH-1708: corrections wired into refine-issue/ready-issue) read from tables that are never written to. This project is the primary testbed for history.db features and should have analytics enabled.

## Current Behavior

`.ll/ll-config.json` contains no `analytics` key. `feature_enabled(config, "analytics.enabled")` returns `False`. Despite all write-path infrastructure being implemented (ENH-1831–1835 all done), the following tables have 0 rows:
- `skill_events` — `/ll:` skill invocations never recorded
- `user_corrections` — correction detection never fires
- `file_events` — even when BUG-1881 is fixed, gated out here too

## Expected Behavior

`.ll/ll-config.json` includes:
```json
"analytics": {
  "enabled": true,
  "capture": {
    "skills": ["*"],
    "cli_commands": ["*"],
    "corrections": true,
    "file_events": true
  }
}
```

After this change, each `/ll:` invocation creates a `skill_events` row. User correction patterns (e.g. "no, don't do that") are detected and written to `user_corrections`. File touch events flow into `file_events` (once BUG-1881 is also fixed). ENH-1708's reads from `user_corrections` in `refine-issue`/`ready-issue` have actual data.

## Motivation

- The project uses EPIC-1707 consumer features (`ll-history-context`, corrections in confidence-check) but has zero data in the tables those features query.
- `ll-ctx-stats` always falls back to the static `.ll/ll-context-state.json` because `tool_events`/`file_events` are empty — the analytics command is not exercised in the project's own workflow.
- This is a one-line config change that unlocks the entire analytics write path without any code changes.

## Proposed Solution

Add an `analytics` block to `.ll/ll-config.json` with `enabled: true` and default-inclusive capture settings. Additionally, verify `config-schema.json` already has the `analytics` property block (FEAT-1623 was supposed to add it) so config validation doesn't reject the new key.

## Scope Boundaries

- **Out of scope**: Adding new analytics infrastructure — already implemented via ENH-1831–1835
- **Out of scope**: Fixing `post_tool_use.py` Python handler wiring — tracked separately in BUG-1881
- **Out of scope**: Analytics dashboards or reporting UI
- **Out of scope**: Changing the `analytics` schema shape — use the existing `AnalyticsCaptureConfig` structure as-is

## Integration Map

### Files to Modify
- `.ll/ll-config.json` — add `analytics` block
- `config-schema.json` — verify `analytics` property exists; add if missing

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/user_prompt_submit.py` — `handle()` gates correction detection and `record_skill_event()` at `if config is not None and feature_enabled(config, "analytics.enabled"):` (line ~70); both paths are inside this single outer gate
- `scripts/little_loops/hooks/post_tool_use.py` — `handle()` gates `tool_events` INSERT and `write_file_event()` at `if config is not None and feature_enabled(config, "analytics.enabled"):` (line ~151); `tool_events` is written via inline SQL (not a named session_store function)
- `scripts/little_loops/session_store.py` — `record_correction()` (line ~382), `record_skill_event()` (line ~415), `write_file_event()` (line ~348); each has a secondary internal gate on the `config.capture.*` sub-flag but assumes the caller already checked `analytics.enabled`
- `scripts/little_loops/config/core.py` — `BRConfig._parse_config()` constructs `AnalyticsCaptureConfig.from_dict(self._raw_config.get("analytics", {}).get("capture", {}))` (line ~221); `analytics.enabled` itself is not stored in a typed field — it is read on demand via `feature_enabled()` from `_raw_config`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/ctx_stats.py` — `main_ctx_stats()` emits a `logger.warning()` ("No analytic rows in .ll/history.db — enable analytics...") when `tool_events` has zero rows; this warning will stop appearing once analytics is enabled and tool calls are processed; no code change needed, purely behavioral
- `scripts/little_loops/cli/doctor.py` — `main_doctor()` calls `_print_capture_section(cfg.analytics_capture)` to render the analytics capture sub-flags; once the explicit `analytics.capture` block is added, `BRConfig._analytics_capture` reads from the file rather than `from_dict({})`; output is identical since the proposed values match the defaults

### Similar Patterns
- `.ll/ll-config.json` — `context_monitor` block (`"enabled": true`) follows the same opt-in pattern; its presence confirms the minimal form `"analytics": { "enabled": true }` is valid (capture sub-keys default safely via `AnalyticsCaptureConfig.from_dict({})`)
- `.ll/ll-config.json` — `scratch_pad` and `documents` blocks show the same `enabled` boolean shape
- `scripts/little_loops/config/features.py:feature_enabled()` — the dot-path lookup that gates all analytics writes; traverses `_raw_config` at runtime, so a missing top-level key returns `False` immediately without any error

### Tests
- Manual: invoke `/ll:ready-issue` and verify a `skill_events` row appears in `.ll/history.db`
- `scripts/tests/test_config.py:TestBRConfigAnalyticsCaptureIntegration` — existing tests for analytics config round-trip; `test_analytics_capture_loads_from_config` loads a config with `analytics.enabled: true` and asserts properties; run to confirm no regression after adding the block
- `scripts/tests/test_config_schema.py` — `test_analytics_in_schema` and `test_analytics_capture_in_schema` assert the schema block exists with `enabled: boolean, default: false` and `additionalProperties: false`; these pass without schema changes needed

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hook_user_prompt_submit.py` — exercises the skip-when-disabled path (`test_skips_write_when_analytics_disabled`, `test_skill_write_skipped_when_analytics_disabled`); all tests use `tmp_path` not the real config, so they are unaffected by ENH-1883 but should be run to verify no regression in the disabled path
- `scripts/tests/test_hook_post_tool_use.py` — exercises the file_events skip path (`test_skips_write_when_analytics_disabled`, `test_no_file_event_when_analytics_disabled`); same tmp_path isolation, run as regression check

### Documentation
- N/A — config-only change; no public API or user-facing documentation updated

### Configuration
- `.ll/ll-config.json` — project config
- `config-schema.json` — JSON Schema for config validation

## Implementation Steps

1. **Schema is already present — verify only**: `config-schema.json` lines 1340–1380 already define the `analytics` block with `enabled`, `capture.skills`, `capture.cli_commands`, `capture.corrections`, and `capture.file_events` (added by FEAT-1623/ENH-1840). Run `python -m pytest scripts/tests/test_config_schema.py -v -k analytics` to confirm; no schema edits needed.
2. Add the `analytics` block to `.ll/ll-config.json`. Minimal form mirrors the `context_monitor` block pattern already in the file:
   ```json
   "analytics": {
     "enabled": true,
     "capture": {
       "skills": ["*"],
       "cli_commands": ["*"],
       "corrections": true,
       "file_events": true
     }
   }
   ```
3. Restart Claude Code session to reload config (config is parsed at session start by `BRConfig._parse_config()` in `scripts/little_loops/config/core.py`).
4. Invoke a skill (e.g. `/ll:ready-issue`) and verify `skill_events` is populated:
   ```bash
   python3 -c "import sqlite3; c=sqlite3.connect('.ll/history.db'); print(c.execute('SELECT COUNT(*) FROM skill_events').fetchone())"
   ```
5. Run existing config round-trip tests to confirm no regression:
   ```bash
   python -m pytest scripts/tests/test_config.py::TestBRConfigAnalyticsCaptureIntegration -v
   ```

## Impact

- **Priority**: P3 — activation gap; all infrastructure exists, this is a config flip
- **Effort**: Small — one JSON block addition + schema check
- **Risk**: Low — opt-in flag; enabling it adds write overhead per tool call / prompt submit (negligible)
- **Breaking Change**: No

## Labels

`enhancement`, `history-db`, `analytics`, `config`, `captured`

## Status

**Open** | Created: 2026-06-02 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-03T01:00:59 - `b773ed04-caa9-4596-b890-7f5a3b05df36.jsonl`
- `/ll:confidence-check` - 2026-06-03T01:15:00 - `1d8b477f-7177-4004-aa45-8b1f23e2f734.jsonl`
- `/ll:wire-issue` - 2026-06-03T00:57:15 - `1eb8b671-ed02-4a28-83a1-4f28267a8a04.jsonl`
- `/ll:refine-issue` - 2026-06-03T00:53:05 - `b4f4a9be-21e8-47c5-813d-d39d0e05f9ec.jsonl`
- `/ll:format-issue` - 2026-06-02T23:43:15 - `6762fecb-c5c5-457f-a753-c7014e582f14.jsonl`

- `/ll:capture-issue` - 2026-06-02T23:39:38Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/65f77860-d771-4c40-9ba9-2bc9f9139bfe.jsonl`
