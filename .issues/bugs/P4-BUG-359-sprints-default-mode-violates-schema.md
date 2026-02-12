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

## Impact

- **Priority**: P4
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `config`, `schema`

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
