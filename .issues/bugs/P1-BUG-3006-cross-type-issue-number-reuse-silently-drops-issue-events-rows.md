---
id: BUG-3006
title: Cross-type issue-number reuse silently drops issue_events completion rows
type: BUG
priority: P1
status: done
discovered_date: 2026-08-02
completed_at: '2026-08-02T23:09:11Z'
labels:
- observability
- history-db
- data-integrity
confidence_score: 96
outcome_confidence: 82
score_complexity: 17
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 18
---

# Cross-type issue-number reuse silently drops issue_events completion rows

## Summary

`idx_issue_events_dedup` is unique on `(issue_num, transition)` — the bare numeric portion of the issue id, type-blind. When two *different* issues reuse the same number under different type prefixes (e.g. a `BUG-1978` that was later deleted/renumbered, and an unrelated `EPIC-1978`), the second issue's transition silently no-ops against the first issue's row. `INSERT OR IGNORE` raises nothing and logs nothing, so a completion is lost with zero diagnostic signal.

**Live instance in this repo's `.ll/history.db`:** `EPIC-1978` is `status: done` on disk but has **zero** `done` rows in `issue_events`, because `BUG-1978` already occupies `(1978, 'done')`.

## Current Behavior

```
sqlite> SELECT issue_id, issue_num, transition, ts FROM issue_events WHERE issue_num=1978;
BUG-1978 |1978|done|2026-06-06T20:24:37Z
EPIC-1978|1978|open|2026-06-05

sqlite> SELECT COUNT(*) FROM issue_events WHERE issue_id='EPIC-1978' AND transition='done';
0
```

`.issues/epics/P2-EPIC-1978-cli-first-init-headless-core.md` is `status: done`. `BUG-1978` was a real file (added in `23adcaf7`, since deleted/renumbered). Its `(1978,'done')` row permanently blocks `EPIC-1978`'s own completion from ever being recorded.

No exception is raised, no log line is emitted — every writer uses `INSERT OR IGNORE`, which no-ops on the unique-index collision. `ll-issues set-status` additionally wraps the whole event-recording block in a blanket `except Exception: pass` (`cli/issues/set_status.py:126-156`), so even a genuine failure at that call site is invisible.

Downstream impact: `issue_events` is the root table for `issue_sessions` and `issue_effort()`. A dropped `done` row means the issue is absent from effort/duration analytics and from `ll-logs`/history queries that join on the completion transition.

## Expected Behavior

