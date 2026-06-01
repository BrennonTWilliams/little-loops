---
id: ENH-1835
type: ENH
priority: P3
status: done
discovered_date: 2026-06-01
captured_at: '2026-06-01T01:10:54Z'
discovered_by: capture-issue
relates_to:
- ENH-1833
- ENH-1834
- ENH-1831
labels:
- enhancement
- captured
parent: EPIC-1707
confidence_score: 95
outcome_confidence: 69
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
size: Very Large
---

# ENH-1835: Make tracked skills and CLI commands configurable in ll-config.json

## Summary

Once skill invocations (ENH-1833), CLI invocations (ENH-1834), and user corrections
(ENH-1831) are being captured in `history.db`, users should be able to control
which events are tracked via `ll-config.json`. The config schema (`config-schema.json`
in the repo root) should be updated to reflect these options.

## Current Behavior

All capture write paths (skill invocations, CLI commands, user corrections, file events)
write unconditionally to `history.db` regardless of project needs. There is no mechanism
to exclude specific skill names, CLI binaries, or capture categories at the project level.

## Expected Behavior

`ll-config.json` has an `analytics.capture` configuration block that the write paths
consult before recording any event. Projects can allowlist/blocklist specific skill names
and CLI binaries via glob patterns, and toggle correction/file-event capture on or off.
`ll-doctor` surfaces the current capture config state for quick diagnostics.

## Motivation

Not all projects need full capture. A project-level allowlist/blocklist for tracked
skill names, CLI binaries, and correction heuristics prevents unwanted data collection
and keeps the DB from growing unbounded on high-volume projects.

## Scope Boundaries

- **In scope**: New `analytics.capture` block in `config-schema.json`; `feature_enabled_for()` helper in `config_loader.py`; threading the config check into ENH-1831–1834 write paths; `ll-doctor` reporting; `docs/reference/CONFIGURATION.md` update
- **Out of scope**: Retroactive pruning of already-captured data based on new config; per-session config overrides (project-level only); interactive CLI for config editing; UI for managing capture settings

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 (schema)**: Add `capture` sub-object inside the existing `"analytics"` property in `config-schema.json` (currently at lines 1272–1283, `additionalProperties: false` must be preserved on the outer object and added to the new inner object). Pattern follows `events.sqlite` sub-object structure.
- **Step 2 (helper)**: Target file is `scripts/little_loops/config/features.py` (not `config_loader.py`). `feature_enabled()` lives there (lines 13–34). Add `feature_enabled_for(config_data, dot_path, subject, default=True)` next to it using `fnmatch.fnmatch` — follow the pattern in `scripts/little_loops/events.py::EventBus.emit()` which does `any(fnmatch.fnmatch(subject, p) for p in patterns)`. Also add `AnalyticsCaptureConfig` dataclass following `LearningTestsConfig.from_dict()` pattern, and wire into `BRConfig._parse_config()` in `config/core.py`.
- **Step 3 (threading)**: Two live write-path hooks to update: `hooks/post_tool_use.py::handle()` (add `analytics.capture.file_events` gate after existing `analytics.enabled` check; `write_file_event()` already has forward-compat `config` param) and `hooks/user_prompt_submit.py::handle()` (add `analytics.capture.corrections` gate before `record_correction()` call). The `analytics.capture.skills` and `analytics.capture.cli_commands` gates cannot be wired until ENH-1833 and ENH-1834 (skill/CLI event tables) are implemented — wire those write paths when their tables exist.
- **Step 4 (doctor)**: `cli/doctor.py::main_doctor()` currently does NOT read analytics config; it only calls `runner.describe_capabilities()`. Add a new reporting block that loads raw config (using the existing `_load_config` pattern from hooks) and prints `analytics.capture.*` state using the existing `_STATUS_SYMBOLS` dict.
- **Backfill path**: `hooks/session_start.py::_run_backfill()` writes `tool_events`/`message_events`/`sessions` but is NOT gated on `analytics.enabled` — out of scope for this issue but document in the doc update.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Implement gating inside `session_store.py::write_file_event()` and `record_correction()` using the `config` param — the hooks pass config in but the functions currently ignore it; add the `feature_enabled_for` / `feature_enabled` checks inside these functions (not only at the hook call site) so gating also works if they are called outside the hook context
7. Update `scripts/little_loops/cli/ctx_stats.py::main_ctx_stats()` error strings (~lines 220, 286) to mention `analytics.capture.file_events` as a second reason data may be absent (alongside `analytics.enabled`)
8. Update `docs/reference/CLI.md` `### ll-doctor` section to reflect the expanded `ll-doctor` output
9. Update test helpers `_write_config()` in `test_hook_post_tool_use.py` and `test_hook_user_prompt_submit.py` to accept `analytics_capture` dict; add gating tests for the new sub-keys
10. Write `TestFeatureEnabledForHelper`, `TestAnalyticsCaptureConfig`, `TestBRConfigAnalyticsCaptureIntegration` in `test_config.py` (the referenced `test_config_loader.py` does not exist — put tests there instead)
11. Add `test_analytics_capture_in_schema` to `test_config_schema.py` to guard the new `capture` sub-object inside `analytics`
12. Add `TestMainDoctor` coverage for capture-state reporting in `test_cli_doctor.py` with a properly configured BRConfig mock

