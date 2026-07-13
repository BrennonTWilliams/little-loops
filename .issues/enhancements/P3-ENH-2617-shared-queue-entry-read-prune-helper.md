---
id: ENH-2617
type: ENH
priority: P3
status: done
captured_at: 2026-07-12 19:49:49+00:00
completed_at: '2026-07-13T17:41:33Z'
discovered_date: 2026-07-12
discovered_by: scope-epic
parent: EPIC-2616
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# Shared queue entry read/prune helper

## Summary

Extract a shared helper for reading `.loops/.queue/*.json` entries with
dead-PID pruning, so `ll-loop queue list`/`ll-loop queue remove` and the
existing `_is_earliest_waiter()` (`scripts/little_loops/cli/loop/_helpers.py:172`)
share one implementation of "what's actually in the queue right now."

## Current Behavior

The queue entry-loading logic (glob `*.json`, parse, dead-PID prune via
`_process_alive()`, sort by `enqueuedAt`) lives inline inside
`_is_earliest_waiter()` in `scripts/little_loops/cli/loop/_helpers.py`. It is the
only implementation of "what's actually in the queue right now," and it is not
callable independently.

## Expected Behavior

A standalone, reusable `read_queue_entries(queue_dir: Path) -> list[dict]`
returns the live, sorted queue entries (pruning dead-PID files as a side effect).
`_is_earliest_waiter()` calls it instead of duplicating the loop, and the sibling
`ll-loop queue list`/`ll-loop queue remove` commands (FEAT-2618/FEAT-2619) can
consume the same view.

## Current Pain Point

The upcoming `queue list`/`queue remove` commands would each re-implement the
same load-and-prune loop, risking behavioral drift (e.g. inconsistent dead-PID
pruning, BUG-1360). There is no single source of truth for reading the queue.

## Scope Boundaries

In scope: a behavior-preserving extraction of the existing inline loop into a
module-level helper plus direct unit tests. Out of scope: any new argparse
surface, the `queue list`/`queue remove` commands themselves (FEAT-2618/2619),
docs updates (ENH-2620), and any change to the queue entry schema.

## Impact

Prep step that unblocks FEAT-2618/FEAT-2619 with a shared, tested helper. Pure
refactor — no user-visible behavior change; existing `_is_earliest_waiter()`
semantics are preserved.

## Status

done

## Implementation

Factor the entry-loading loop currently inline in `_is_earliest_waiter()`
(glob `*.json`, parse, check `context.pid` liveness via `_process_alive()`,
`f.unlink(missing_ok=True)` on dead PIDs, sort by `enqueuedAt`) into a
standalone function, e.g. `read_queue_entries(queue_dir: Path) -> list[dict]`,
that returns the live, sorted entries and prunes dead ones as a side effect.
Update `_is_earliest_waiter()` to call it instead of duplicating the loop.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — the entry-loading loop lives inline in
  `_is_earliest_waiter()` (lines 184–199). Extract it into a new module-level
  `read_queue_entries(queue_dir: Path) -> list[dict]` and have `_is_earliest_waiter()` call it.
  The helper already imports `json`, `Path`, and `_process_alive` (line 25), so no new imports
  are needed.

### New Helper Contract
`read_queue_entries(queue_dir)` should encapsulate the current inline behavior verbatim:
- Return `[]` (or handle absence) when `queue_dir` does not exist — note `_is_earliest_waiter()`
  currently short-circuits to `return True` at line 182 *before* the loop, so the helper must
  own the `not queue_dir.exists()` guard (return `[]`) to stay a faithful extraction.
- `glob("*.json")`, `json.load` each, read `data.get("context", {}).get("pid")`.
- If `pid is not None and not _process_alive(pid)`: `f.unlink(missing_ok=True)` and skip (dead-PID
  prune side effect — BUG-1360).
- Swallow `(json.JSONDecodeError, KeyError, FileNotFoundError, OSError)` per-file and continue.
- Sort surviving entries by `d.get("enqueuedAt", "")` and return them.

After extraction, `_is_earliest_waiter()` reduces to:
`entries = read_queue_entries(queue_dir); return not entries or entries[0].get("id") == entry_id`.

