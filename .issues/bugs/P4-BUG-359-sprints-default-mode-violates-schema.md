---
discovered_date: 2026-02-12
discovered_by: audit_claude_config
---

# BUG-359: sprints.default_mode in config violates additionalProperties:false in schema

## Summary

`ll-config.json` contains `sprints.default_mode: "auto"` (line 36), but `config-schema.json` defines the `sprints` section with `additionalProperties: false` and no `default_mode` property. A strict JSON Schema validator would reject the config file.

## Location

- **Config**: `.claude/ll-config.json:36`
- **Schema**: `config-schema.json` (sprints section)

## Current Behavior

The `default_mode` key exists in config and test fixtures (`scripts/tests/conftest.py:109`, `scripts/tests/test_cli_e2e.py:114`) but is not consumed by any production code in `scripts/little_loops/`.

## Expected Behavior

Either:
1. Add `default_mode` property to the `sprints` schema section (if the feature is planned), or
2. Remove `default_mode` from `ll-config.json` and test fixtures (if unused)

## Motivation

This bug would:
- Ensure schema validation correctness so strict JSON Schema validators do not reject the config file
- Business value: Prevents confusing validation errors for users or CI systems that validate config against the schema
- Technical debt: Resolves a config-schema divergence that indicates either dead code or a missing schema property

## Root Cause

- **File**: `.claude/ll-config.json:36` and `config-schema.json`
- **Anchor**: `in sprints section`
- **Cause**: The `default_mode` key was added to `ll-config.json` (and test fixtures) but a corresponding property definition was never added to the `sprints` section of `config-schema.json`, which uses `additionalProperties: false`

## Implementation Steps

1. Determine whether `default_mode` is a planned feature or dead configuration
2. If planned: add a `default_mode` property (with enum values and description) to the `sprints` section of `config-schema.json`
3. If unused: remove `default_mode` from `.claude/ll-config.json`, `scripts/tests/conftest.py`, and `scripts/tests/test_cli_e2e.py`
4. Update any test fixtures that reference `sprints.default_mode`
5. Verify schema validation passes with the corrected config

## Integration Map

### Files to Modify
- `.claude/ll-config.json` — remove or keep `default_mode`
- `config-schema.json` — add `default_mode` property if keeping

### Dependent Files (Callers/Importers)
- `scripts/tests/conftest.py` — test fixture references `default_mode`
- `scripts/tests/test_cli_e2e.py` — test fixture references `default_mode`

### Similar Patterns
- Other config keys that may exist in config but not in schema

### Tests
- `scripts/tests/conftest.py` — update fixtures
- `scripts/tests/test_cli_e2e.py` — update fixtures

### Documentation
- N/A

### Configuration
- `.claude/ll-config.json` — sprints section
- `config-schema.json` — sprints schema section

## Impact

- **Priority**: P4
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `config`, `schema`

## Blocked By

- ENH-342: command examples hardcode tool names (shared ll-config.json)

---

## Status

**Open** | Created: 2026-02-12 | Priority: P4

---

## Tradeoff Review Note

**Reviewed**: 2026-02-12 by `/ll:tradeoff_review_issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | LOW |
| Complexity added | LOW |
| Technical debt risk | MEDIUM |
| Maintenance overhead | LOW |

### Recommendation
Update first - Schema-config mismatch needs investigation to determine if this is dead code or missing implementation. Decision required: add `default_mode` schema property (if the feature is planned), or remove `default_mode` from config and test fixtures (if unused).

## Verification Notes

- **Verified**: 2026-02-13
- **Verdict**: NEEDS_UPDATE
- `default_mode` has been **removed from ll-config.json** — the main config is now fixed
- However, test fixtures still contain the stale key:
  - `scripts/tests/conftest.py:109` still has `"default_mode": "auto"`
  - `scripts/tests/test_cli_e2e.py:114` still has `"default_mode": "auto"`
- Schema still does NOT define `default_mode`; `additionalProperties: false` is set
- Issue scope should narrow to: remove `default_mode` from test fixtures only

## Session Log
- `/ll:format_issue --all --auto` - 2026-02-13
