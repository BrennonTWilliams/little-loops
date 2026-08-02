---
id: 3006
title: Phantom BUG-025 row in issue_events can block ENH-025 from recording completion
type: BUG
priority: P1
status: open
discovered_date: 2026-08-02
labels:
- observability
- history-db
- data-integrity
---

# Phantom BUG-025 row in issue_events can block ENH-025 from recording completion

## Summary

`issue_events` in `.ll/history.db` holds a row for `BUG-025`. No file named `BUG-025` exists anywhere in `.issues/` — only `ENH-025` (currently open). Because `idx_issue_events_dedup` is unique on `(issue_num, transition)` and the unique key is the bare numeric portion (not the full type-prefixed ID), this phantom row would silently block `ENH-025` from ever recording its own completion transition once the two collide on the same numeric key.

## Current Behavior

`idx_issue_events_dedup` is unique on `(issue_num, transition)`. The phantom `BUG-025` row silently blocks `ENH-025` from ever recording its own completion transition once the two collide on the same numeric key (25). No exception is raised, no log line is emitted; the `INSERT OR IGNORE` semantics of every writer silently no-op on the unique-index collision. `ll-issues set-status` additionally wraps its event-recording block in a blanket `except Exception: pass`, so this class of bug produces zero diagnostic signal today.

## Expected Behavior

No phantom rows exist in `issue_events` for files that were never created, and the dedup key does not let one issue type's history block another's. The `canonicalize_issue_id()` ingestion helper rejects (with a logged warning) any frontmatter `id:` whose type prefix does not match the file's filename-derived type, so the root cause is closed at the writer boundary rather than masked by widening the dedup index.

## Steps to Reproduce

1. `sqlite3 .ll/history.db "SELECT issue_id, issue_num, transition FROM issue_events WHERE issue_num=25"`
2. Observe: a row exists for `BUG-025`, transition `done` — but no `BUG-025` file exists anywhere in `.issues/`, only `ENH-025` (currently open).
3. When `ENH-025` eventually transitions to `done` and calls `record_issue_event()`, the `INSERT OR IGNORE` against `idx_issue_events_dedup (issue_num, transition)` silently no-ops on the existing `(25, 'done')` row, so `ENH-025`'s own completion is never recorded — with no exception or log.

## Root Cause

### 1. Schema/index shape

`idx_issue_events_dedup` is currently `UNIQUE INDEX ... ON issue_events(issue_num, transition) WHERE issue_num IS NOT NULL`, created by migration v36 (`scripts/little_loops/session_store/schema.py:823-905`, tracked as `ENH-2771`, `SCHEMA_VERSION = 37` → `38` after `ENH-2866` → `39` after this fix). v36 replaced the original `(issue_id, transition)` index (v3, `schema.py:176-181`) specifically to stop a *different* collision: the same issue's history splitting across rows when it gets **retyped** (e.g. ENH→FEAT), which used to alias on the old string key. `ENH-2771`'s own collision table (7 known cases) does not include issue `25` — this phantom row predates or is unrelated to that migration's known cases.

### 2. Numeric key derivation

`normalize_issue_id()` (`scripts/little_loops/session_store/writers.py:132-159`) strips the `TYPE-` prefix via `_ISSUE_NUM_RE = re.compile(r"(?:BUG|ENH|FEAT|EPIC)-(\d+)")` and returns the bare int — this is what makes `BUG-025` and `ENH-025` collide once both are 25.

### 3. Plausible creation mechanism

There is no code path that derives `issue_id` purely from a bare number. `issue_id` always goes through `canonicalize_issue_id()` (`writers.py:2005-2054`), which trusts a frontmatter `id:` field verbatim once it already matches `TYPE-NNN` shape, **without** cross-checking it against the file's actual filename-derived type. So a stray/typo'd frontmatter `id: BUG-025` on what is actually `ENH-025-*.md` produces exactly this phantom row, at either backfill (`_backfill_issues_and_snapshots()`, `writers.py:2135+`) or live-write time (`SQLiteTransport.send()`, `writers.py:1867-1947`).

### 4. Silent-swallow confirmation

