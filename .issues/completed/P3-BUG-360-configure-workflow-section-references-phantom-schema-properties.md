---
discovered_date: 2026-02-12
discovered_by: audit_claude_config
---

# BUG-360: configure command workflow section references phantom schema properties

## Summary

`commands/configure.md` (lines 235-247) defines a `workflow` configuration area with 5 settings (`phase_gates.enabled`, `phase_gates.auto_mode_skip`, `deep_research.enabled`, `deep_research.quick_flag_skips`, `deep_research.agents`), but no `workflow` property exists in `config-schema.json`. The root schema specifies `additionalProperties: false`.

## Location

- **File**: `commands/configure.md:235-247`
- **Schema**: `config-schema.json` (no `workflow` section)

## Current Behavior

Running `/ll:configure workflow --show` would display unresolvable `{{config.workflow.*}}` template placeholders.

## Expected Behavior

Either:
1. Add a `workflow` section to `config-schema.json` with the 5 properties, or
2. Remove the `workflow --show` section from `configure.md` if the feature was abandoned

## Impact

- **Priority**: P3
- **Effort**: Medium - requires deciding whether to add schema or remove dead config section
- **Risk**: Low

## Labels

`bug`, `commands`, `config`, `schema`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P3

---

## Tradeoff Review Note

**Reviewed**: 2026-02-12 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | MEDIUM |
| Complexity added | MEDIUM |
| Technical debt risk | MEDIUM |
| Maintenance overhead | LOW |

### Recommendation
Update first - Requires architectural decision about whether workflow configuration is planned or abandoned. If planned, needs schema design; if abandoned, needs documentation cleanup. Scope unclear until decision is made.
