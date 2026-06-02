---
id: ENH-1840
type: ENH
priority: P3
status: done
discovered_date: 2026-06-01
completed_at: 2026-06-01 06:29:38+00:00
parent: ENH-1835
relates_to:
- ENH-1835
- ENH-1831
- ENH-1832
- ENH-1833
- ENH-1834
labels:
- enhancement
size: Small
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1840: Analytics capture config layer — schema, helper, and dataclass

## Summary

Add the `analytics.capture` block to `config-schema.json`, implement the
`feature_enabled_for()` glob-matching helper and `AnalyticsCaptureConfig` dataclass
in `config/features.py`, wire the new config section into `BRConfig._parse_config()`,
and add full unit/schema test coverage. This is the foundational config layer that
ENH-1841 (write-path gating) and ENH-1842 (surface/docs) depend on.

## Current Behavior

The `analytics.capture` configuration block does not exist in `config-schema.json`. The `scripts/little_loops/config/features.py` module provides only a boolean `feature_enabled()` helper; there is no `feature_enabled_for()` function supporting glob pattern matching against a subject string, and no `AnalyticsCaptureConfig` dataclass. The `BRConfig` class in `config/core.py` exposes no `analytics_capture` property.

## Expected Behavior

`config-schema.json` declares and validates an `analytics.capture` sub-object with `skills`, `cli_commands`, `corrections`, and `file_events` fields (all with safe defaults). `feature_enabled_for(config_data, dot_path, subject)` resolves the value at `dot_path` and applies `fnmatch` glob matching against the subject. `AnalyticsCaptureConfig.from_dict({})` returns all-default values. `BRConfig.analytics_capture` provides typed access to the config block. Unit and schema tests cover all new code.

## Scope Boundaries

In scope: schema declaration, `AnalyticsCaptureConfig` dataclass, `feature_enabled_for()` helper, `BRConfig` property wiring, and tests.
Out of scope: applying `feature_enabled_for()` in hooks (ENH-1841), exposing the config in `ll-doctor` or updating user-facing docs (ENH-1842), any write-path gating logic.

## Parent Issue

Decomposed from ENH-1835: Make tracked skills and CLI commands configurable in ll-config.json

## Implementation Steps

1. **`config-schema.json`** — Add `capture` sub-object inside the existing `"analytics"` property
   (currently at lines 1272–1283). Follow the `events.sqlite` sub-object structure. Must preserve
   `additionalProperties: false` on both the outer `analytics` object and the new `capture` object.
   The new block should expose:
   - `skills`: array of strings (default `["*"]`)
   - `cli_commands`: array of strings (default `["*"]`)
   - `corrections`: boolean (default `true`)
   - `file_events`: boolean (default `true`)

2. **`scripts/little_loops/config/features.py`** — Add next to existing `feature_enabled()` (lines 13–34):
   - `AnalyticsCaptureConfig` dataclass with `from_dict()` classmethod following
     `LearningTestsConfig.from_dict()` pattern; fields: `skills: list[str]`, `cli_commands: list[str]`,
     `corrections: bool`, `file_events: bool` with defaults matching schema
   - `feature_enabled_for(config_data, dot_path, subject, default=True)` function using
     `fnmatch.fnmatch` — follow `EventBus.emit()` pattern from `scripts/little_loops/events.py`:
     `any(fnmatch.fnmatch(subject, p) for p in patterns)` with `str | list[str] | None` normalization.
     The normalization logic is in `EventBus.register()` (lines 81–96 of `events.py`): a bare `str`
     is wrapped in `[str]`, a `list` is used as-is, `None` means "match all". Apply the same
     before calling `fnmatch`.

3. **`scripts/little_loops/config/core.py`** — In `BRConfig._parse_config()`, wire in new field:
   ```python
   self._analytics_capture = AnalyticsCaptureConfig.from_dict(
       self._raw_config.get("analytics", {}).get("capture", {})
   )
   ```
   Add `@property analytics_capture` returning `self._analytics_capture`.
   Also update `to_dict()` (lines 484–665): add an `"analytics"` key (or extend it if
   `enabled` is already serialized there) with `"capture": {...}` so the round-trip
   integration test in step 5c passes. Model after how `learning_tests` is serialized
   there (each sub-config contributes its own nested dict key).

4. **`scripts/little_loops/config/__init__.py`** — Re-export `AnalyticsCaptureConfig`: add the import and also add `"AnalyticsCaptureConfig"` to the `__all__` list (every dataclass exported here is listed in `__all__` explicitly — omitting it would make the export inconsistent).

### Tests (TDD — write tests first)

5. **`scripts/tests/test_config.py`** — Add three new test classes:
   - `TestFeatureEnabledForHelper`: wildcard `["*"]` matches any subject; exact `["Read"]` matches
     only `"Read"`; list of patterns; empty list returns `default=True`; absent key returns `default=True`
   - `TestAnalyticsCaptureConfig`: defaults when absent; skills/cli_commands override; `corrections`/
     `file_events` false
   - `TestBRConfigAnalyticsCaptureIntegration`: defaults when absent; override from config; `to_dict()`
     round-trip

6. **`scripts/tests/test_config_schema.py`** — Add `test_analytics_capture_in_schema` to `TestConfigSchema`
   asserting the new `capture` sub-object is declared inside `analytics.properties` (guards against
   `additionalProperties: false` silently rejecting the new key).

## Acceptance Criteria

- `config-schema.json` accepts `analytics.capture.{skills,cli_commands,corrections,file_events}`
- `feature_enabled_for(config_data, "analytics.capture.skills", "my-skill")` returns correct bool
- `AnalyticsCaptureConfig.from_dict({})` returns all-default values
- `BRConfig.analytics_capture` property is accessible
- All new test classes pass

