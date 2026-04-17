---
id: ENH-1128
type: ENH
priority: P3
status: completed
parent: ENH-1111
size: Small
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1128: Extend config-schema.json with scratch_pad Properties

## Summary

Extend the existing `scratch_pad` config block in `config-schema.json:526-544` with four new properties required by the PreToolUse hook (ENH-1129), add a commented-out template block to `.ll/ll-config.json`, and add `test_config_schema.py` assertions so schema drift is caught in CI.

## Parent Issue

Decomposed from ENH-1111: Scratch-Pad Enforcement via PreToolUse Hook

## Motivation

The `scratch_pad` schema block already exists (`config-schema.json:526-544`) with only `enabled` (bool, default `false`) and `threshold_lines` (int, default 200). The hook in ENH-1129 requires four additional properties. Because the block uses `additionalProperties: false`, the schema must be extended before the hook can read these values via `ll_config_value`.

## Acceptance Criteria

- `config-schema.json:526-544` `scratch_pad.properties` is extended with:
  - `automation_contexts_only` (bool, default `true`)
  - `tail_lines` (int, default 20, min 5, max 200)
  - `command_allowlist` (array of strings, default `["cat","pytest","mypy","ruff","ls","grep","find"]`)
  - `file_extension_filters` (array of strings, default `[".log",".txt",".json",".md",".py",".ts",".tsx",".js"]`)
- `.ll/ll-config.json` gains a commented-out `scratch_pad` block as an opt-in template
- `scripts/tests/test_config_schema.py` asserts all four new properties exist with expected defaults

## Files to Modify

- `config-schema.json:526-544` — add 4 new properties to `scratch_pad.properties`
- `.ll/ll-config.json` — add commented-out template block
- `scripts/tests/test_config_schema.py` — extend to assert new `scratch_pad` properties

## Similar Patterns

- `config-schema.json:447-525` (`context_monitor`) — reference for a richer properties block with bounds and nested objects
- `scripts/tests/test_config_schema.py:12-26` (`TestConfigSchema`) — existing regression-guard pattern: `json.loads(CONFIG_SCHEMA.read_text())` then assert on nested `properties` keys

## Integration Map

### Files to Modify
- `config-schema.json:526-544` — extend `scratch_pad.properties` with 4 new keys (bounded by `additionalProperties: false` at line 543)
- `.ll/ll-config.json:25-28` — add `scratch_pad` template block (see Open Decision below on the "commented-out" requirement)
- `scripts/tests/test_config_schema.py:12` — extend existing `TestConfigSchema` class with new assertions; follow the `json.loads` + nested `properties` assertion style already in `test_extensions_in_properties` at line 19

### Downstream Consumers (read-only, do not modify here)
- `hooks/scripts/lib/common.sh:218-234` (`ll_config_value`) — the function ENH-1129 will call to resolve `scratch_pad.tail_lines`, `scratch_pad.command_allowlist`, etc. Uses `jq -r ".${key_path} // empty"`; default fallbacks in the bash caller mean the schema extension is primarily for validation and typo-catching, not runtime resolution
- `hooks/scripts/lib/common.sh:198-212` (`ll_feature_enabled`) — resolves `scratch_pad.enabled` for the new hook's no-op gate

### Tests
- `scripts/tests/test_config_schema.py` — existing file, extend the `TestConfigSchema` class (do not create a new file)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:155-158` — full example JSON block contains current 2-key `scratch_pad` block; will need 4 new keys once ENH-1128 ships (owned by sibling ENH-1130)
- `docs/reference/CONFIGURATION.md:474-481` — `### scratch_pad` reference table has only 2 rows; needs 4 new rows for the new properties (owned by sibling ENH-1130)
- `site/reference/CONFIGURATION/index.html` — generated artifact mirroring CONFIGURATION.md; will be stale until site is regenerated (not covered by any test suite; not in ENH-1128 or ENH-1130 scope)

## Open Decisions

- **"Commented-out" block in JSON**: `.ll/ll-config.json` is parsed by `scripts/little_loops/config/core.py:92` via plain `json.load`, which does not support `//` comments. Two viable implementations:
  1. **Underscore-prefix key** (`"_scratch_pad": { ... }`) — inert because it won't match the schema's `scratch_pad` key; users rename to activate. Self-documenting.
  2. **Inactive block with `enabled: false`** (`"scratch_pad": { "enabled": false, ... }`) — validates against the schema, defaults visible, user flips `enabled` to `true` to activate.
  - **Recommendation**: option 2 (inactive block with `enabled: false`). It validates, documents all defaults inline, and matches the `context_monitor` block already present at lines 25-28. Does not require any parser changes.

## Implementation Steps

