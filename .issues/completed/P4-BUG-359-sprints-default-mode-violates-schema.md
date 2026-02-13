---
discovered_date: 2026-02-12
discovered_by: audit_claude_config
---

# BUG-359: sprints.default_mode in config violates additionalProperties:false in schema

## Summary

Test fixtures contain `sprints.default_mode: "auto"` which is not defined in `config-schema.json` (which uses `additionalProperties: false`). The key was already removed from `ll-config.json` but remains in two test fixtures. No production code consumes `default_mode`.

## Location

- **File**: `scripts/tests/conftest.py:109`
- **Anchor**: `in sample_config fixture, sprints section`
- **File**: `scripts/tests/test_cli_e2e.py:114`
- **Anchor**: `in _create_config method, sprints section`
- **Schema**: `config-schema.json` (sprints section, `additionalProperties: false`)

## Steps to Reproduce

1. Run JSON Schema validation of test fixture config against `config-schema.json`
2. Observe that `sprints.default_mode` violates `additionalProperties: false`

## Current Behavior

Test fixtures in `scripts/tests/conftest.py:109` and `scripts/tests/test_cli_e2e.py:114` include `"default_mode": "auto"` in the `sprints` section, which is not a valid property per the schema.

## Actual Behavior

A strict JSON Schema validator rejects test configs containing `sprints.default_mode` because the schema declares `additionalProperties: false` for the `sprints` section and does not define a `default_mode` property.

## Expected Behavior

Remove `default_mode` from test fixtures so they conform to the schema.

## Motivation

This bug would:
- Ensure schema validation correctness so strict JSON Schema validators do not reject the config file
- Business value: Prevents confusing validation errors for users or CI systems that validate config against the schema
- Technical debt: Resolves a config-schema divergence that indicates either dead code or a missing schema property

## Root Cause

- **File**: `scripts/tests/conftest.py:109` and `scripts/tests/test_cli_e2e.py:114`
- **Anchor**: `in sprints section of test fixture configs`
- **Cause**: The `default_mode` key was removed from `ll-config.json` but the corresponding test fixtures were not updated. No production code consumes this key.

## Implementation Steps

1. Remove `"default_mode": "auto"` from `scripts/tests/conftest.py` sprints fixture
2. Remove `"default_mode": "auto"` from `scripts/tests/test_cli_e2e.py` sprints fixture
3. Run tests to verify nothing depends on this key

## Integration Map

### Files to Modify
- `scripts/tests/conftest.py` — remove `default_mode` from `sample_config` fixture
- `scripts/tests/test_cli_e2e.py` — remove `default_mode` from `_create_config` method

### Dependent Files (Callers/Importers)
- N/A — no production code references `default_mode`

### Similar Patterns
- N/A

### Tests
- `scripts/tests/conftest.py` — the file being modified is itself a test fixture
- `scripts/tests/test_cli_e2e.py` — the file being modified is itself a test file

### Documentation
- N/A — test fixture cleanup, no user-facing doc changes

### Configuration
- `config-schema.json` — defines `sprints` section with `additionalProperties: false` (no changes needed)

## Impact

- **Priority**: P4
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `config`, `schema`

## Blocked By

None — `ll-config.json` is no longer modified by this issue (scope narrowed to test fixtures only).

---

## Status

**Completed** | Created: 2026-02-12 | Completed: 2026-02-13 | Priority: P4

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

## Resolution

- **Action**: fix
- **Completed**: 2026-02-13
- **Status**: Completed

### Changes Made
- `scripts/tests/conftest.py`: Removed `"default_mode": "auto"` from `sample_config` sprints fixture
- `scripts/tests/test_cli_e2e.py`: Removed `"default_mode": "auto"` from `_create_config` sprints section

### Verification Results
- Tests: PASS (2728 passed)
- Lint: PASS
- Types: PASS

## Session Log
- `/ll:format_issue --all --auto` - 2026-02-13
- `/ll:manage_issue` - 2026-02-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3277caec-96af-44a0-a3eb-f6fa8595c338.jsonl`