## Integration Map

### Files to Modify
- `config-schema.json` — new `analytics.capture` block
- `scripts/little_loops/config/features.py` — `feature_enabled_for()` helper (extend existing `feature_enabled()` at lines 13–34 to support glob matching via `fnmatch`)
- `scripts/little_loops/config/core.py` — `BRConfig._parse_config()` to wire in new `AnalyticsCaptureConfig` field and `@property`
- `scripts/little_loops/config/__init__.py` — re-export `AnalyticsCaptureConfig`
- Capture write-path files from ENH-1831, ENH-1832, ENH-1833, ENH-1834
- `scripts/little_loops/cli/doctor.py` — capture config reporting
- `docs/reference/CONFIGURATION.md` — new keys documentation

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/post_tool_use.py::handle()` — gates on `feature_enabled(config, "analytics.enabled")`; calls `write_file_event()` (which already has a `config: dict | None = None` forward-compat param per ENH-1835 note in its docstring); needs `analytics.capture.file_events` gate added after existing gate
- `scripts/little_loops/hooks/user_prompt_submit.py::handle()` — gates on `feature_enabled(config, "analytics.enabled")` then calls `record_correction()`; needs `analytics.capture.corrections` gate added
- `scripts/little_loops/hooks/session_start.py::_run_backfill()` — daemon thread writes `tool_events`/`message_events`/`sessions`; currently NOT gated on `analytics.enabled` at all; backfill gating is out of scope for ENH-1835 but worth documenting
- `scripts/little_loops/config/core.py::BRConfig._parse_config()` — needs new `_analytics_capture` field wired in (following the `LearningTestsConfig` pattern)
- `scripts/little_loops/config/__init__.py` — package re-exports; new `AnalyticsCaptureConfig` dataclass must be added here

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store.py` — direct home of `write_file_event()` and `record_correction()`; both functions already have `config: dict | None = None` forward-compat params; the actual gating logic inside these functions (using the `config` param) must be implemented here as part of Step 3, not only in the hook call sites
- `scripts/little_loops/transport.py` — TYPE_CHECKING import of `EventsConfig` from `config.features`; no change needed but file touches `config/__init__.py` exports and should be verified post-refactor
- `scripts/little_loops/cli/ctx_stats.py::main_ctx_stats()` — user-facing error strings at lines ~220 and ~286 read `"set analytics.enabled: true in .ll/ll-config.json"`; once `analytics.capture.file_events` is a separate gate, these strings will mislead users who have `analytics.enabled: true` but `capture.file_events: false` — update the message to mention both gates

### Similar Patterns
- `scripts/little_loops/config/features.py::feature_enabled()` — existing dot-path helper (lines 13–34); no `feature_enabled_for()` exists yet — add it here using `fnmatch.fnmatch`
- `scripts/little_loops/events.py::EventBus.emit()` — the only `fnmatch` usage in the codebase; pattern: `any(fnmatch.fnmatch(subject, p) for p in patterns)` with `str | list[str] | None` normalization
- `scripts/little_loops/config/features.py::LearningTestsConfig.from_dict()` — pattern for new `AnalyticsCaptureConfig` dataclass (`@dataclass` + `from_dict(cls, data)` classmethod with `.get()` defaults)
- `scripts/little_loops/config/core.py::BRConfig._parse_config()` — wiring pattern for new section: one `from_dict` call + one `@property`, using `self._raw_config.get("analytics", {}).get("capture", {})`
- `scripts/tests/test_hook_post_tool_use.py::_write_config()` — the hook test helper pattern to extend for `analytics.capture.*` gating tests (also `test_hook_user_prompt_submit.py`)
- `scripts/tests/test_config_schema.py::TestConfigSchema.test_analytics_in_schema` — regression guard pattern to extend for the new `capture` sub-block
- Note: `ll-doctor::main_doctor()` does NOT currently report any config feature flags — a new section must be added that reads raw config directly (the existing path delegates to `runner.describe_capabilities()` only)

