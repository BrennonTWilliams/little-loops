---
id: ENH-2131
type: ENH
priority: P4
status: open
title: ll-logs stats JSON always-null errors/error_rate fields should be removed or implemented
discovered_date: 2026-06-14
discovered_by: capture-issue
captured_at: "2026-06-14T01:52:17Z"
parent: EPIC-1918
depends_on: [ENH-2134]
---

# ENH-2131: ll-logs stats JSON always-null errors/error_rate fields should be removed or implemented

## Summary

`_cmd_stats` JSON output (lines 1187-1188 of `cli/logs.py`) always emits:

```json
"errors": null,
"error_rate": null
```

No code path ever populates these fields. `test_stats_json_keys` validates `row["errors"] is None` — confirming the stub is tested as a stub, not as a feature. The `--sort` option does not support `--sort errors` either.

Consumers parsing the JSON stats output cannot rely on these fields for anything. Their presence implies future functionality that has never landed.

## Current Behavior

`_cmd_stats` JSON output always emits `"errors": null` and `"error_rate": null`. No code path populates these fields; `test_stats_json_keys` asserts they remain `None`, confirming they are stubs with no implementation.

## Expected Behavior

The `stats` JSON output omits `errors` and `error_rate` entirely (Option A — remove stubs). The resulting JSON schema has no null stubs, giving consumers a clean, reliable API surface.

## Motivation

A clean API surface: either remove the fields to eliminate consumer confusion, or implement them (sourcing error data from `scan-failures` clusters or a dedicated `error_events` DB table) and add a corresponding `--sort errors` option.

## Proposed Solution

**Option A — Remove the stubs**: Delete `"errors": None, "error_rate": None` from the JSON output dict. Update `test_stats_json_keys` accordingly. Clean, immediate.

**Option B — Implement via `scan-failures` data**: Populate `errors` by cross-referencing the JSONL-based failure counts from `_cmd_scan_failures` logic. Add `--sort errors` as a third sort option. Larger scope — create a separate ENH for the implementation and just remove the stubs here.

Recommend Option A now; open a follow-on ENH if error-rate data in stats becomes desired.

## Implementation Steps

1. In `_cmd_stats` (around line 1177), remove `"errors": None, "error_rate": None` from the `rows_json` list comprehension.
2. Update `test_stats_json_keys` to not assert on those keys.
3. Update `docs/reference/CLI.md` if the JSON schema is documented there.

## Scope Boundaries

- **In scope**: Remove `"errors": None, "error_rate": None` from `_cmd_stats`; update `test_stats_json_keys`; update `docs/reference/CLI.md` if schema is documented
- **Out of scope**: Implementing error-rate data sourcing — open a separate ENH if that becomes desired

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — `_cmd_stats` around line 1177; remove two null fields from `rows_json` list comprehension
- `scripts/tests/test_ll_logs.py` — `test_stats_json_keys`; remove assertions on `errors`/`error_rate` keys
- `docs/reference/CLI.md` — if JSON schema is documented there, remove the two fields from the schema

### Dependent Files (Callers/Importers)
- N/A — `stats` output is a terminal CLI subcommand; no code-level callers within the project

### Similar Patterns
- N/A — no other subcommands use stub null fields

### Tests
- `scripts/tests/test_ll_logs.py` — update `test_stats_json_keys` (currently asserts `row["errors"] is None`)

### Documentation
- `docs/reference/CLI.md` — verify and update if JSON schema is documented there

### Configuration
- N/A

## Impact

- **Priority**: P4 — cosmetic API cleanup; no functional regression risk
- **Effort**: Small — two-line deletion in one file, one test update, one optional doc edit
- **Risk**: Low — consumers cannot rely on always-null fields; tests confirm null-only behavior
- **Breaking Change**: Technically yes — removes two JSON keys. In practice, zero-impact since keys are always `null`.

## Labels

`code-cleanup`, `ll-logs`

## Verification Notes

2026-06-18 (ACCURATE): Lines 1187-1188 of `cli/logs.py` confirmed: `"errors": None, "error_rate": None` still emitted by `_cmd_stats`. No code path populates these fields. `test_stats_json_keys` validates null behavior. Option A (remove stubs) not yet applied.

## Status

**Open** | Created: 2026-06-14 | Priority: P4

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-18T15:18:48 - `1a9c4417-3e84-4834-8a7a-2109919401cc.jsonl`
- `/ll:format-issue` - 2026-06-14T01:58:55 - `d9bff7da-ceab-4140-99fa-ea076f1863f3.jsonl`
- `/ll:capture-issue` - 2026-06-14T01:52:17Z - `audit-session`
- `/ll:format-issue` - 2026-06-14T00:00:00Z - `auto`
