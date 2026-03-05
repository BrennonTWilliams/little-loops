---
id: ENH-587
priority: P4
type: ENH
status: open
title: "Make ll-issues refine-status table columns configurable via ll-config.json"
discovered_date: 2026-03-05
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 86
---

# ENH-587: Make ll-issues refine-status table columns configurable via ll-config.json

## Summary

Add a `refine_status.columns` configuration key to `ll-config.json` so users can control which columns appear in the `ll-issues refine-status` output table and in what order, without editing source code.

## Motivation

The `ll-issues refine-status` command outputs a fixed-column table. Users with different workflows may want to show/hide columns (e.g., hide `confidence_score` when not using confidence checks, show custom frontmatter fields, reorder columns) without modifying the source code. Exposing column configuration in `.claude/ll-config.json` makes the output adaptable per project.

## Current Behavior

`ll-issues refine-status` renders a hardcoded set of columns in a fixed order. There is no way to configure which columns appear or in what order without editing `scripts/little_loops/`.

## Expected Behavior

A `refine_status.columns` key in `.claude/ll-config.json` (or `ll-config.json`) allows users to specify an ordered list of columns to display. Unrecognized column names should either be ignored with a warning or mapped to frontmatter fields dynamically.

### Example Config

```json
{
  "refine_status": {
    "columns": ["id", "priority", "title", "status", "confidence_score", "outcome_confidence"]
  }
}
```

### Expected Table Behavior

- When `columns` is set, render only those columns in that order.
- When `columns` is absent or empty, fall back to the current default column set.
- Column names should map to issue frontmatter keys or computed display fields.

## Proposed Solution

Load a `refine_status.columns` list from `ll-config.json` in the `refine-status` render path. When present, filter and reorder the display columns accordingly; when absent, use the existing hardcoded defaults. Map column names to frontmatter keys or computed display fields, rendering `—` for missing or unknown keys (no crash).

```python
# In the refine-status render function
config_columns = config.get("refine_status", {}).get("columns", None)
columns = config_columns if config_columns else DEFAULT_COLUMNS
```

## API/Interface

### Config Schema (`config-schema.json`)

```json
{
  "refine_status": {
    "columns": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Ordered list of columns to display in refine-status output. Omit or leave empty to use defaults.",
      "default": []
    }
  }
}
```

