---
id: ENH-2134
type: ENH
priority: P5
status: open
title: ll-logs minor code cleanup bundle (double import, readlines vs streaming, Path wrap)
discovered_date: 2026-06-14
discovered_by: capture-issue
captured_at: "2026-06-14T01:52:17Z"
parent: EPIC-1918
decision_needed: false
---

# ENH-2134: ll-logs minor code cleanup bundle (double import, readlines vs streaming, Path wrap)

## Summary

Three trivial inconsistencies found during the 2026-06-14 audit of `scripts/little_loops/cli/logs.py`:

### 1. Double import of `resolve_history_db` in `_cmd_eval_export`

`resolve_history_db` is imported at module level (line 24):
```python
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context, resolve_history_db
```
And again locally inside `_cmd_eval_export` (line 1590):
```python
from little_loops.session_store import resolve_history_db
```
The local import is redundant.

### 2. `_cmd_scan_failures` uses `readlines()` while all other subcommands stream

Line 957: `lines = f.readlines()` — loads the entire JSONL file into memory. All other subcommands use line-by-line iteration (`for line in f:`). The stateful `pending` dict (lines 961–1043) works equally well with streaming iteration. This is a memory consistency issue, not a correctness issue.

### 3. `_cmd_stats` double-wraps `args.project` in `Path()`

Line 1147: `Path(args.project)` — `args.project` is declared `type=Path` in `stats_parser` (line 1783), so `args.project` is already a `Path` object. `_cmd_sequences` (line 480) and `_cmd_extract` (line 583) use the typed value directly.

## Current Behavior

`scripts/little_loops/cli/logs.py` contains three minor inconsistencies:

1. `resolve_history_db` is imported twice — once at module level and again as a local import inside `_cmd_eval_export`.
2. `_cmd_scan_failures` loads entire JSONL files into memory with `f.readlines()`, inconsistent with all other subcommands that use `for line in f:` streaming.
3. `_cmd_stats` wraps `args.project` in an extra `Path()` call even though `args.project` is already typed as `Path` in `stats_parser`.

## Expected Behavior

- `_cmd_eval_export` uses only the module-level `resolve_history_db` import; the redundant local re-import is removed.
- `_cmd_scan_failures` iterates with `for line in f:`, consistent with all other subcommands; no full-file load into memory.
- `_cmd_stats` uses `args.project` directly without an additional `Path()` wrap, matching `_cmd_sequences` and `_cmd_extract`.

## Scope Boundaries

- **In scope**: The three specific one-line cleanup items in `scripts/little_loops/cli/logs.py` (`_cmd_eval_export` import, `_cmd_scan_failures` readlines, `_cmd_stats` Path wrap).
- **Out of scope**: Any behavioral changes, new features, test additions (no logic changes — existing tests pass as-is), or broader refactors of `logs.py`.

## Implementation Steps

1. **`_cmd_eval_export` (line 1559)**: Remove `from little_loops.session_store import resolve_history_db` — the module-level import at line 24 is already in scope.
2. **`_cmd_scan_failures` (lines 972–980)**: Remove `lines = f.readlines()` (line 973) and change `for line in lines:` (line 980) to `for line in f:` — the `pending` dict (line 978) and all loop body variables are compatible with streaming; no other changes needed.
3. **`_cmd_stats` (line 1160)**: Change `Path(args.project)` to `args.project` — `stats_parser` declares `--project` as `type=Path` (line 1753), so the value is already a `Path`.

