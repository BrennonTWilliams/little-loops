---
id: ENH-1842
type: ENH
priority: P3
status: done
discovered_date: 2026-06-01
completed_at: 2026-06-01 07:15:09+00:00
parent: ENH-1835
relates_to:
- ENH-1835
- ENH-1840
labels:
- enhancement
size: Small
decision_needed: false
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 (tests) — `TestMainDoctor` already exists:**
- `scripts/tests/test_cli_doctor.py` exists with `TestMainDoctor` (12 methods) — no need to create the file
- Mock pattern to use: `mock_config = MagicMock(); patch("little_loops.config.BRConfig", return_value=mock_config)` — set attributes directly on the mock (e.g. `mock_config.analytics_capture.corrections = True`, `mock_config.analytics_capture.file_events = False`)
- Output assertion pattern: `_capture_print()` helper at line 29 returns `(lines, side_effect)`; pass as `patch("builtins.print", side_effect=side_effect)`; assert on `"\n".join(lines)`
- `analytics.enabled` is not a typed `BRConfig` property — it is in `_raw_config`; for doctor display, use only the `analytics_capture` sub-object fields; do not try to read `config.analytics_enabled`

**Step 2 (doctor.py) — BRConfig binding:**
- Current line ~102: `apply_host_cli_from_config(BRConfig(Path.cwd()))` — BRConfig instance is discarded; change to `cfg = BRConfig(Path.cwd()); apply_host_cli_from_config(cfg)`, then read `cfg.analytics_capture` for the new section
- `_STATUS_SYMBOLS` (line 12) has no boolean keys; use: `_STATUS_SYMBOLS["full" if value else "unsupported"]` for each field; for list fields (`skills`, `cli_commands`), display the list items alongside the symbol

**Step 3 (ctx_stats.py) — exact error string locations:**
- Line 219–221, inside `_render_fallback()`: `"set analytics.enabled: true in .ll/ll-config.json"`
- Lines 285–288, inside `main_ctx_stats()` zero-row branch: `"set analytics.enabled: true in .ll/ll-config.json and run a few tool calls"`

**Step 4–7 (docs) — section targets confirmed:**
- `CONFIGURATION.md:429` — `analytics.enabled` entry; append `capture` sub-object table beneath it
- `CLI.md:115` — `### ll-doctor` section including example output block (lines 115–144)
- `API.md:3496` — single `"Enable per-tool byte tracking by setting…"` note line in `main_ctx_stats` docstring
- `HOST_COMPATIBILITY.md:214` — `ll-doctor` description sentence containing `"prints a CapabilityReport"`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `docs/codex/README.md` (~line 42) — expand the one-line `ll-doctor` description to mention it also reports analytics config-state when `analytics.capture` is configured
9. Review `hooks/adapters/opencode/README.md` and `hooks/adapters/codex/README.md` — decide whether the `analytics.enabled`-only guard description should be supplemented with `analytics.capture.file_events` (lower-priority; in-scope only if the doc pass covers adapter READMEs)
10. When implementing test step (step 1), confirm `test_cli_ctx_stats.py` coverage is not broken; the `_render_fallback` and `main_ctx_stats` error strings are emitted via `logger`, not `print`, so the `_capture_print()` helper won't capture them — no test assertions on those strings exist, so ctx_stats changes are safe

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

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/doctor.py` — Bind the discarded `BRConfig(Path.cwd())` return value (line ~102) to a variable; read `.analytics_capture` property; print new section after `_print_report()` call
- `scripts/little_loops/cli/ctx_stats.py` — Update two error strings: line 220 (in `_render_fallback()`) and line 286 (in `main_ctx_stats()` zero-row-count branch)

### Config Layer (landed in ENH-1840)
- `scripts/little_loops/config/features.py:404` — `AnalyticsCaptureConfig` dataclass with `skills: list[str]`, `cli_commands: list[str]`, `corrections: bool`, `file_events: bool`
- `scripts/little_loops/config/core.py:306` — `BRConfig.analytics_capture` property returning `AnalyticsCaptureConfig`

### `_STATUS_SYMBOLS` gap in `doctor.py:12`
- Dict currently has no `"enabled"`/`"disabled"` keys — map booleans to existing `"full"` (`✓`) and `"unsupported"` (`✗`): `_STATUS_SYMBOLS["full" if enabled else "unsupported"]`

### Tests
- `scripts/tests/test_cli_doctor.py` — `TestMainDoctor` class (12 existing methods); use `_capture_print()` helper (line 29) and `patch("little_loops.config.BRConfig", return_value=mock_config)` where `mock_config = MagicMock()` with attributes set explicitly (see `test_cli_sync.py:28-44` for attribute-setup mock pattern)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_ctx_stats.py` — existing coverage for `_render_fallback()` and `main_ctx_stats()`; error strings use `logger` (not `print`), so ctx_stats changes won't break these tests — but this file should be checked when adding ctx_stats coverage [Agent 3 finding]
- `scripts/tests/test_feat1504_doc_wiring.py` — structural test asserts `ll-doctor` string present in `HOST_COMPATIBILITY.md` and `help.md`; the planned HOST_COMPATIBILITY.md addition must not remove the `"ll-doctor"` anchor [Agent 2 finding]
- `scripts/tests/test_feat1625_doc_wiring.py` — structural test asserts `ll-ctx-stats` appears in `CLI.md`, `help.md`, `CLAUDE.md`, `skills/configure/areas.md`, `skills/init/SKILL.md`; doc changes must preserve those anchor strings [Agent 2 finding]