No new CLI flags. No new Python public API.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/refine_status.py` — `cmd_refine_status` and hardcoded column widths/layout (lines 14–57 define constants; `_row` builds the table row)
- `scripts/little_loops/cli/issues/__init__.py` — registers `refine-status` subcommand; may need to expose new config arg
- `config-schema.json` — add `refine_status.columns` array property

### Dependent Files (Callers/Importers)
- `scripts/little_loops/config.py` (or equivalent config loader) — provides `ll-config.json` data at runtime

### Similar Patterns
- Other CLI commands that read per-command config keys from `ll-config.json` (e.g., existing `issues.base_dir`, `issues.columns` if present)

### Tests
- `scripts/tests/test_refine_status.py` — add tests for custom column list, empty list (fallback), and unknown column name (renders `—`)

### Documentation
- `docs/reference/API.md` — document new `refine_status.columns` config key

### Configuration
- `config-schema.json` — JSON schema update for new key
- `.claude/ll-config.json` — example project-specific config entry

## Implementation Steps

1. Locate the `refine-status` rendering logic in `scripts/little_loops/` (likely `ll_issues.py` or a related CLI module).
2. Add a `refine_status.columns` key to the config schema (`config-schema.json`).
3. Load the column list from config at render time; fall back to hardcoded defaults when absent.
4. Map column names to frontmatter keys or computed values (handle missing keys gracefully with `—`).
5. Update `docs/reference/API.md` or relevant config docs to document the new key.
6. Add a test asserting custom columns are rendered correctly.

## Scope Boundaries

- **In scope**: Column visibility (show/hide), column ordering via `refine_status.columns` config key; graceful `—` for unknown column names.
- **Out of scope**: Adding new computed columns (e.g., cycle time, last-modified); custom column widths or truncation rules; CSV/JSON export formats; filtering or sorting rows by column value; dynamic frontmatter field discovery beyond the existing set.

## Success Metrics

- Custom `columns` config renders only specified columns in the declared order
- Absent/empty `columns` config: current default columns unchanged (0 regression)
- Unknown column name: renders as `—` without error or crash
- Test coverage: 1+ new test in `test_refine_status.py` for custom column config

## Impact

- **Priority**: P4 — Quality-of-life improvement for power users; no blocking use case
- **Effort**: Small — Config loading pattern is well-established across the codebase; change is isolated to the render function and schema
- **Risk**: Low — Purely additive; existing default behavior is fully preserved when config key is absent
- **Breaking Change**: No

## Acceptance Criteria

- [x] `refine_status.columns` in `ll-config.json` controls which columns appear in the table.
- [x] Default behavior (no config key) is unchanged.
- [x] Unknown column names render as blank/`—` without crashing.
- [x] Config schema updated and documented.

## Verification Notes

- **VALID** — Core claims verified against `scripts/little_loops/cli/issues/refine_status.py`.
- `cmd_refine_status` uses hardcoded column widths (`_ID_WIDTH`, `_PRI_WIDTH`, etc.) and a fixed `_row()` layout with no config-driven column selection.
- `BRConfig` is passed to `cmd_refine_status` but only used for `find_issues()`; no `refine_status` section exists in `config-schema.json`.
- **Correction applied**: Integration Map originally referenced `ll_issues.py` (non-existent); corrected to `scripts/little_loops/cli/issues/refine_status.py` and added `__init__.py`.
- Test file `scripts/tests/test_refine_status.py` exists and is the correct target for new tests.
- No dependency references in this issue to validate.

## Blocked By

- ENH-459 — both touch `ll-config.json`; ENH-459 should be completed first (file overlap, conflict score: 0.6)

## Related Key Documentation

_None identified._

## Labels

`enhancement`, `config`, `ll-issues`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d3e9ec7e-17c7-4cb7-922e-274afad800f0.jsonl`
- `/ll:format-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/355f2ad5-857c-4db2-9529-3e1ed4f84d7e.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/355f2ad5-857c-4db2-9529-3e1ed4f84d7e.jsonl`
- `/ll:map-dependencies` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/355f2ad5-857c-4db2-9529-3e1ed4f84d7e.jsonl`
- `/ll:confidence-check` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/355f2ad5-857c-4db2-9529-3e1ed4f84d7e.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c5aa134b-94a2-43de-99e6-3c792a77ca23.jsonl`
- `/ll:map-dependencies` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c5aa134b-94a2-43de-99e6-3c792a77ca23.jsonl`
- `/ll:confidence-check` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c5aa134b-94a2-43de-99e6-3c792a77ca23.jsonl`

- `/ll:format-issue` - 2026-03-05T12:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/01471175-2814-49cb-8d28-d70874526382.jsonl`
- `/ll:ready-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/efde53d8-3a4c-4bc4-ac38-1a7c7e7cf6e3.jsonl`
- `/ll:manage-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

## Resolution

**Status**: Completed
**Implemented**: 2026-03-05

### Changes Made
- `scripts/little_loops/config.py` — Added `RefineStatusConfig` dataclass with `columns: list[str]` field; wired into `BRConfig._parse_config` and exposed via `refine_status` property
- `scripts/little_loops/cli/issues/refine_status.py` — Added `_STATIC_COLUMN_SPECS`, `_DEFAULT_STATIC_COLUMNS`, `_POST_CMD_STATIC` constants; replaced hardcoded `_row` closure with data-driven `_build_row`, `_header_cell`, `_cell_value`, `_render_cell` helpers that respect the configured column list
- `config-schema.json` — Added `refine_status.columns` array property with description
- `scripts/tests/test_refine_status.py` — Added `TestRefineStatusConfigColumns` with 3 tests: custom columns render only specified, empty list falls back to defaults, unknown column renders `—`

---
## Status

**Completed** | Created: 2026-03-05 | Priority: P4
