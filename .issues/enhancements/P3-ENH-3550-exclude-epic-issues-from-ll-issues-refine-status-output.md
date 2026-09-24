---
id: ENH-3550
type: ENH
title: Exclude EPIC issues from ll-issues refine-status output
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T18:17:10Z'
---

# ENH-3550: Exclude EPIC issues from ll-issues refine-status output

## Summary

`ll-issues refine-status` should exclude EPIC issues from its output (table, `--json`, `--format json`). EPICs are containers decomposed into child BUG/FEAT/ENH issues; they are not refined through the per-issue refinement pipeline, so their rows (and command-touch counts) are noise in a refinement-depth table.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

`cmd_refine_status` in `scripts/little_loops/cli/issues/refine_status.py` lists every active issue, including EPIC-typed ones. EPICs never accumulate refinement commands the way BUG/FEAT/ENH do, so they sink to the bottom of the "sorted by commands touched" view and distort the picture of what still needs refinement.

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Proposed Change

- Filter out issues of type `EPIC` in `cmd_refine_status` before rendering, for all output formats.
- Decide behavior for explicit `--type EPIC` and for `refine-status EPIC-NNN` (single-ID lookup): recommend keeping the exclusion silent for the default listing, and returning a clear "EPICs are not tracked by refine-status" message for explicit requests rather than an empty table.
- Update `ll-issues refine-status --help` / `docs/reference/CLI.md` to note EPICs are excluded.

## Acceptance Criteria

- [ ] Default `ll-issues refine-status` output contains no EPIC rows
- [ ] `--json` / `--format json` output contains no EPIC entries
- [ ] Explicit EPIC `--type` / ID request gives a clear message instead of a confusing empty result
- [ ] Test added under `scripts/tests/` covering EPIC exclusion
- [ ] CLI reference updated

## Related

- ENH-596 (colorize refine-status output) touches the same command; no overlap in behavior.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-24T18:17:16 - `12e7e1d6-d62f-431d-b8e0-a48dad1b4619.jsonl`