### Documentation
- `docs/reference/CONFIGURATION.md:429` — `analytics` section; append `analytics.capture.*` table after existing `analytics.enabled` entry
- `docs/reference/CLI.md:115` — `### ll-doctor` example output block (~lines 115–143); add "Analytics Capture" section to sample
- `docs/reference/API.md:3496` — `main_ctx_stats` note string; supplement with `analytics.capture` mention
- `docs/reference/HOST_COMPATIBILITY.md:214` — `ll-doctor` `CapabilityReport` description; add note about config-state reporting

_Wiring pass added by `/ll:wire-issue`:_
- `docs/codex/README.md:42` — describes `ll-doctor` purpose as "capabilities and hook intents" only; add note that it also reports analytics config-state when `analytics.capture` is configured [Agent 2 finding]
- `hooks/adapters/opencode/README.md` — lines 42, 51, 118 reference `analytics.enabled` as the sole guard for SQLite writes; consider adding a note that `analytics.capture.file_events` is a second gate [Agent 2 finding]
- `hooks/adapters/codex/README.md:83` — same `analytics.enabled`-only pattern as opencode README [Agent 2 finding]

## Resolution

Implemented all steps:
- Added `_print_capture_section()` to `doctor.py` and bound the `BRConfig` return value so `cfg.analytics_capture` is readable
- Fixed two error strings in `ctx_stats.py` to mention `analytics.capture.file_events`
- Added `analytics.capture.*` table to `CONFIGURATION.md` with examples
- Updated `CLI.md` ll-doctor example output to include the new Analytics Capture section
- Updated `API.md` main_ctx_stats note with `analytics.capture` reference
- Updated `HOST_COMPATIBILITY.md` ll-doctor description with config-state reporting note
- Updated `docs/codex/README.md` ll-doctor description
- Added two new `TestMainDoctor` tests (all_enabled, file_events_disabled); all 8554 tests pass

## Session Log
- `/ll:manage-issue` - 2026-06-01T07:15:09Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53293d84-c2d0-44c2-bd40-9387a21b4f56.jsonl`
- `/ll:ready-issue` - 2026-06-01T07:07:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f496ef9f-9121-4abd-a242-6dad047d86c2.jsonl`
- `/ll:wire-issue` - 2026-06-01T07:03:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5dcfb3ab-ceb2-47de-9a9b-ae04e00f6492.jsonl`
- `/ll:refine-issue` - 2026-06-01T06:57:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9851cae-ee57-46f2-9816-321c3b81e6ee.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c1325861-5c8a-40ab-90ee-ac4727f376b5.jsonl`
- `/ll:confidence-check` - 2026-06-01T08:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c9e9161-3ff2-499f-87e7-06318cd1ec80.jsonl`
