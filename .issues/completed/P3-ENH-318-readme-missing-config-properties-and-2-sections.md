---
discovered_commit: 2347db3
discovered_branch: main
discovered_date: 2026-02-10T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# ENH-318: README missing config properties and 2 undocumented sections

## Summary

Documentation issue found by `/ll:audit_docs`. Several config properties are missing from existing README tables, and two config sections defined in `config-schema.json` (`workflow`, `prompt_optimization`) have no README documentation.

## Current Behavior

The README configuration reference is incomplete:
- The `project` table (line 227) is missing the `test_dir` property
- The `issues` table (line 242) is missing `capture_template` and `duplicate_detection` properties
- The `workflow` and `prompt_optimization` config sections have no documentation in the README

## Expected Behavior

All config properties and sections defined in `config-schema.json` should be documented in the README configuration reference.

## Current Pain Point

Users cannot discover `test_dir`, `capture_template`, `duplicate_detection`, `workflow`, or `prompt_optimization` settings from the README alone. They must read `config-schema.json` directly, reducing discoverability.

## Missing Properties in Existing Tables

### `project` table (line 227)

- `test_dir` (default: `"tests"`) - Test directory path

### `issues` table (line 242)

- `capture_template` (enum: `"full"` / `"minimal"`, default: `"full"`) - Default template style for captured issues
- `duplicate_detection` object with:
  - `exact_threshold` (default: 0.8) - Jaccard similarity threshold for exact duplicates
  - `similar_threshold` (default: 0.5) - Jaccard similarity threshold for similar issues

## Undocumented Config Sections

### `workflow`

Phase gates, deep research, and plan template settings:
- `phase_gates.enabled` (default: true)
- `phase_gates.auto_mode_skip` (default: true)
- `deep_research.enabled` (default: true)
- `deep_research.quick_flag_skips` (default: true)
- `deep_research.agents` (default: 3 sub-agents)
- `plan_template.sections_recommended` (default: true)
- `plan_template.sections_mandatory` (default: false)

### `prompt_optimization`

Automatic prompt optimization settings (toggle with `/ll:toggle_autoprompt`):
- `enabled` (default: true)
- `mode` (enum: quick/thorough, default: "quick")
- `confirm` (default: true)
- `bypass_prefix` (default: "*")
- `clarity_threshold` (default: 6)

## Proposed Solution

Add a `workflow` and `prompt_optimization` section table to the README Configuration Sections area (between `scan` and `continuation`). Add the missing `test_dir`, `capture_template`, and `duplicate_detection` rows to their respective existing tables.

## Scope Boundaries

- Out of scope: `context_monitor` section (already has a dedicated doc reference)
- Out of scope: Restructuring existing documented sections
- Out of scope: Adding usage examples or guides for these settings

## Context

ENH-314 (completed 2026-02-10) explicitly listed these as "out of scope" when adding `sync`, `sprints`, and `documents` sections. This issue covers the remaining gap. Note: `continuation` was originally listed here but is already documented in README (line 321).

## Impact

- **Severity**: Low (features work without docs, but discoverability suffers)
- **Effort**: Low (2 new section tables + 3 property additions to existing tables)
- **Risk**: Low

## Labels

`enhancement`, `documentation`, `auto-generated`

---

## Status

**Completed** | Created: 2026-02-10 | Completed: 2026-02-10 | Priority: P3

---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-10
- **Status**: Completed

### Changes Made
- `README.md`: Added `test_dir` row to `project` config table
- `README.md`: Added `capture_template` and `duplicate_detection` rows to `issues` config table
- `README.md`: Added new `workflow` section table (7 properties with dot notation)
- `README.md`: Added new `prompt_optimization` section table (5 properties)
- `README.md`: Updated Full Configuration Example with all missing properties and sections

### Verification Results
- Tests: N/A (documentation-only change)
- Lint: N/A (documentation-only change)
- Types: N/A (documentation-only change)
- Integration: PASS