### Callers / Consumers
- `_is_earliest_waiter()` — sole current caller of the inline loop; called from
  `scripts/little_loops/cli/loop/run.py:389` in the wait-retry loop.
- `ll-loop queue list` / `ll-loop queue remove` (the sibling EPIC-2616 work) are the intended
  future consumers — they need the same "live, sorted entries" view, which is the motivation
  for the extraction.

_Wiring pass added by `/ll:wire-issue`:_
- The sibling consumers now have concrete issue IDs: `FEAT-2618` (`ll-loop queue list`),
  `FEAT-2619` (`ll-loop queue remove <id>`), and `ENH-2620` (docs). No `queue.py`/`queue_cmds.py`
  module exists in `scripts/little_loops/cli/loop/` yet, and `main_loop()` in
  `scripts/little_loops/cli/loop/__init__.py` registers no `queue` subparser — this extraction is
  purely a prep step; it wires no new argparse surface itself. [Agent 1 + Agent 2 finding]
- `_process_alive` is sourced from `scripts/little_loops/fsm/concurrency.py:56` (imported at
  `_helpers.py:25`); the extracted helper keeps that same import, no change needed. [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — the `##### Queue entries (`.loops/.queue/`)` section (line 643)
  documents the entry schema and notes that "cleanup tooling may want to prune entries whose
  `pid` is no longer alive" (the doc-level home for the BUG-1360 prune behavior this helper
  centralizes). **Advisory only** — the entry shape is unchanged by this pure extraction, so no
  edit is required here; the note lands with `ENH-2620` when `queue list`/`remove` ship. [Agent 2 finding]

### Queue Entry Schema (written at `run.py:358–367`)
Entries are `{id, loopName, enqueuedAt (ISO-8601 UTC), context:{waitingFor, scope, pid}}`,
written to `queue_dir / f"{entry_id}.json"` where `queue_dir = loops_dir / ".queue"`
(`run.py:355`).

### Tests
- `scripts/tests/test_cli_loop_queue.py` — existing queue tests; add a `read_queue_entries` case
  covering: dead-PID pruning (file unlinked), malformed JSON skipped, missing dir → `[]`,
  and `enqueuedAt` sort order.

_Wiring pass added by `/ll:wire-issue`:_
- **New tests, not edits.** The existing `TestQueueFifoOrdering` (lines 163–257) is black-box
  against `_is_earliest_waiter()`'s public return value + unlink side effect, not its loop
  internals — since the extraction is behavior-preserving, all 5 existing tests
  (`test_is_earliest_when_queue_dir_missing`, `..._is_empty`, `test_earliest_entry_wins`,
  `test_stale_entries_from_dead_pids_are_skipped`, `test_malformed_entries_are_skipped`) pass
  unchanged. Add a parallel `TestReadQueueEntries` class alongside it. [Agent 3 finding]
- **Pattern to mirror:** copy the structure of `test_stale_entries_from_dead_pids_are_skipped`
  (lines 202–239, `pid: 99999999` guaranteed-dead convention + `assert not stale_file.exists()`)
  for the prune case, `test_malformed_entries_are_skipped` (lines 241–257) for the `bad.json`
  case, and adapt `test_earliest_entry_wins` (lines 180–200) to assert list order
  (`entries[0]["id"] == ...`) instead of a boolean. Precedent for a zero-new-test behavior-preserving
  extraction is `ENH-537` (`_process_alive` extraction); this issue deliberately diverges by adding
  direct coverage for the new module-level helper. [Agent 3 finding]
- `TestQueueRetryOnRace` (lines 59–160) and the `run.py:389` wait-retry loop mock `LockManager`
  and never write real queue files, so they exercise `_is_earliest_waiter`/`read_queue_entries`
  only trivially (empty queue → `True`); no integration test change needed. [Agent 3 finding]

## Session Log
- `/ll:scope-epic` - 2026-07-12T19:49:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8999ce06-5d43-4dd5-bc03-841f57c28bf2.jsonl`
- `/ll:refine-issue` - 2026-07-13T12:30:48 - `session JSONL unavailable`
- `/ll:wire-issue` - 2026-07-13T12:37:00 - `session JSONL unavailable`
- `/ll:ready-issue` - 2026-07-13T12:40:00 - `session JSONL unavailable`
