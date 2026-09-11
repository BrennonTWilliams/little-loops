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

`RepoActivity.instrumented` is true whenever the history.db file exists (`aggregate_workspace_activity()`: non-ok branches set `instrumented = status is not MemberActivityStatus.DB_MISSING`; the count-failure and ok branches hardcode `True`). A schema'd-but-empty db and a db whose rows all fall outside the `--since/--until` window are indistinguishable: both report `instrumented: true` with zero counts. There is no field that answers "were any rows ever recorded".

## Expected Behavior

A separate `has_history` signal on `RepoActivity` distinguishes the two cases: `false` for empty-but-schema'd dbs, `true` when rows exist outside the window, `null` when the db cannot be read (schema_skew/unreadable), `false` for db_missing. `instrumented` keeps its current file-exists meaning and its load-bearing role in the workspace quality reader. `WorkspaceTotals` gains `has_history_members` (count) and `has_history` (any), mirroring the existing `instrumented`/`instrumented_members` pair.

## Motivation

**Verified in code** (`aggregate_workspace_activity()`):

- Non-ok branches: `instrumented=status is not MemberActivityStatus.DB_MISSING` (line 277).
- Count-failure branch: `instrumented=True` (line 291).
- Ok branch: `instrumented=True` (line 304).

So `instrumented` is true whenever the file exists. A downstream consumer (little-loops-hermes) must distinguish "empty db" (tables exist, zero rows ever) from "quiet window" (rows exist, none in window). It reports "measured zero activity" only for the latter; treating the former as measured-zero is exactly the "no answer ≠ zero" conflation its own code exists to prevent.

`instrumented` is load-bearing in the workspace quality reader and its tests, so it must keep its current meaning.

## Proposed Solution

Resolved — see "Decisions (resolved, do not re-derive)" for the field/value semantics and "Implementation Steps" for the landing order. In short: a new `_has_any_history(conn)` helper (EXISTS over `issue_events` OR `loop_runs`, no scan) feeds a new `RepoActivity.has_history: bool | None` in the ok path; `db_missing` → `False`, `schema_skew`/`unreadable` → `None`; `_totals()` mirrors with `has_history_members`/`has_history`; `to_dict()` on both dataclasses plus the text/markdown formatters expose it.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history/workspace_activity.py` — new `_has_any_history()` helper; `RepoActivity`, `WorkspaceTotals`, `_totals()`, `aggregate_workspace_activity()`, `to_dict()` ×2, `format_workspace_activity_text()` / `format_workspace_activity_markdown()`, module docstring.

### Dependent Files (Callers/Importers)
- `ll-history activity` CLI path (consumes `WorkspaceActivityResult.to_dict()` and the formatters) — additive keys only, no code change needed beyond formatters.
- little-loops-hermes (external consumer) — reads the JSON shape; gains the new keys.

### Similar Patterns
- `WorkspaceTotals.instrumented` / `instrumented_members` pair in the same module — `has_history`/`has_history_members` mirrors it exactly.
- `workspace_quality.py` gates dbs via the shared `_gate_member()`; `has_history` must NOT follow quality's ATTACH/union machinery — a plain per-member EXISTS suffices.

### Tests
- `scripts/tests/test_feat3445_workspace_activity.py` — extend with empty-db / rows-outside-window / loop-only / issue-only / db_missing / schema_skew / unreadable cases per AC.

### Documentation
- `docs/reference/API.md` (workspace_activity section)
- `docs/reference/CLI.md` (ll-history activity output shape)
- Module docstring in `workspace_activity.py`

### Configuration
- N/A

## Implementation Steps

1. Add `_has_any_history(conn) -> bool` next to `_count_member_activity` in `workspace_activity.py` using the EXISTS query.
2. Call it in the ok path (inside the existing `try`, so `sqlite3.Error` routes to `UNREADABLE`); set `has_history=False` in the `DB_MISSING` case and `None` for `SCHEMA_SKEW`/`UNREADABLE`.
3. Extend `_totals()` with `has_history_members` and `has_history`.
4. Update `to_dict()` on both dataclasses and the text/markdown formatters.
5. Update the module docstring and `docs/reference/API.md` (workspace_activity section) and `docs/reference/CLI.md` (ll-history activity output shape).
6. Tests (see AC).

## Impact

- **Priority**: P2 - additive signal needed by a real consumer (little-loops-hermes) to avoid reporting measured-zero on empty dbs; no data corruption or user-facing breakage without it.
- **Effort**: Small - one helper, three fields, two `to_dict()`s, two formatters, doc updates, focused tests in one existing test file.
- **Risk**: Low - purely additive; `instrumented` semantics untouched; FEAT-3446 stable-key-order contract preserved for existing keys (new keys appended after `instrumented`).
- **Breaking Change**: No - new dataclass fields default to `None`; JSON/YAML gain keys; consumers ignoring unknown keys are unaffected.

## Program Design

### Signatures
- **New helper** (placement: `workspace_activity.py`, adjacent to `_count_member_activity`):

  ```python
  def _has_any_history(conn: sqlite3.Connection) -> bool:
      ...
  ```

  Body: `SELECT EXISTS(SELECT 1 FROM issue_events) OR EXISTS(SELECT 1 FROM loop_runs)` — cheap index-probe per table, no scan, no window predicates.
- **New field** on `RepoActivity` (after `instrumented`):

  ```python
  has_history: bool | None = None
  ```

- **New fields** on `WorkspaceTotals` (after `instrumented`):

  ```python
  has_history_members: int
  has_history: bool
  ```

### Call Path
`aggregate_workspace_activity()` → `_gate_member()` → `_has_any_history(conn)` → `RepoActivity` → `_totals()` → `WorkspaceTotals` → `to_dict()` → `format_workspace_activity_text()` / `format_workspace_activity_markdown()`

`_has_any_history()` is called in the ok branch inside the existing `try:` whose `except sqlite3.Error` already routes to `MemberActivityStatus.UNREADABLE`, so a failing EXISTS needs no new error path — it lands in the existing branch and `has_history` reads as `None`.

### Decision Rules
- Never redefine `instrumented` — it is load-bearing in the workspace quality reader and its tests.
- `None` (not `False`) whenever the row count is unknowable (schema_skew/unreadable): asserting `False` would repeat the no-answer-≠-zero conflation this issue exists to fix.
- `db_missing` → `False` (a real answer: nothing was ever recorded).

## Scope Boundaries

- **Out of scope**: changing `instrumented` semantics; windowing `has_history` (it is deliberately any-rows-ever, irrespective of `--since/--until`); counting rows (only existence); changes to `workspace_quality.py` or its tests; new CLI flags on `ll-history activity`; hermes-side consumption logic (sibling ENH-3449 covers the opt-out env var for that consumer).
- **In scope**: the three new fields, the helper, serializer/formatter exposure, docs, and tests in `test_feat3445_workspace_activity.py`.

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
- `/ll:format-issue` - 2026-09-11T20:31:22 - `927fc9d3-cc55-46d9-9660-1cb2e288f9d7.jsonl`
- `/ll:capture-issue` - 2026-09-11T20:26:49 - `d2544764-cca3-4cd1-bd27-85b0d1d0f3c3.jsonl`