## Files to Modify

- `config-schema.json`
- `scripts/little_loops/config/features.py`
- `scripts/little_loops/config/core.py`
- `scripts/little_loops/config/__init__.py`
- `scripts/tests/test_config.py`
- `scripts/tests/test_config_schema.py`

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Similar Patterns to Follow
- `scripts/little_loops/config/features.py:344–359` — `LearningTestsConfig.from_dict()` is the exact template for `AnalyticsCaptureConfig`: typed fields with explicit defaults, `data.get(key, default)` in `from_dict()`
- `scripts/little_loops/config/features.py:13–34` — `feature_enabled()` is the direct counterpart to `feature_enabled_for()`; walk `dot_path` the same way, then apply fnmatch instead of `bool()`
- `scripts/little_loops/events.py:81–96` — `EventBus.register()` contains the `str | list[str] | None → list[str]` normalization to replicate before calling `fnmatch`
- `scripts/little_loops/events.py:117–138` — `EventBus.emit()` shows the `any(fnmatch.fnmatch(subject, p) for p in patterns)` expression

#### Consumers (callers in ENH-1841 — read-only context for ENH-1840)
- `scripts/little_loops/hooks/post_tool_use.py:25` — calls `feature_enabled(config, "analytics.enabled")` on a raw dict; ENH-1841 will add `feature_enabled_for()` calls here
- `scripts/little_loops/hooks/user_prompt_submit.py:26,69` — same pattern; will call `feature_enabled_for()` in ENH-1841
- Note: hooks load config via `_load_config()` → raw `dict`, NOT `BRConfig`; `feature_enabled_for()` must therefore operate on a raw dict (same signature as `feature_enabled()`)

#### Test Patterns to Model After
- `scripts/tests/test_config.py:1061` — `TestFeatureEnabledHelper` class: shape for `TestFeatureEnabledForHelper`
- `scripts/tests/test_config.py:1588` — `TestBRConfigEventsIntegration`: shape for `TestBRConfigAnalyticsCaptureIntegration` (uses `temp_project_dir` fixture, writes minimal JSON config, calls `to_dict()` for round-trip)
- `scripts/tests/test_config_schema.py:184–203` — `test_analytics_in_schema`: existing neighbor test; `test_analytics_capture_in_schema` goes in the same class right after it
- `scripts/tests/test_config_schema.py:226–288` — `test_events_in_schema`: shows how to assert a nested sub-object with its own `additionalProperties: false`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/post_tool_use.py` — imports `feature_enabled` from `config.features` directly (line 25); ENH-1841 will add a `feature_enabled_for` import alongside it. No changes needed for ENH-1840, but run its tests as a don't-break check.
- `scripts/little_loops/hooks/user_prompt_submit.py` — same direct import pattern (line 26); same ENH-1841 scope note.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hook_post_tool_use.py` — exercises the `feature_enabled(config, "analytics.enabled")` gate via `_write_config()`; won't break due to ENH-1840 (writes only `analytics.enabled`, which stays valid), but run as a regression check
- `scripts/tests/test_hook_user_prompt_submit.py` — same pattern; same don't-break note

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `BRConfig` properties table (around line 100–121) needs a new row for `analytics_capture: AnalyticsCaptureConfig`; this is NOT assigned to ENH-1842 (ENH-1842 step 6 covers only `main_ctx_stats` docstring) — it is an undocumented gap that should be resolved either here or in ENH-1842

## Depends On

- None (this is the foundation layer)

## Blocks

- ENH-1841 (write-path gating needs `feature_enabled_for` and `AnalyticsCaptureConfig`)
- ENH-1842 (doctor reporting needs `BRConfig.analytics_capture` property)

## Impact

- **Priority**: P3
- **Effort**: Small — focused config/dataclass work on ~6 files
- **Risk**: Low — purely additive; safe defaults mean no behavior change unless user opts in

## Resolution

Implemented the `analytics.capture` config layer in full:
- `config-schema.json`: added `capture` sub-object to `analytics` with `skills`, `cli_commands`, `corrections`, `file_events` fields and `additionalProperties: false`
- `features.py`: added `fnmatch`-based `feature_enabled_for()` helper and `AnalyticsCaptureConfig` dataclass
- `core.py`: wired `_analytics_capture` in `_parse_config()`, added `analytics_capture` property, extended `to_dict()` with `analytics.capture` block
- `config/__init__.py`: re-exported `AnalyticsCaptureConfig` and added to `__all__`
- Tests: 19 new tests across `TestFeatureEnabledForHelper`, `TestAnalyticsCaptureConfig`, `TestBRConfigAnalyticsCaptureIntegration`, and `test_analytics_capture_in_schema` — all pass

## Session Log
- `/ll:manage-issue` - 2026-06-01T06:29:38Z - `ab5b7063-586d-4d46-98ff-508f939fa8aa.jsonl`
- `/ll:ready-issue` - 2026-06-01T06:25:40 - `ab5b7063-586d-4d46-98ff-508f939fa8aa.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `57be6e9a-e5c2-439b-80e5-04c349b4c87e.jsonl`
- `/ll:wire-issue` - 2026-06-01T06:18:09 - `95cadb0b-6da8-4f6b-a689-d21bc63f3ce9.jsonl`
- `/ll:refine-issue` - 2026-06-01T06:12:54 - `21d238a3-9b92-4861-a16b-538adf0c392b.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `c1325861-5c8a-40ab-90ee-ac4727f376b5.jsonl`
