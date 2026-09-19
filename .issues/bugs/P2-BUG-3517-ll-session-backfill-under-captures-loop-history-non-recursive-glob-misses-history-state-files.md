---
id: BUG-3517
type: BUG
title: 'll-session backfill under-captures loop history: non-recursive glob misses
  .history state files'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T22:27:37Z'
labels:
- session-store
- backfill
---

# BUG-3517: ll-session backfill under-captures loop history: non-recursive glob misses .history state files

## Summary

`ll-session backfill` silently under-captures loop history. `_backfill_loops` (session_store/writers.py) reads FSM state with a non-recursive `glob("*.json")`, so it catches the currently-running loops in `.loops/.running/*.state.json` but misses the completed runs stored as `.loops/.history/<run>/state.json` — roughly 92% of loop history is skipped.

## Current Behavior

`_backfill_loops` iterates `directory.glob("*.json")` over `.loops/.running` and `.loops/.history`:

- `.loops/.running/*.state.json` → caught (112 files on the little-loops repo).
- `.loops/.history/*/state.json` → missed: each completed run is a per-run subdirectory (`<timestamp>-<loop-name>/state.json`), and the non-recursive glob never descends into them.

Two secondary gaps compound it: it stores only `(loop_name, current_state, ts)` with `transition="backfill"` hardcoded, discarding the `captured` dict (per-state `output`/`exit_code`/`duration_ms`); and it uses a plain `INSERT` with no dedup, so re-running duplicates rows.

## Expected Behavior

`_backfill_loops` should capture every loop run — running and completed — and persist the full state sequence plus `captured` outputs (not just `current_state`), deduped on `(loop_name, ts)` so the backfill is idempotent.

## Impact

- **Priority**: P2 - Silent data loss: ~92% of loop history never reaches `loop_events`, skewing any loop analytics built on it
- **Effort**: Small - One function (`_backfill_loops`) plus a dedup index/check
- **Risk**: Low - Backfill-only path; `INSERT OR IGNORE` keeps re-runs idempotent
- **Breaking Change**: No

## Steps to Reproduce

1. On a repo with completed loop history, run `ll-session backfill`.
2. Compare `SELECT COUNT(*) FROM loop_events` against the number of state files under `.loops/.running/*.state.json` plus `.loops/.history/*/state.json`.
3. Observe that only `.running` state is ingested; `.history` subdirectories are skipped.

## Root Cause

`directory.glob("*.json")` is non-recursive, but completed runs live one directory deeper under `.loops/.history/<run>/state.json`.

## Proposed Solution

1. Replace the flat `glob("*.json")` with a recursive walk — e.g. `loops_dir.rglob("state.json")`, or iterate `.history/*/state.json` explicitly alongside `.running/*.state.json`.
2. Extract the full state: `current_state`, the `captured` dict, and `iteration`.
3. Dedupe on `(loop_name, ts)` (or the state-file path) — e.g. a UNIQUE index + `INSERT OR IGNORE`, or a pre-existence check.
4. Re-run `ll-session backfill` to ingest the completed runs.

## Program Design

### Types

- `state_file: Path` — a `.running/*.state.json` or `.history/<run>/state.json` file
- `data["captured"]: dict[str, dict]` — per-state `output`/`exit_code`/`duration_ms`

### Signatures

- `_backfill_loops(conn: sqlite3.Connection, loops_dir: Path) -> int` — walks both dirs, `INSERT OR IGNORE`, returns rows inserted
- `_iter_loop_state_files(loops_dir: Path) -> Iterator[Path]` — yields `.running/*.state.json` then `.history/*/state.json`

### Call Path

`backfill` (session_store/lifecycle.py) -> `_backfill_loops` -> `_iter_loop_state_files` -> `_index`

## Status

**Open** | Created: 2026-09-19 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-09-19T23:02:59 - `f7716757-cc12-4f9f-9358-3ee432f01464.jsonl`