### Tests
- `scripts/tests/test_config_loader.py` — NOTE: this file does not exist; tests belong in `scripts/tests/test_config.py` instead (see wiring note below)
- Tests for each write-path: verify skip behavior when feature is disabled

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py` — add three new test classes following the `TestLearningTestsConfig` / `TestBRConfigLearningTestsIntegration` pattern:
  - `TestFeatureEnabledForHelper` — unit tests for the new `feature_enabled_for()` glob-matching function: wildcard `["*"]` matches any subject, exact match `["Read"]` matches only `"Read"`, list of patterns, empty list returns default, absent key returns `default=True`
  - `TestAnalyticsCaptureConfig` — unit tests for new `AnalyticsCaptureConfig.from_dict()`: defaults when absent, skills/cli_commands override, corrections/file_events false
  - `TestBRConfigAnalyticsCaptureIntegration` — BRConfig property tests: defaults when absent, override from config file, round-trip via `to_dict()`
- `scripts/tests/test_hook_post_tool_use.py` — update `_write_config()` helper to accept `analytics_capture: dict | None = None` kwarg; add test methods to `TestFileEventsWrite` covering the `analytics.capture.file_events: false` gate (analytics enabled at top level but file_events disabled)
- `scripts/tests/test_hook_user_prompt_submit.py` — same pattern: extend `_write_config()` helper, add test for `analytics.capture.corrections: false` gate
- `scripts/tests/test_config_schema.py` — add `test_analytics_capture_in_schema` method in `TestConfigSchema` to assert the new `capture` sub-object is declared inside `analytics.properties` (existing `test_analytics_in_schema` only checks `enabled` — the `additionalProperties: false` guard on `analytics` makes a missing `capture` a silent schema bug)
- `scripts/tests/test_cli_doctor.py` — add test methods to `TestMainDoctor` covering the new analytics capture-state reporting block; configure mock `BRConfig` to return a suitable `analytics_capture` value (bare `MagicMock()` will silently pass the new block but not assert correct output)

### Documentation
- `docs/reference/CONFIGURATION.md` — new `analytics.capture` keys section

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `### ll-doctor` section (~lines 115–143) describes `ll-doctor` output format; update when `main_doctor()` gains the new "Capture Config" section
- `docs/reference/API.md` — `main_ctx_stats` docstring at ~line 3496 reads `"Enable per-tool byte tracking by setting \"analytics\": {\"enabled\": true}"` — supplement to mention `analytics.capture` as the per-category control alongside the master switch
- `docs/reference/HOST_COMPATIBILITY.md` — ~line 214 states `ll-doctor` "prints a `CapabilityReport`"; add note that it also reports config-state when `analytics.capture` is configured

### Configuration
- `config-schema.json` — primary artifact of this issue

## Depends On

- ENH-1831, ENH-1832, ENH-1833, ENH-1834 (the write paths this configures)

## Impact

- **Priority**: P3 — Nice-to-have control layer; useful on high-volume projects but ENH-1831–1834 are functional without it
- **Effort**: Medium — New config block, glob-matching helper, and threading the check through 4+ write paths; straightforward pattern but touches several files
- **Risk**: Low — Purely additive config with safe defaults (`"*"` / `true`); no behavior change unless user opts in

## Status

**Open** | Created: 2026-06-01 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-01_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 69/100 → MODERATE

### Outcome Risk Factors
- **High site count (breadth 0/12)** — 18 distinct files touched across source, test, and documentation layers; per-site changes are mechanical or local, but the enumeration sweep is wide and a missed site will go unnoticed. Work through the integration map top-to-bottom and do a final verification grep after each group (config → write paths → doctor → tests → docs).
- **Skills/CLI capture gates deferred** — ENH-1833 and ENH-1834 are still open; `analytics.capture.skills` and `analytics.capture.cli_commands` config keys and `AnalyticsCaptureConfig` fields should be fully defined now so the wire-in is a single-pass diff when those issues close. Place explicit `# TODO(ENH-1835): wire when ENH-1833/ENH-1834 land` markers at the call sites.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-06-01
- **Reason**: Issue too large for single session

### Decomposed Into
- ENH-1840: Analytics capture config layer — schema, helper, and dataclass
- ENH-1841: Analytics capture write-path gating
- ENH-1842: Analytics capture surface layer — ll-doctor reporting and documentation

## Session Log
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c1325861-5c8a-40ab-90ee-ac4727f376b5.jsonl`
- `/ll:confidence-check` - 2026-06-01T07:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e04b82c5-934a-429c-97f3-c8f3204410f7.jsonl`
- `/ll:wire-issue` - 2026-06-01T06:01:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e6056b8-0c65-47b1-98fe-5221eaca62e7.jsonl`
- `/ll:refine-issue` - 2026-06-01T05:55:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1d5eaf95-ffe3-48a2-8e4c-da2b559177cc.jsonl`
- `/ll:format-issue` - 2026-06-01T01:23:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a513f1d-2fed-4b43-8002-f50ed0ac51fd.jsonl`
- `/ll:capture-issue` - 2026-06-01T01:10:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
