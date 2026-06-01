---
id: ENH-1843
title: 'Auto-commit config layer: auto_commit and auto_commit_prefix feature flags'
type: ENH
priority: P3
status: done
parent: ENH-1717
confidence_score: 100
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-06-01 08:27:16+00:00
---

# ENH-1843: Auto-commit config layer: auto_commit and auto_commit_prefix feature flags

## Summary

Add `auto_commit` (bool, default `false`) and `auto_commit_prefix` (string, default `"chore(issues)"`) to the issues config layer: JSON schema, `IssuesConfig` dataclass, and `BRConfig.to_dict()` serialization.

## Current Behavior

The `issues` config layer (`config-schema.json`, `IssuesConfig` dataclass, `BRConfig.to_dict()`) has no `auto_commit` or `auto_commit_prefix` fields. Any hook that wants to gate on these flags must hard-code defaults or read raw dict keys directly — neither is accessible via `{{config.issues.auto_commit}}` template variable resolution.

## Expected Behavior

`config.issues.auto_commit` (default `false`) and `config.issues.auto_commit_prefix` (default `"chore(issues)"`) are recognized by the JSON schema, parsed into `IssuesConfig`, and serialized by `BRConfig.to_dict()`, making them available as template variables and via the config object.

## Parent Issue

Decomposed from ENH-1717: Auto-commit hooks on Issue file CRUD operations

## Proposed Solution

### config-schema.json

Add inside `issues.properties` (which already has `additionalProperties: false`):

```json
"auto_commit": { "type": "boolean", "default": false },
"auto_commit_prefix": { "type": "string", "default": "chore(issues)" }
```

### scripts/little_loops/config/features.py

Add to `IssuesConfig` dataclass:

```python
auto_commit: bool = False
auto_commit_prefix: str = "chore(issues)"
```

And to `IssuesConfig.from_dict()` — follow the `LearningTestsConfig.from_dict()` pattern at line 394.

### scripts/little_loops/config/core.py

Extend `BRConfig.to_dict()` to include `auto_commit` and `auto_commit_prefix` in the `issues` sub-dict so template variable resolution (`{{config.issues.auto_commit}}`) works correctly.

## Integration Map

### Files to Modify
- `config-schema.json` — `issues.properties` block; insert before `"additionalProperties": false` at line 241 (all new fields must be declared here or schema rejects them)
- `scripts/little_loops/config/features.py` — `IssuesConfig` dataclass: append after `next_issue` field (line 203); `IssuesConfig.from_dict()`: append to `cls(...)` kwargs after `next_issue=` line (line 238)
- `scripts/little_loops/config/core.py` — `BRConfig.to_dict()` `"issues"` sub-dict: insert after `"capture_template"` key (line 518, before closing `},`)

### Closest Recent Analog
- `scripts/little_loops/config/features.py:403` — `AnalyticsCaptureConfig` (ENH-1840): mixed `bool`/non-bool flat `from_dict()` — the most direct structural analog
- `scripts/little_loops/config/core.py:596` — `analytics` block in `BRConfig.to_dict()` — shows scalar bool serialization pattern alongside a nested block

