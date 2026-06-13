---
id: ENH-2114
title: "Wire loops.run_defaults into /ll:configure skill"
type: ENH
status: open
priority: P3
captured_at: "2026-06-13T18:07:59Z"
discovered_date: "2026-06-13"
discovered_by: capture-issue
testable: false
---

# ENH-2114: Wire loops.run_defaults into /ll:configure skill

## Summary

The `/ll:configure` skill (`skills/configure/`) has no awareness of `loops.run_defaults`. The setting added in ENH-2109 (`clear`, `show_diagrams`, `mode` under `loops.run_defaults`) cannot be discovered or set via the interactive configure flow — users must hand-edit `ll-config.json` directly.

## Current Behavior

`skills/configure/areas.md` defines all configurable areas surfaced by `/ll:configure`. It has no entry for `loops.run_defaults` or any sub-fields of it. Running `/ll:configure` gives no indication that persistent `ll-loop run` defaults exist as a config option.

## Expected Behavior

`/ll:configure` should expose `loops.run_defaults` as a configurable area, allowing users to:
- Set `clear` (bool) — whether to clear the screen before each loop run
- Set `show_diagrams` (string enum: topology, preset, both, none) — diagram display mode
- Set `mode` (string) — default execution mode (e.g. `--dry-run`, `--interactive`)

The area description should explain what each field does and what the valid values are (especially the `show_diagrams` enum validated in `LoopRunDefaults.from_dict()`).

## Motivation

`loops.run_defaults` was shipped in ENH-2109 but `/ll:configure` is the canonical discovery surface for project config. Users who reach for `/ll:configure` to tweak loop behavior will find nothing and likely assume the feature doesn't exist. Wiring it in closes the discoverability gap without requiring doc-reading.

## Proposed Solution

Add a `loops.run_defaults` entry to `skills/configure/areas.md`. The entry should include:
- Area name/key: `loops.run_defaults`
- Description of each sub-field with valid values
- The `show_diagrams` enum values (from `config/features.py:_VALID_SHOW_DIAGRAMS`): `topology`, `preset`, `both`, `none`
- Example config snippet showing a complete `loops.run_defaults` block

Optionally, if `/ll:configure` supports interactive prompting per area, add prompts for each field (clear: yes/no, show_diagrams: enum select, mode: freetext).

## Integration Map

### Files to Modify
- `skills/configure/areas.md` — add `loops.run_defaults` area entry

### Dependent Files (Callers/Importers)
- `skills/configure/SKILL.md` — skill entrypoint; may reference areas.md for the list of supported areas
- `scripts/little_loops/config/features.py:_VALID_SHOW_DIAGRAMS` — source of truth for `show_diagrams` enum values; copy into areas.md

### Similar Patterns
- Existing entries in `skills/configure/areas.md` — follow the same format for consistency

### Tests
- No automated tests for skill content; manual verification that `/ll:configure loops.run_defaults` surfaces the correct options

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — already documents `loops.run_defaults`; cross-reference to `/ll:configure` could be added

### Configuration
- `config-schema.json` — `loops.run_defaults` schema already present; `areas.md` should mirror valid values

## Implementation Steps

1. Read `skills/configure/areas.md` to understand the existing area entry format
2. Read `scripts/little_loops/config/features.py` to extract `_VALID_SHOW_DIAGRAMS` values
3. Add `loops.run_defaults` area entry to `areas.md` with per-field docs and examples
4. Verify `/ll:configure` renders the new area correctly in a dry run

## Impact

- **Priority**: P3 - Discoverability gap; feature works without this
- **Effort**: Small - Markdown edit only; no code changes
- **Risk**: Low - Documentation-only change to skill definition
- **Breaking Change**: No

## Scope Boundaries

- Does not change `LoopRunDefaults` validation logic or defaults
- Does not add new config fields beyond what ENH-2109 shipped
- Does not add TUI-style interactive prompting if the configure skill doesn't already support it

## Success Metrics

- `/ll:configure loops.run_defaults` (or equivalent area selection) renders the area description with all three sub-fields (`clear`, `show_diagrams`, `mode`) and their valid values
- The `show_diagrams` enum values (`topology`, `preset`, `both`, `none`) are visible without requiring the user to read `features.py` or `config-schema.json`
- A user who has never set loop defaults can discover and apply them through `/ll:configure` alone

## Related Key Documentation

- `docs/guides/LOOPS_GUIDE.md` — documents `loops.run_defaults` at the guide level; `/ll:configure` area should align with this
- `config-schema.json` — defines the `loops.run_defaults` schema; `areas.md` valid-value list must mirror it
- `skills/configure/SKILL.md` — skill entrypoint; describes how areas are discovered and rendered

## Labels

`enhancement`, `configure`, `loops`, `captured`

## Session Log
- `/ll:format-issue` - 2026-06-13T18:12:09 - `4821328e-80ea-46ad-b04b-631e490d2e81.jsonl`

- `/ll:capture-issue` - 2026-06-13T18:07:59Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/68161d6f-aa46-4b19-8309-5c8794319dc2.jsonl`

---

## Status

**Open** | Created: 2026-06-13 | Priority: P3