All five `INSERT OR IGNORE` sites share silent-on-collision semantics: `record_issue_event` (`writers.py:380`), `record_issue_snapshot` (`writers.py:331`), `SQLiteTransport.send()` `issue.*` branch (`writers.py:1878`), `_backfill_snapshots` (`writers.py:2080`), `_backfill_issues_and_snapshots` (`writers.py:2135+`, `:2173`). The `set_status` CLI additionally wraps `record_issue_event()` in a blanket `except Exception: pass` (`cli/issues/set_status.py:127-156`).

## Proposed Solution — Option B (selected)

**Option A** (widen `idx_issue_events_dedup` back to a composite key that includes issue type, e.g. `(issue_type, issue_num, transition)`): directly prevents BUG-NNN/ENH-NNN aliasing, but reintroduces the exact collision `ENH-2771`/migration v36 was written to fix — an issue that changes type (ENH→FEAT, etc.) would again split its event history across two rows instead of deduping to one. `issue_type` is also NULL in ~1.6–3% of existing rows at 3 of 4 write sites, so a type-inclusive key lacks a reliable source.

**Option B** (leave the index on `(issue_num, transition)`; instead tighten `canonicalize_issue_id()` to reject/warn when a frontmatter `id:` field's type prefix doesn't match the file's filename-derived type): preserves `ENH-2771`'s retype-collision fix and stops future phantom rows of this specific shape without reopening the older bug. **Selected** by `/ll:decide-issue` on 2026-07-30.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (widen index) | 0/3 | 1/3 | 1/3 | 0/3 | 2/12 |
| Option B (fix canonicalize_issue_id) | 2/3 | 2/3 | 2/3 | 2/3 | 8/12 |

The one-time `DELETE` repair of the existing phantom row is also required (mirror the v36 migration shape, `schema.py:823-905`).

## Implementation Plan

All file paths are in `scripts/little_loops/session_store/` and `scripts/little_loops/issue_history/` unless otherwise noted. Steps assume Option B and the one-time DELETE repair. Order matters: backfill/repair before any index change, call-site guards before the writer guard.

### Step 1 — One-time DELETE repair in a v39 migration entry

Append a new `_MIGRATIONS` entry to `scripts/little_loops/session_store/schema.py` after the v38 ENH-2866 entry (`schema.py:918-934`). `_apply_migrations()` uses `len(_MIGRATIONS)` as source-of-truth (`schema.py:1002`); appending the entry automatically bumps `SCHEMA_VERSION` to 39. Keep `SCHEMA_VERSION = 39` in sync at line 21 (per convention).

- `DELETE FROM issue_events WHERE issue_id = 'BUG-025' AND issue_num = 25;`
- Skip if the hub-side one-time repair has already landed (per ENH-107-style data-repair pattern); only repeat as belt-and-braces if the implementer wants a second guard.
- `_split_sql_statements()` (`schema.py:957`) splits on `;` boundaries — keep the migration script free of `;` inside string literals or column definitions.

### Step 2 — Tighten `canonicalize_issue_id()`'s canonical-shape branch

In `scripts/little_loops/session_store/writers.py:2005-2054` (the `canonicalize_issue_id()` function):

- Before returning the uppercased `canonical`, compare `canonical` against the filename-derived `_FILENAME_TYPE_RE` match (`writers.py:1998`) — if both `raw_str` already matches `_CANONICAL_ISSUE_ID_RE` (`writers.py:2002`) *and* the filename has a `TYPE-NNN` shape, and the two type prefixes disagree, return `None` and `logger.warning(...)` (mirroring the existing warn-and-repair convention at lines `2033` and `2048-2053`).
- Mirror `check_format_gaps()`'s `malformed_id` branch (`issue_parser.py:492-499`) for the comparison logic and `FormatGaps.malformed_id` field (`issue_parser.py:248`) for the warning wording.
- Update the stale docstring at `writers.py:371-373` to describe the index as `(issue_num, transition)` (post-v36 reality). **Bundle** with the two companion stale-docstring sites: `scripts/little_loops/session_store/lifecycle.py:987` (`backfill_snapshots` docstring) and `scripts/little_loops/issue_history/rework.py:45`; also the test-side comment at `scripts/tests/test_issue_history_rework.py:42`.

### Step 3 — Remove the two `... or <raw>` fallbacks

The `... or <raw>` fallback is exactly two call sites — both must be removed so a `canonicalize_issue_id()` rejection isn't silently neutralized:

- `writers.py:310` — `record_issue_snapshot()` — change `canonicalize_issue_id(issue_id, file_path) or issue_id` to call without the `or` fallback; let `record_issue_snapshot()` log a warning and return `False` when canonicalization fails.
- `writers.py:1905-1907` — `SQLiteTransport.send()` `issue.*` branch — change `canonicalize_issue_id(event.get("issue_id"), _id_source_path) or event.get("issue_id")` similarly; if `issue_id` ends up `None`, drop the event with a `logger.warning(...)` rather than substituting the raw id.

The `*_backfill_*` paths (`writers.py:2097-2099`, `writers.py:2160-2162`) instead use `if not issue_id: continue` because they have no fallback to fall back to — they need no change.

### Step 4 — Add a guard at `cli/issues/set_status.py:144-154`

`record_issue_event()` is called *directly* (not via `SQLiteTransport`) and reads its `issue_id` from `args.issue_id` without going through `canonicalize_issue_id()`. Either:

- Resolve the on-disk file path from `args.issue_id`, call `canonicalize_issue_id(args.issue_id, path)`, and reject the CLI call with a clear error if the canonicalization returns `None`, **or**
- Cross-check `args.issue_id` against the frontmatter `id:` field's type and the file's filename-derived type before calling `record_issue_event()`.

### Step 5 — Unwrap the `except Exception: pass`

In `cli/issues/set_status.py:127-156`: at minimum, narrow to `except sqlite3.Error` and `logger.warning(...)` so the silent-swallow class is visible. The user-facing transition print at line 123 happens *before* the try-block, so any failure currently produces no stderr line and no nonzero exit.

> Caveat: `except Exception: pass` is a codebase-wide idiom (40+ bare-`except` sites across `scripts/` Python + YAML combined). Narrowing set-status to `except sqlite3.Error` is consistent with `session_store/writers.py`'s own narrower convention but inconsistent with the YAML-loop convention — treat the scope of this step as an implementer judgment call.

### Step 6 — Add a `TestSchemaV39` class

In `scripts/tests/test_session_store_schema.py`, after `TestSchemaV38BaseShaColumns` at line 1898+ (first new migration test class since ENH-2771):

- Use the `_bootstrap_schema_at()` helper at `test_session_store_schema.py:1134-1154` to seed a v38 database and assert the v39 migration's DELETE semantics.
- Add a regression test that seeds a `(25, 'done')` row for `BUG-025` plus a `(25, 'done')` insert attempt for `ENH-025`, asserting the post-fix state matches the desired behavior.

### Step 7 — Add an Option B unit test for `canonicalize_issue_id()`

In `scripts/tests/test_session_store_writers.py`:

- Mirror `test_record_issue_event_idempotent` (`test_session_store_writers.py:743-757`) but pass a mismatched frontmatter/filename pair and assert the function returns `None` and emits the expected `logger.warning`.

### Step 8 — Seed a raw-SQL collision regression test

In `scripts/tests/test_history_reader.py`, modeled on `test_find_session_for_issue_transition` at lines 2006-2026:

- Insert a `BUG-25/25/done` row, then assert that `record_issue_event(db, "ENH-25", "done")` *succeeds* (i.e. does not silently no-op) and produces a second `issue_events` row — this is the post-fix invariant that breaks today.

### Step 9 — Update stale documentation

`little-loops/docs/ARCHITECTURE.md:680` — the v16 entry mentions `issue_events.session_id` but does **not** document the v36 `issue_num` migration or `(issue_num, transition)` dedup index (doc gap to close at the same time as the fix).

## Files to Modify

- `scripts/little_loops/session_store/schema.py` — append v39 `_MIGRATIONS` entry; bump `SCHEMA_VERSION` to 39 (line 21)
- `scripts/little_loops/session_store/writers.py:2005-2054` — tighten `canonicalize_issue_id()`; update stale docstring at `:371-373`; remove `... or <raw>` fallbacks at `:310` and `:1905-1907`
- `scripts/little_loops/session_store/lifecycle.py:987` — stale docstring claiming `INSERT OR IGNORE` on `(issue_id, transition)` (companion to `writers.py:371-373`)
- `scripts/little_loops/issue_history/rework.py:45` — same stale comment in a different module
- `scripts/little_loops/cli/issues/set_status.py:127-156` — add a guard at `:144-154`; narrow the `except Exception: pass`
- `scripts/little_loops/issue_parser.py:492-499` — `check_format_gaps()` comparator (existing precedent; reuse for Option B comparison logic)
- `scripts/tests/test_session_store_schema.py` — add `TestSchemaV39` class after `TestSchemaV38BaseShaColumns`
- `scripts/tests/test_session_store_writers.py` — add Option B unit test for `canonicalize_issue_id()`
- `scripts/tests/test_history_reader.py` — raw-SQL collision regression test
- `scripts/tests/test_issue_history_rework.py:42` — stale comment asserting `(issue_id, transition)` dedup key (companion fix site)
- `little-loops/docs/ARCHITECTURE.md:680` — document the v36 `issue_num` migration and `(issue_num, transition)` dedup index

## Tests Required

- `TestSchemaV39` — first new migration test class since ENH-2771 (covers the v39 DELETE repair)
- `test_bare_numeric_issue_id_canonicalized_via_file_path` precedent (`test_session_store_writers.py:205`) — mirror for Option B
- `test_set_status_writes_issue_events_row` (`test_set_status_cli.py:1153`, BUG-2770)
- `test_set_status_canonicalizes_malformed_frontmatter_id` (`test_set_status_cli.py:1200`, BUG-2769, file_path fallback only)

## Verification

Run from the `little-loops` repo root:

- `python -m pytest scripts/tests/test_session_store_schema.py scripts/tests/test_session_store_writers.py scripts/tests/test_history_reader.py scripts/tests/test_set_status_cli.py -v`
- `python -m pytest scripts/tests/test_issue_parser.py -v` (regression check on the `malformed_id` branch reused by Option B)
- Smoke test: `python -c "from little_loops.session_store import SCHEMA_VERSION; print(SCHEMA_VERSION)"` should print `39`

## Acceptance Criteria

1. `sqlite3 .ll/history.db "SELECT issue_id FROM issue_events WHERE issue_num=25"` returns zero rows after the migration lands.
2. Triggering `ll-issues set-status ENH-025 done` after the migration produces an `issue_events` row for `ENH-025` with `(issue_num=25, transition='done')` — i.e. the previous silent no-op is now a real insert.
3. A mismatched frontmatter/filename pair (e.g. `id: BUG-025` on `ENH-025-*.md`) is rejected by `canonicalize_issue_id()` with a logged warning, and no `issue_events` row is created from that input.
4. `SCHEMA_VERSION == 39` after the v39 migration entry is appended and the migration has run on a fresh DB.
5. All tests in `test_session_store_schema.py`, `test_session_store_writers.py`, `test_history_reader.py`, and `test_set_status_cli.py` pass.
6. The four stale-docstring sites (`writers.py:371-373`, `lifecycle.py:987`, `issue_history/rework.py:45`, `tests/test_issue_history_rework.py:42`) are updated to describe the `(issue_num, transition)` index shape.
7. `little-loops/docs/ARCHITECTURE.md:680` documents the v36 `issue_num` migration and the `(issue_num, transition)` dedup index.

## References

This issue was identified by a hub-side observability audit (audit findings E5 + E55). The data-repair half (E55: heal corrupted titles, the phantom BUG-025 row, and the second history DB at `.issues/.ll/history.db`) is the precondition; this issue is the durable mechanism-level fix that closes the root cause at the writer boundary so the bug class cannot recur.

Related hub-side issue: BUG-105 (second history DB split — hub-side, separate from this spoke-side fix).