A completion transition for an issue that is genuinely distinct from the row already occupying its `(issue_num, transition)` slot is **not silently discarded**. At minimum the collision is detected and logged with both issue ids, so the loss is visible rather than silent. Retype dedup (ENH-2771's fix) is preserved unchanged.

## Steps to Reproduce

1. Create `.issues/bugs/P2-BUG-9001-first.md`, set it `done` via `ll-issues set-status BUG-9001 done`.
2. Delete the file and create an unrelated `.issues/epics/P2-EPIC-9001-second.md`.
3. `ll-issues set-status EPIC-9001 done`.
4. `sqlite3 .ll/history.db "SELECT issue_id FROM issue_events WHERE issue_num=9001 AND transition='done'"` returns only `BUG-9001`. `EPIC-9001`'s completion was dropped, with no error, no warning, and exit code 0.

## Root Cause

### 1. Type-blind numeric dedup key

`idx_issue_events_dedup` is `UNIQUE INDEX ... ON issue_events(issue_num, transition) WHERE issue_num IS NOT NULL`, created by migration v36 (`scripts/little_loops/session_store/schema.py:823-905`, ENH-2771). `issue_snapshots` carries the identical `idx_issue_snapshots_dedup` shape. `normalize_issue_id()` (`writers.py:132-159`) strips the `TYPE-` prefix via `_ISSUE_NUM_RE` and returns the bare int, so `BUG-1978` and `EPIC-1978` both key to `1978`.

### 2. v36 deliberately made the key type-blind — and that was correct

v36 replaced the original `(issue_id, transition)` index (v3, `schema.py:176-181`) specifically to fix a *different* bug: an issue that gets **retyped** (ENH→FEAT) splitting its history across two rows. That fix is live and working. Confirmed retypes in `issue_snapshots` today:

| issue_num | rows | on-disk file |
|-----------|------|--------------|
| 2576 | `ENH-2576 deferred`, `FEAT-2576 done` | `FEAT-2576` only |
| 2689 | `FEAT-2689 deferred`, `ENH-2689 open/done` | `ENH-2689` only |
| 2705 | `ENH-2705 deferred`, `FEAT-2705 open/done` | `FEAT-2705` only |

**Retype (same issue, one file) and number-reuse (two distinct issues) are structurally indistinguishable in the DB** — both appear as one `issue_num` with two type prefixes. This is the core tension: any key that separates 1978 also re-splits 2576/2689/2705.

### 3. Silent-swallow at every write site

All `INSERT OR IGNORE` sites share silent-on-collision semantics: `record_issue_event` (`writers.py:380`), `record_issue_snapshot` (`writers.py:331`), `SQLiteTransport.send()` `issue.*` branch (`writers.py:1915`), `_backfill_snapshots` (`writers.py:2108`), `_backfill_issues_and_snapshots` (`writers.py:2176`, `:2211`). None inspects `cursor.rowcount`, so no site can distinguish "already recorded, correctly deduped" from "a different issue's record was just discarded."

### 4. Not a malformed-frontmatter problem

An earlier revision of this issue hypothesized that a stray `id: BUG-025` in an `ENH-025-*.md` file created a phantom row, and proposed tightening `canonicalize_issue_id()` at the writer boundary. **That hypothesis is refuted by the data.** The `issue_num=25` row is `ENH-025 | done | 2026-02-13T00:00:00Z`, which exactly matches `.issues/enhancements/P3-ENH-025-universal-discovered-by-field.md` (`status: done`, `completed_at: 2026-02-13T00:00:00Z`) — a correct row. That file has no `id:` frontmatter field at all, so `canonicalize_issue_id()` derived the id from the filename exactly as designed. There is no `BUG-025` row and never was.

Both real collisions (1978 in `issue_events`; 2576/2689/2705 in `issue_snapshots`) involved genuine, correctly-typed files with well-formed frontmatter. Writer-boundary id validation would have prevented **none** of them.

## Program Design

_Based on codebase analysis:_

### Deviations

- **2026-08-02** — The Step 2 audit CLI's classification signal turned out to differ
  from what this section originally implied. "Which of the colliding ids has an
  on-disk file" was tried first and rejected during implementation: the confirmed
  BUG-1978/EPIC-1978 collision and the confirmed 2576/2689/2705 retypes both leave
  **exactly one** on-disk survivor, so a simple on-disk-count check cannot tell
  retype from number-reuse — they're indistinguishable on that signal alone (unit
  tests written against the literal plan text failed on both fixtures with this
  approach). The implemented signal instead compares the on-disk survivor's current
  `status:` frontmatter against its own recorded transitions in that table: a
  retype's survivor was written under its current type the whole time its current
  status was recorded, so the two agree; a number-reuse victim's most recent
  transition (e.g. `EPIC-1978`'s `done`) was the one silently discarded by the
  collision, so its on-disk status is absent from its own recorded transitions.
  `ll-history audit-issue-collisions` on this repo confirms the expected
  classification for all four known cases (see Verification). `CollisionEntry`
  gained an `on_disk_status` field beyond what § Signatures specifies, to carry this.

### Types

- `normalize_issue_id(issue_id: str | int | None) -> int | None` — `writers.py:132`, backed by `_ISSUE_NUM_RE = re.compile(r"(?:BUG|ENH|FEAT|EPIC)-(\d+)", re.IGNORECASE)`. Type-blind by design; returns the bare `int` that the dedup index collides on. **Unchanged by this fix.**
- `record_issue_event(db_path, issue_id, transition, *, session_id=None, issue_type=None, priority=None, discovered_by=None, captured_at=None, completed_at=None) -> None` — `writers.py:349-407`. Returns `None` today; the fix does not change the signature (callers ignore the return), but the function gains a post-insert collision probe.
- `canonicalize_issue_id(raw: object, file_path: str | Path | None) -> str | None` — `writers.py:2005`. **Not modified.** Working as designed; listed only to record that it was investigated and cleared.

### Signatures

- New module-level helper in `writers.py`, adjacent to `record_issue_event`:
  `_warn_on_dedup_collision(conn: sqlite3.Connection, table: str, issue_num: int | None, issue_id: str, transition: str, inserted: bool) -> None`
  When `inserted` is `False` and `issue_num` is not `None`, `SELECT issue_id FROM {table} WHERE issue_num=? AND transition=?`; if the stored id differs from `issue_id`, `logger.warning(...)` naming both ids, the table, and the transition. Identical stored id → silent (correct idempotent no-op). `table` is an internal literal (`"issue_events"` / `"issue_snapshots"`), never caller-supplied — interpolated into the `SELECT`, never parameterized.
- `inserted` is derived from `cursor.rowcount` on the `INSERT OR IGNORE` (`0` = suppressed, `1` = written); the existing `conn.execute(...)` calls must capture their return value, which they currently discard.

### Call Path

- `cli/issues/set_status.py:126-156` → `record_issue_snapshot()` (`:132`) and `record_issue_event()` (`:144-154`) → `normalize_issue_id()` → `INSERT OR IGNORE` at `writers.py:331` / `writers.py:380` → **new** `_warn_on_dedup_collision()`
- `SQLiteTransport.send()` `issue.*` branch (`writers.py:1867-1953`) → `canonicalize_issue_id()` at `:1905-1907` → `normalize_issue_id()` at `:1913` → `INSERT OR IGNORE` at `:1915` → **new** `_warn_on_dedup_collision()`; on `transition in ("done","open","cancelled")` also calls `record_issue_snapshot()` at `:1947`
- `_backfill_snapshots()` (`writers.py:2097-2108`) and `_backfill_issues_and_snapshots()` (`writers.py:2160-2211`) → same probe, but **suppressed by default** — a backfill legitimately replays already-recorded history and would emit warnings for every retyped issue. Gate behind an explicit flag so the audit CLI (Step 2) can turn it on.

## Proposed Solution — Option C (selected)

**Option A — widen the dedup key to include type** (e.g. `(issue_type, issue_num, transition)`): separates 1978 correctly, but re-splits the 2576/2689/2705 retypes, reintroducing exactly the bug v36/ENH-2771 was written to fix. `issue_type` is also NULL in ~1.6–3% of existing rows at 3 of 4 write sites, so the widened key lacks a reliable source. **Rejected.**

**Option B — tighten `canonicalize_issue_id()` to reject frontmatter/filename type mismatches**: addresses a mechanism for which there is no evidence. All four real collisions involved well-formed, correctly-typed files. Would have prevented zero observed cases while adding a rejection path that can drop legitimate events. **Rejected** (this was the prior revision's selection, made against a since-refuted premise).

**Option C — detect the collision and make it observable**: leave the index and `canonicalize_issue_id()` alone; check `cursor.rowcount` after each `INSERT OR IGNORE`, read back the stored `issue_id`, and warn when it differs from the caller's. Requires no schema change, preserves ENH-2771's retype dedup exactly, and converts a silent permanent data loss into a logged, greppable event at the moment it happens. Pairs with a one-time audit CLI to surface the collisions already in the DB. **Selected.**

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (widen index) | 0/3 | 1/3 | 1/3 | 0/3 | 2/12 |
| Option B (validate ids at writer) | 1/3 | 2/3 | 2/3 | 1/3 | 6/12 |
| Option C (detect + surface collision) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |

**Deliberately out of scope:** automatically *resolving* a detected collision (renumbering, forcing the insert under a synthetic key, or dropping the older row). Because retype and number-reuse are indistinguishable from the DB alone, any automatic resolution risks corrupting the retype case. This issue makes the loss visible; disambiguation is a follow-up if the warning ever fires in practice.

## Implementation Plan

All paths are under `scripts/little_loops/` unless noted. No schema migration and no `SCHEMA_VERSION` bump are required — Option C is pure Python.

### Step 1 — Add `_warn_on_dedup_collision()` and wire it into the five write sites

In `session_store/writers.py`:

- Add the helper described in Program Design § Signatures, placed next to `record_issue_event`.
- Capture `cursor = conn.execute(...)` at `writers.py:331` (`record_issue_snapshot`), `:380` (`record_issue_event`), and `:1915` (`SQLiteTransport.send()` `issue.*` branch); call the helper with `inserted=(cursor.rowcount == 1)`.
- Wire the two backfill sites (`:2108`, `:2176`, `:2211`) with the probe **off by default** via a keyword-only `warn_on_collision: bool = False`, so replaying history stays quiet.
- Warning text should name both ids explicitly, e.g.
  `issue_events dedup collision: %s %s discarded — (issue_num=%d, transition=%r) already held by %s. If these are distinct issues, the newer transition is lost; if this is a retype, it is expected.`

### Step 2 — Add a `ll-history audit-issue-collisions` read-only report

Surface the collisions already present. Group `issue_events` and `issue_snapshots` by `issue_num` having `COUNT(DISTINCT issue_id) > 1`, and for each group report the ids, transitions, and whether an on-disk `.issues/` file exists for each id — the on-disk check is what distinguishes retype (one file survives) from number-reuse (the ids are unrelated). Read-only; no `DELETE`, no repair. Locate alongside the existing `ll-history` subcommands.

Expected output on this repo today: `issue_events` → 1 group (`1978`, number-reuse); `issue_snapshots` → 3 groups (`2576`, `2689`, `2705`, all retypes).

### Step 3 — Narrow `except Exception: pass` in `set_status.py`

`cli/issues/set_status.py:155-156`: narrow to `except (sqlite3.Error, ImportError, OSError)` with a `logger.warning(...)`, so genuine write failures are visible. The user-facing transition print at `:123` happens *before* the try-block, so a failure today produces no stderr line and exit code 0.

> The `except Exception: pass` idiom is codebase-wide (40+ sites). Narrowing here is consistent with `session_store/writers.py`'s own convention; treat the exact exception tuple as an implementer judgment call, but do not leave it bare.

### Step 4 — Fix the stale docstrings

Five sites still describe the dedup key as `(issue_id, transition)`, which has been wrong since v36:

- `session_store/writers.py:303` (`record_issue_snapshot`) — *not listed in the prior revision; found during this pass*
- `session_store/writers.py:372` (`record_issue_event`)
- `session_store/lifecycle.py:987` (`backfill_snapshots`)
- `issue_history/rework.py:45`
- `scripts/tests/test_issue_history_rework.py:42` (comment)

Each should read `(issue_num, transition)` and note the type-blindness plus the new collision warning.

### Step 5 — Tests

In `scripts/tests/test_session_store_writers.py`:

- Number-reuse warns: insert `BUG-9001/9001/done`, then `record_issue_event(db, "EPIC-9001", "done")`; assert exactly one row remains **and** that `caplog` contains the collision warning naming both ids. This is the regression test for the reported bug.
- Retype stays silent: insert `ENH-9002/9002/done`, call `record_issue_event(db, "ENH-9002", "done")` again; assert no warning (identical id → correct idempotent no-op). Extend `test_record_issue_event_idempotent` (`:743-757`) rather than duplicating it.
- Same pair for `record_issue_snapshot()` against `issue_snapshots`.
- Backfill is quiet: assert `_backfill_issues_and_snapshots()` emits no collision warnings on a DB seeded with a retype pair.

In `scripts/tests/test_set_status_cli.py` (follow `TestSetStatusRecordsIssueEvent` scaffolding at `:1153`, `:1200`):

- Assert a mocked `sqlite3.Error` from `record_issue_event` is caught **and logged**, while an unrelated exception type propagates.
- End-to-end: `ll-issues set-status` on a number-reuse pair emits the warning.

New `scripts/tests/` coverage for the Step 2 audit CLI: seed one retype pair and one number-reuse pair, assert both are reported and correctly classified by the on-disk-file check.

### Step 6 — Documentation

- `docs/ARCHITECTURE.md:680` — the v16 entry mentions `issue_events.session_id` but never documents the v36 `issue_num` migration or the `(issue_num, transition)` dedup index. Add both, including the type-blindness and its retype-vs-reuse consequence.
- `docs/reference/CLI.md:2004` — `ll-issues set-status` describes the `issue_events` write as unconditionally "best-effort" with no guard; note the narrowed exception handling and the collision warning.
- `docs/reference/CLI.md` — document the new `ll-history audit-issue-collisions` subcommand.
- `docs/reference/API.md:8490` — `record_issue_event` description; note the collision-warning behavior.

### Step 7 — Pre-existing doc staleness (unblocked side-cleanup)

These are already stale against `SCHEMA_VERSION = 38` and are worth fixing while in the area, but are **not** caused by this fix (Option C bumps no version):

- `docs/reference/API.md:8473` — "Current schema version: **34**"
- `docs/reference/API.md:8477` — inline comment `SCHEMA_VERSION,  # 30`
- `docs/development/USER_GUIDE_AUDIT_REPORT.md:293` — "History DB schema version: 12"

## Files to Modify

- `scripts/little_loops/session_store/writers.py` — add `_warn_on_dedup_collision()`; capture `rowcount` at `:331`, `:380`, `:1915`; gated probe at `:2108`, `:2176`, `:2211`; fix docstrings at `:303`, `:372`
- `scripts/little_loops/cli/issues/set_status.py:155-156` — narrow `except Exception: pass`
- `scripts/little_loops/session_store/lifecycle.py:987` — stale docstring
- `scripts/little_loops/issue_history/rework.py:45` — stale comment
- `scripts/little_loops/cli/` — new `ll-history audit-issue-collisions` subcommand (Step 2)
- `scripts/tests/test_session_store_writers.py` — collision-warning and retype-silence tests
- `scripts/tests/test_set_status_cli.py` — narrowed-exception and end-to-end tests
- `scripts/tests/test_issue_history_rework.py:42` — stale comment
- new `scripts/tests/` coverage for the audit CLI
- `docs/ARCHITECTURE.md:680`, `docs/reference/CLI.md:2004`, `docs/reference/API.md:8490` — see Step 6
- `docs/reference/API.md:8473,8477`, `docs/development/USER_GUIDE_AUDIT_REPORT.md:293` — pre-existing staleness, Step 7

### Dependent Files (Callers/Importers)

- No callers of `record_issue_event()` / `record_issue_snapshot()` exist beyond the sites listed above (confirmed by codebase trace). Both return `None` today and the fix keeps that, so no caller needs updating.
- **No `SCHEMA_VERSION` bump**, so `scripts/tests/test_assistant_messages.py:88` (`assert SCHEMA_VERSION == 38`) is **not** affected. This was a required change under the prior revision's plan; it is not under Option C.
- `scripts/tests/test_session_store_writers.py:134-150` (`test_issue_event_transition_mapping`) uses a non-canonical `issue_id="X-1"` with no `file_path`. Option C does not touch `canonicalize_issue_id()` or its `... or <raw>` fallbacks, so this test is unaffected — noted only because the prior revision would have broken it.

## Tests Required

- New: number-reuse collision emits a warning naming both ids (`issue_events` and `issue_snapshots`)
- New: retype / identical-id re-insert stays silent
- New: backfill paths stay silent by default
- New: audit CLI classifies retype vs number-reuse via the on-disk-file check
- New: `set_status` logs a caught `sqlite3.Error`; other exception types propagate
- Extend: `test_record_issue_event_idempotent` (`test_session_store_writers.py:743-757`)
- Regression: `test_set_status_writes_issue_events_row` (`test_set_status_cli.py:1153`, BUG-2770), `test_set_status_canonicalizes_malformed_frontmatter_id` (`:1200`, BUG-2769) must still pass unchanged

## Verification

From the repo root:

- `python -m pytest scripts/tests/test_session_store_writers.py scripts/tests/test_set_status_cli.py scripts/tests/test_session_store_schema.py scripts/tests/test_history_reader.py scripts/tests/test_issue_history_rework.py -v`
- `python -m pytest scripts/tests/` — full suite green
- `ll-history audit-issue-collisions` on this repo reports `issue_events`: `1978` (number-reuse) and `issue_snapshots`: `2576`, `2689`, `2705` (retypes)

## Acceptance Criteria

1. `record_issue_event()` and `record_issue_snapshot()` emit a `logger.warning` naming both issue ids when an `INSERT OR IGNORE` is suppressed by a row holding a **different** `issue_id` at the same `(issue_num, transition)`.
2. An identical-id re-insert (true idempotent no-op) emits **no** warning.
3. Backfill paths emit no collision warnings by default.
4. `ll-history audit-issue-collisions` reports every `issue_num` in `issue_events` and `issue_snapshots` held by more than one `issue_id`, and classifies each as retype or number-reuse via an on-disk `.issues/` file check. It performs no writes.
5. `SCHEMA_VERSION` is unchanged at 38; `idx_issue_events_dedup` and `idx_issue_snapshots_dedup` remain on `(issue_num, transition)`; ENH-2771's retype dedup still holds for `2576`/`2689`/`2705`.
6. `cli/issues/set_status.py` no longer swallows all exceptions silently; a caught DB error produces a warning.
7. The five stale-docstring sites (`writers.py:303`, `writers.py:372`, `lifecycle.py:987`, `issue_history/rework.py:45`, `tests/test_issue_history_rework.py:42`) describe the `(issue_num, transition)` key.
8. `docs/ARCHITECTURE.md:680` documents the v36 `issue_num` migration, the `(issue_num, transition)` dedup index, and its type-blindness.
9. Full `python -m pytest scripts/tests/` passes.

## Impact

- **Data integrity**: a completion transition can be permanently and silently
  discarded whenever a numeric id is reused across a different type prefix.
  `EPIC-1978` is the confirmed live instance in this repo's own `.ll/history.db`.
- **Analytics gap**: `issue_events` is the root table for `issue_sessions` and
  `issue_effort()`; a dropped `done` row removes the issue from effort/duration
  analytics and from any `ll-logs`/history query joining on the completion
  transition, with zero error signal to notice it happened.
- **Masked failures**: `set_status.py`'s blanket `except Exception: pass` means
  even a genuine DB write failure at this call site currently produces no
  stderr line and exit code 0.
- P1 because the failure mode is silent and permanent (no retry, no log, no
  exit-code signal), even though the write path itself is narrow (issue
  completion transitions only) and Option C requires no schema change.

## Status

**Open** | Created: 2026-08-02 | Priority: P1

## Notes

**`EPIC-1978`'s lost `done` row is not repaired by this fix.** Option C makes future losses visible; it does not backfill the one already taken. Repairing it means inserting a row that the unique index forbids without either a synthetic key or deleting `BUG-1978`'s row — both of which risk the retype case. Track separately if the analytics gap matters.

**Unrelated finding from the same audit:** a stray zero-byte `.issues/.ll/history.db` exists. It shadows `find_project_root()` for anything resolving from inside `.issues/`. Zero bytes means no data was written there, so nothing was lost — but the stray `.ll/` directory should be removed. Separate issue.

## References

Identified by an observability audit. The original revision of this issue was written against a "phantom `BUG-025` row" premise that verification against `.ll/history.db` refuted — no such row exists; `issue_num=25` holds a correct `ENH-025 done` row matching its on-disk file. This revision re-anchors on the `1978` collision, which is real and reproducible.

## Session Log
- `/ll:manage-issue` - 2026-08-02T23:08:52 - `d33b540d-8b96-4540-9f2b-d60447bf5b2a.jsonl`
- `/ll:ready-issue` - 2026-08-02T22:36:46 - `16f792a7-36fa-4ba8-b9d3-5872d8971f3f.jsonl`
- `/ll:confidence-check` - 2026-08-02T22:27:15 - `d6fe08ee-2c9a-4d85-87c7-ff92a712a1ff.jsonl`
- `/ll:confidence-check` - 2026-08-02T22:07:26 - `e7f2cc20-1ed8-4981-b8bd-33be36b2d365.jsonl`
- `/ll:wire-issue` - 2026-08-02T22:00:37 - `8df826b4-7a59-474c-9d12-c9d43cdd3d7b.jsonl`
- `/ll:refine-issue` - 2026-08-02T21:37:41 - `318b91da-b9fe-4a72-ab97-e9f2a732a2f6.jsonl`
