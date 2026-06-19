---
id: ENH-2131
type: ENH
priority: P4
status: done
title: ll-logs stats JSON always-null errors/error_rate fields should be removed or
  implemented
discovered_date: 2026-06-14
discovered_by: capture-issue
captured_at: '2026-06-14T01:52:17Z'
completed_at: '2026-06-19T16:21:38Z'
parent: EPIC-1918
depends_on:
- ENH-2134
decision_needed: false
confidence_score: 95
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

> **Selected:** Option A — Remove the stubs — matches the existing `ctx_stats.py` 4-field clean schema exactly; 2-line deletion with no new infrastructure required.

**Option B — Implement via `scan-failures` data**: Populate `errors` by cross-referencing the JSONL-based failure counts from `_cmd_scan_failures` logic. Add `--sort errors` as a third sort option. Larger scope — create a separate ENH for the implementation and just remove the stubs here.

Recommend Option A now; open a follow-on ENH if error-rate data in stats becomes desired.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-19.

**Selected**: Option A — Remove the stubs

**Reasoning**: Option A directly mirrors the clean 4-field schema already used by `ctx_stats.py:354–368` and `_cmd_stats`'s sibling `dead-skills` JSON output (`logs.py:834–839`). Option B would require joining two separate data sources (SQLite `skill_events` vs JSONL scan-failures clusters) with no existing bridge utility — high complexity for a field that has never been populated. Zero production call sites read `errors` or `error_rate` from stats JSON output; the field is consumed only by the test that asserts it is always `None`.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Remove the stubs | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B — Implement via scan-failures | 1/3 | 0/3 | 1/3 | 1/3 | 3/12 |

**Key evidence**:
- Option A: `ctx_stats.py:354–368` emits identical 4-field schema (`skill`, `invocations`, `corrections`, `correction_rate`) with no null stubs — direct precedent. `dead-skills` at `logs.py:834–839` also emits only fields with real values. `grep` finds zero production call sites reading `errors` or `error_rate` from stats output.
- Option B: `_cmd_scan_failures` (`logs.py:922`) operates on JSONL session files keyed by `(cwd_path, tool_name, sig)` triple — entirely different data source from the SQLite `skill_events` table used by `_cmd_stats`. No existing bridge utility; new infrastructure required.

## Implementation Steps

1. In `scripts/little_loops/cli/logs.py` `_cmd_stats` JSON path: delete `"errors": None,` (line 1181) and `"error_rate": None,` (line 1182) from the `rows_json` list comprehension.
2. In `scripts/little_loops/cli/logs.py` `_cmd_stats` tabular path: remove `"Errors"` from the `headers` list (line 1189) and the trailing `"N/A"` value from each `rows.append(...)` call (line 1195).
3. In `scripts/tests/test_ll_logs.py` `test_stats_json_keys` (lines 1561–1593): update the docstring; remove `"errors"` and `"error_rate"` from the `set(row.keys())` assert; delete the `assert row["errors"] is None` and `assert row["error_rate"] is None` lines. Target schema: `{"skill", "invocations", "corrections", "correction_rate"}`.
4. In `docs/reference/API.md` line 3567: update the JSON schema from `[{skill: str, invocations: int, corrections: int, correction_rate: float, errors: null, error_rate: null}]` to `[{skill: str, invocations: int, corrections: int, correction_rate: float}]`.
5. In `docs/reference/CLI.md` line 1908: optionally expand `--json` description to enumerate the 4 real fields inline (following the `dead-skills` pattern at line 1918).
6. Run `python -m pytest scripts/tests/test_ll_logs.py -k "TestStats" -v` to verify.

## Scope Boundaries

- **In scope**: Remove `"errors": None, "error_rate": None` from `_cmd_stats`; update `test_stats_json_keys`; update `docs/reference/CLI.md` if schema is documented
- **Out of scope**: Implementing error-rate data sourcing — open a separate ENH if that becomes desired

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — `_cmd_stats`; remove `"errors": None` (line 1181) and `"error_rate": None` (line 1182) from the `rows_json` list comprehension; also remove `"Errors"` from the `headers` list (line 1189) and the trailing `"N/A"` from each `rows.append(...)` call (line 1195) to clean up the tabular output path as well
- `scripts/tests/test_ll_logs.py` — `test_stats_json_keys` (lines 1561–1593); update docstring (line 1562), remove `"errors"` and `"error_rate"` from the `set(row.keys())` assertion (lines 1584–1591), and delete the two trailing `assert row["errors"] is None` / `assert row["error_rate"] is None` lines (1592–1593)
- `docs/reference/API.md` — line 3567 explicitly documents the JSON schema as `[{skill: str, invocations: int, corrections: int, correction_rate: float, errors: null, error_rate: null}]`; update to `[{skill: str, invocations: int, corrections: int, correction_rate: float}]`
- `docs/reference/CLI.md` — `--json` flag for `stats` subcommand (line 1908) is described only as `Output as JSON array` with no schema block; no existing schema to remove, but optionally expand description to enumerate the 4 real fields

### Dependent Files (Callers/Importers)
- N/A — `stats` output is a terminal CLI subcommand; no code-level callers within the project

### Similar Patterns
- `scripts/little_loops/cli/ctx_stats.py:352` — `ll-ctx-stats` uses the identical 4-field clean schema (`skill`, `invocations`, `corrections`, `correction_rate`) with no null stubs — model the post-removal `_cmd_stats` output after this shape
- `scripts/little_loops/cli/logs.py:834` — `dead-skills` JSON output only emits fields with real values (`skill`, `invocations`, `tier`); documented in `docs/reference/CLI.md:1918` as the canonical inline-schema pattern to follow

### Tests
- `scripts/tests/test_ll_logs.py` — update `test_stats_json_keys` (currently asserts `row["errors"] is None`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli.py` — `test_stats_returns_0` (line 2950) invokes `ll-logs stats --all`; confirmed unaffected (exit-code assertion only, no field-level assertions)
- `scripts/tests/test_ll_logs.py` — `test_stats_counts_invocations` (line 1510) invokes tabular `stats` output; confirmed unaffected (checks skill names in output, not column headers or N/A values)

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
- `/ll:ready-issue` - 2026-06-19T16:18:11 - `0555ba31-d2c0-40ab-a555-41c0c58df250.jsonl`
- `/ll:wire-issue` - 2026-06-19T15:58:00 - `52d179dc-327a-402f-b457-71236c58536b.jsonl`
- `/ll:decide-issue` - 2026-06-19T15:49:32 - `9dc761a6-9b86-4ce1-ad31-5b60a51c47f0.jsonl`
- `/ll:refine-issue` - 2026-06-19T15:44:36 - `6dc69311-412d-4357-b182-a3cfd89f91c9.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T15:18:48 - `1a9c4417-3e84-4834-8a7a-2109919401cc.jsonl`
- `/ll:format-issue` - 2026-06-14T01:58:55 - `d9bff7da-ceab-4140-99fa-ea076f1863f3.jsonl`
- `/ll:capture-issue` - 2026-06-14T01:52:17Z - `audit-session`
- `/ll:format-issue` - 2026-06-14T00:00:00Z - `auto`