### Tests
- `scripts/tests/test_config_schema.py:39` — `test_issues_next_issue_in_schema` (shape to follow)
- `scripts/tests/test_config_schema.py:120` — `test_learning_tests_in_schema` (boolean field with `default` assertion pattern)
- `scripts/tests/test_config.py:167` — `TestIssuesConfig.test_from_dict_with_defaults` (add assertions here)
- `scripts/tests/test_config.py:126` — `TestIssuesConfig.test_from_dict_with_all_fields` (also needs the new fields added)
- `scripts/tests/test_config.py:2262` — `TestBRConfigLearningTestsIntegration.test_learning_tests_round_trip_to_dict` (round-trip `to_dict()` test pattern to follow)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/__init__.py` — re-exports `IssuesConfig` and `BRConfig`; no changes needed (additive fields with defaults are non-breaking) [Agent 1 finding]
- Downstream consumers (`ll-auto`, `ll-parallel`, `ll-sprint`, `issue_manager.py`, `cli/issues/*`) read `config.issues` but do not access `auto_commit` yet — no changes required for this issue; ENH-1844 adds the hook that reads these fields [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — `### \`issues\`` table needs two new rows for `auto_commit` and `auto_commit_prefix`; covered by **ENH-1845** [Agent 2 finding]
- `docs/reference/API.md` — `### IssuesConfig` verbatim `@dataclass` block needs the two new fields shown; covered by **ENH-1845** [Agent 2 finding]
- `skills/configure/areas.md` — `## Area: issues` Current Values block needs entries for the new fields; covered by **ENH-1845** [Agent 2 finding]

## Implementation Steps

1. Update `config-schema.json` — add both fields under `issues.properties` (before line 241)
2. Update `IssuesConfig` dataclass and `from_dict()` in `scripts/little_loops/config/features.py` (lines 203, 238)
3. Update `BRConfig.to_dict()` in `scripts/little_loops/config/core.py` to serialize new fields (after line 518)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Add `test_issues_auto_commit_in_schema()` to `scripts/tests/test_config_schema.py` (follow `test_issues_next_issue_in_schema` pattern at line 39 — navigate `data["properties"]["issues"]["properties"]`, assert `type == "boolean"`, `default is False`, and `auto_commit_prefix` type is `"string"`)
5. Update `scripts/tests/test_config.py` — append assertions to `TestIssuesConfig.test_from_dict_with_defaults` (line 167) and `test_from_dict_with_all_fields` (line 126); add round-trip test following `TestBRConfigLearningTestsIntegration.test_learning_tests_round_trip_to_dict` (line 2262) asserting `d["issues"]["auto_commit"] is False` and `d["issues"]["auto_commit_prefix"] == "chore(issues)"` plus an override-from-config-file test

## Acceptance Criteria

- [ ] `config-schema.json` validates `auto_commit` as boolean and `auto_commit_prefix` as string
- [ ] `IssuesConfig` parses both fields from dict with correct defaults
- [ ] `BRConfig.to_dict()` includes both fields in `issues` sub-dict
- [ ] `test_config_schema.py` — `test_issues_auto_commit_in_schema` passes
- [ ] `test_config.py` — `TestIssuesConfig` default and explicit-value tests pass

## Tests

- `scripts/tests/test_config_schema.py` — add `test_issues_auto_commit_in_schema` asserting `auto_commit` (boolean, default false) and `auto_commit_prefix` (string) are present under `issues.properties`; follow `test_issues_next_issue_in_schema` pattern
- `scripts/tests/test_config.py` — update `TestIssuesConfig.test_from_dict_with_defaults` (line 167) and `test_from_dict_with_all_fields`; add explicit-value test; add `BRConfig.to_dict()` round-trip test following `TestBRConfigLearningTestsIntegration.test_learning_tests_round_trip_to_dict` (line 2262) asserting `d["issues"]["auto_commit"] is False` and `d["issues"]["auto_commit_prefix"] == "chore(issues)"`

## Similar Patterns

- `scripts/little_loops/config/features.py:394` — `LearningTestsConfig.from_dict()` — boolean flag config pattern
- `scripts/little_loops/config/features.py:403` — `AnalyticsCaptureConfig` (ENH-1840) — most recent analog: mixed `bool + str` flat dataclass with `from_dict()`; `BRConfig.to_dict()` analog at `core.py:596`

## Scope Boundaries

- Out of scope: the hook that reads `auto_commit` at runtime (ENH-1844)
- Out of scope: documentation updates to `CONFIGURATION.md`, `API.md`, `skills/configure/areas.md` (ENH-1845)
- Out of scope: migration of existing user configs — additive defaults mean no migration is needed

## Impact

- **Priority**: P3 — prerequisite for ENH-1844; no standalone user-facing value
- **Effort**: Small — additive dataclass fields with defaults; three-file change following direct analogs
- **Risk**: Low — additive only; schema's `additionalProperties: false` prevents silent config drift
- **Breaking Change**: No

## Labels

`config`, `enhancement`, `auto-commit`

## Status

**Open** | Created: 2026-06-01 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-01T08:24:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cef9a759-47c8-4319-b4e5-d8d5396f9e74.jsonl`
- `/ll:wire-issue` - 2026-06-01T08:19:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d5d94f6b-e683-463c-ba3d-358b7c3f7be7.jsonl`
- `/ll:refine-issue` - 2026-06-01T08:12:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cc2e6b1b-cb20-4a81-9dcd-a97a26e2c8ad.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e2ad9a6-4834-4969-9404-2babd791318d.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82b5e106-31e3-4359-8b6e-b9f524e989b2.jsonl`