No test changes needed — these are all non-behavioral cleanup items.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` (functions: `_cmd_eval_export`, `_cmd_scan_failures`, `_cmd_stats`)

### Dependent Files (Callers/Importers)
- N/A — changes are internal to `logs.py`; no callers are affected

### Similar Patterns
- `_cmd_sequences` (line ~480) and `_cmd_extract` (line ~583) — already use `args.project` directly and `for line in f:` streaming; these are the reference patterns

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified 2026-06-19 against current code:_

**Corrected exact line numbers (shifted since original capture):**

| Item | Issue states | Actual line |
|------|-------------|-------------|
| `resolve_history_db` local re-import (`_cmd_eval_export`) | 1590 | **1559** |
| `f.readlines()` in `_cmd_scan_failures` | 957 | **973** |
| `Path(args.project)` double-wrap in `_cmd_stats` | 1147 | **1160** |

**Canonical streaming pattern (reference):**
- `scripts/little_loops/cli/logs.py:495` — `_cmd_sequences`: `cwd_path: Path = args.project` (no wrap), feeds directly into `get_project_folder()`
- `scripts/little_loops/cli/logs.py:980` — current scan_failures loop is `for line in lines:` — rename `lines` variable to `f` when converting: remove `lines = f.readlines()` (line 973) and change `for line in lines:` (line 980) to `for line in f:` inside the same `with open(...)` block

**`pending` dict streaming compatibility confirmed:** `pending` dict (line 978) is scoped per `jsonl_file` iteration; both inserts and pops (`pending.pop(tool_use_id)`, line 1028) are within the same sequential line-scan. Streaming `for line in f:` is fully compatible — no ordering dependency on the full list.

**`stats_parser` `--project` typed as `Path`** (line 1753): `type=Path` confirmed, making `Path(args.project)` at line 1160 a redundant no-op wrap.

**Module-level `resolve_history_db`** is actively used at line 1342 (`_cmd_diff`) — removing the local re-import at line 1559 leaves the module-level import intact and sufficient.

### Tests
- `scripts/tests/test_ll_logs.py` — existing test suite; no tests specifically for `_cmd_eval_export`, `_cmd_scan_failures`, or `_cmd_stats`; non-behavioral changes do not require new tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_logs.py` — contrary to the note above, `test_ll_logs.py` contains `class TestScanFailures` (17 tests, lines 1982–2592), `class TestStats` (14 tests, lines 1435–1742), and `class TestEvalExport`/`TestEvalExportRoundTrip` (8 tests, lines 2877+) that exercise these exact subcommands. All tests pass unchanged — the changes are non-behavioral and produce identical output.
- `scripts/tests/test_cli.py` — smoke tests `test_stats_returns_0` (line 2950) and `test_scan_failures_returns_0` (line 2965) invoke `main_logs()` end-to-end; both pass unchanged. [Agent 1 + Agent 3 finding]

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P5 - Trivial cleanup; no functional impact, can be deferred or batched with other minor cleanups.
- **Effort**: Small - Three one-line changes in a single file; no logic changes required.
- **Risk**: Low - Non-behavioral cleanup in internal helper functions; no public API or interface changes.
- **Breaking Change**: No

## Labels

`enhancement`, `code-quality`, `cleanup`

## Verification Notes

2026-06-18 (ACCURATE): All three items confirmed unfixed. (1) Line 1590: `from little_loops.session_store import resolve_history_db` redundant local re-import still present alongside module-level import at line 24. (2) Line 957: `lines = f.readlines()` in `_cmd_scan_failures` still loads full JSONL into memory. (3) Line 1147: `Path(args.project)` double-wrap in `_cmd_stats` still present.

## Status

**Open** | Created: 2026-06-14 | Priority: P5

## Session Log
- `/ll:wire-issue` - 2026-06-19T19:47:21 - `1ab8d550-7f64-413a-91f7-000380d1fda3.jsonl`
- `/ll:refine-issue` - 2026-06-19T19:40:32 - `97db09a4-8f95-4735-af2a-f8a1ba636df4.jsonl`
- `/ll:format-issue` - 2026-06-14T01:58:59 - `177b54d4-d59e-4c5f-b2ab-5b0d7849573b.jsonl`
- `/ll:capture-issue` - 2026-06-14T01:52:17Z - `audit-session`
