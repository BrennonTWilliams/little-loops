---
id: ENH-3450
type: ENH
title: Add has_history any-rows-ever signal to RepoActivity and WorkspaceTotals
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-11'
captured_at: '2026-09-11T20:26:38Z'
---

# ENH-3450: Add has_history any-rows-ever signal to RepoActivity and WorkspaceTotals

## Summary

`RepoActivity.instrumented` (in `scripts/little_loops/issue_history/workspace_activity.py`) means "a history.db file exists", not "any activity was ever recorded". A schema'd-but-empty db and a db with rows outside the `--since/--until` window both report `instrumented: true` with zero counts, so a consumer cannot tell "empty db" from "quiet window". Add a separate `has_history` signal; do not redefine `instrumented`.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

**Verified in code** (`aggregate_workspace_activity()`):

- Non-ok branches: `instrumented=status is not MemberActivityStatus.DB_MISSING` (line 277).
- Count-failure branch: `instrumented=True` (line 291).
- Ok branch: `instrumented=True` (line 304).

So `instrumented` is true whenever the file exists. A downstream consumer (little-loops-hermes) must distinguish "empty db" (tables exist, zero rows ever) from "quiet window" (rows exist, none in window). It reports "measured zero activity" only for the latter; treating the former as measured-zero is exactly the "no answer ≠ zero" conflation its own code exists to prevent.

`instrumented` is load-bearing in the workspace quality reader and its tests, so it must keep its current meaning.

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

1. Add `_has_any_history(conn) -> bool` next to `_count_member_activity` in `workspace_activity.py` using the EXISTS query.
2. Call it in the ok path (inside the existing `try`, so `sqlite3.Error` routes to `UNREADABLE`); set `has_history=False` in the `DB_MISSING` case and `None` for `SCHEMA_SKEW`/`UNREADABLE`.
3. Extend `_totals()` with `has_history_members` and `has_history`.
4. Update `to_dict()` on both dataclasses and the text/markdown formatters.
5. Update the module docstring and `docs/reference/API.md` (workspace_activity section) and `docs/reference/CLI.md` (ll-history activity output shape).
6. Tests (see AC).

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Decisions (resolved, do not re-derive)

1. **New field, not a redefinition.** Add `has_history: bool | None` to `RepoActivity` meaning "at least one row exists in `issue_events` OR `loop_runs`, irrespective of the window".
2. **Values per status:**
   - `ok`: computed via `SELECT EXISTS(SELECT 1 FROM issue_events) OR EXISTS(SELECT 1 FROM loop_runs)` (cheap, no scan).
   - `db_missing`: `False` (a real answer: nothing recorded).
   - `schema_skew` / `unreadable`: `None` (JSON `null`). `False` would assert "no rows", which is the same no-answer-≠-zero conflation. If the EXISTS query itself raises `sqlite3.Error`, it falls into the existing `UNREADABLE` branch → `None`.
3. **Totals mirror the `instrumented` pattern:** `WorkspaceTotals.has_history_members: int` (count of members with `has_history is True`) and `WorkspaceTotals.has_history: bool` (any).
4. **JSON key placement:** `has_history` appended immediately after `instrumented` in `RepoActivity.to_dict()`; `has_history_members` and `has_history` immediately after `instrumented` in `WorkspaceTotals.to_dict()`. Existing key order otherwise unchanged (FEAT-3446 AC 1 stable-order contract preserved for existing keys).

## API/Interface

- `RepoActivity.has_history: bool | None` (new dataclass field, default `None`).
- `WorkspaceTotals.has_history_members: int`, `WorkspaceTotals.has_history: bool` (new fields).
- JSON/YAML output from `ll-history activity` gains the three keys above. Text/markdown formatters show `has_history` alongside `instrumented` counts.

## Acceptance Criteria

- [ ] Empty schema'd db (tables, zero rows): `instrumented: true`, `has_history: false`, counts zero.
- [ ] Db with rows all outside the window: `instrumented: true`, `has_history: true`, counts zero.
- [ ] Db with one `loop_runs` row and no `issue_events` (and vice versa): `has_history: true`.
- [ ] `db_missing`: `has_history: false`. `schema_skew` and `unreadable`: `has_history: null` in JSON.
- [ ] `WorkspaceTotals` JSON contains `has_history_members` and `has_history` with the any/count semantics above.
- [ ] Existing `instrumented` semantics and all workspace_quality tests unchanged.
- [ ] Docs updated; `python -m pytest scripts/tests/` passes.

## Related

- FEAT-3445, FEAT-3446 (shipped `ll-history activity`).
- Sibling: ENH-3449 (analytics opt-out env var for CLI read paths), same consumer.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-11 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-09-11T20:26:49 - `d2544764-cca3-4cd1-bd27-85b0d1d0f3c3.jsonl`