1. **Extend schema** — in `config-schema.json:529-542`, insert four new properties after `threshold_lines`:
   - `automation_contexts_only` (bool, default `true`)
   - `tail_lines` (int, default 20, minimum 5, maximum 200)
   - `command_allowlist` (array of strings, default `["cat","pytest","mypy","ruff","ls","grep","find"]`, `items: {"type": "string"}`)
   - `file_extension_filters` (array of strings, default `[".log",".txt",".json",".md",".py",".ts",".tsx",".js"]`, `items: {"type": "string"}`)
   - Use `context_monitor.estimate_weights` (lines 466-498) as the style reference for bounded numbers; use `scan.exclude_patterns` (existing in `.ll/ll-config.json:16-23`) as the style reference for string arrays.

2. **Add template block to `.ll/ll-config.json`** — append (per Open Decision, option 2):
   ```json
   "scratch_pad": {
     "enabled": false,
     "threshold_lines": 200,
     "automation_contexts_only": true,
     "tail_lines": 20,
     "command_allowlist": ["cat", "pytest", "mypy", "ruff", "ls", "grep", "find"],
     "file_extension_filters": [".log", ".txt", ".json", ".md", ".py", ".ts", ".tsx", ".js"]
   }
   ```
   Place after the `context_monitor` block (line 28) to group context/observation settings.

3. **Extend `test_config_schema.py`** — add a new test method to `TestConfigSchema` following the `test_extensions_in_properties` pattern at line 19:
   ```python
   def test_scratch_pad_properties(self) -> None:
       data = json.loads(CONFIG_SCHEMA.read_text())
       props = data["properties"]["scratch_pad"]["properties"]
       assert props["automation_contexts_only"]["default"] is True
       assert props["tail_lines"]["default"] == 20
       assert props["tail_lines"]["minimum"] == 5
       assert props["tail_lines"]["maximum"] == 200
       assert "cat" in props["command_allowlist"]["default"]
       assert ".py" in props["file_extension_filters"]["default"]
   ```

4. **Verify** — run `python -m pytest scripts/tests/test_config_schema.py -v` and `python -c "import json; json.load(open('.ll/ll-config.json'))"` to confirm schema is valid JSON and the template parses.

## Impact

- **Priority**: P3 — Foundational prerequisite for ENH-1129 hook work; schema-only change is low-urgency on its own.
- **Effort**: Small — ~20 lines of schema JSON, 1 template block, 1 test method; purely additive.
- **Risk**: Low — `additionalProperties: false` remains enforced; new keys have defaults matching hook behavior; existing `scratch_pad.enabled=false` default preserves no-op state.
- **Breaking Change**: No

## Scope Boundaries

- Out of scope: the PreToolUse hook implementation itself (ENH-1129) and documentation updates to `docs/reference/CONFIGURATION.md` (ENH-1130).
- Out of scope: regenerating `site/reference/CONFIGURATION/index.html`.
- Out of scope: changing existing `scratch_pad.enabled` or `threshold_lines` defaults.

## Labels

`enhancement`, `config`, `schema`, `scratch-pad`, `parent-ENH-1111`

## Session Log
- `/ll:ready-issue` - 2026-04-17T03:26:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/951ded3e-753e-42fd-8f39-9fd9094e2226.jsonl`
- `/ll:confidence-check` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10664fc9-e8f4-4704-aef0-4df6fb9ba0c9.jsonl`
- `/ll:wire-issue` - 2026-04-17T03:20:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a1d5130-4f36-4679-8288-365c673b3c29.jsonl`
- `/ll:refine-issue` - 2026-04-17T03:15:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/841f3369-f515-4521-99ea-cce418852f36.jsonl`
- `/ll:issue-size-review` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4fc25386-a9f0-4e75-8434-c659db481895.jsonl`
- `/ll:manage-issue` - 2026-04-16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2436aadd-5394-4708-8fd9-aadfc40d82f6.jsonl`

**Status**: Completed | Created: 2026-04-16 | Completed: 2026-04-16 | Priority: P3

## Resolution

Extended `config-schema.json` `scratch_pad` block with four new properties (`automation_contexts_only`, `tail_lines`, `command_allowlist`, `file_extension_filters`) per spec. Added an inert opt-in `scratch_pad` template block to `.ll/ll-config.json` with `enabled: false`. Added `test_scratch_pad_properties` regression guard to `scripts/tests/test_config_schema.py`.

### Changes
- `config-schema.json` — 4 new properties added to `scratch_pad.properties` (keeps `additionalProperties: false`); bounded int (`tail_lines`), boolean (`automation_contexts_only`), and two string arrays with defaults matching the ENH-1129 hook.
- `.ll/ll-config.json` — new `scratch_pad` template block grouped after `context_monitor`; validates against the extended schema with `enabled: false` preserving no-op state.
- `scripts/tests/test_config_schema.py` — new `test_scratch_pad_properties` asserts defaults, bounds, and key presence (follows `test_extensions_in_properties` pattern).

### Verification
- `python -m pytest scripts/tests/` → 4857 passed, 5 skipped
- `ruff check scripts/tests/test_config_schema.py` → clean
- `python -m mypy scripts/tests/test_config_schema.py` → clean
- `json.load` on both JSON files → parses OK

Red phase verified before implementation: new test failed with `KeyError: 'automation_contexts_only'`, then passed after schema extension.
