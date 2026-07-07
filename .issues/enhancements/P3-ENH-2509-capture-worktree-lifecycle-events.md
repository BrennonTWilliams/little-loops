---
id: ENH-2509
title: Capture worktree lifecycle events into session_lifecycle_events
type: ENH
priority: P3
status: open
discovered_date: 2026-07-06
captured_at: "2026-07-06T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
labels:
  - enhancement
  - history-db
  - worktree
  - widening
  - captured
---

# ENH-2509: Capture worktree lifecycle events into session_lifecycle_events

## Summary

`ll-parallel`, `ll-loop` (in worktree mode), and `ll-sprint` create,
merge, and delete git worktrees as part of orchestration — and none of
those ops leave a row in `.ll/history.db`. So "did BUG-2501's worktree
ever get cleaned up" or "how many worktrees did session X spin up" are
unanswerable. Widen ENH-2495's `session_lifecycle_events` table with a
new event discriminator (`worktree_create` / `worktree_merge` /
`worktree_delete`) and rows of `(session_id, worktree_path, op, branch,
issue_id, parent_sha, ts)`. Trivial fold into ENH-2495 — single new
event type, same producer wiring pattern.

## Motivation

- **Worktrees are first-class orchestration primitives that leave no
  trace.** When `ll-parallel` spawns 4 workers each on its own
  worktree, those worktrees are how the issue→session mapping actually
  works — but if a cleanup hook fails (or the user kills the parent
  process mid-merge), the orphaned worktree is invisible.
- **The widens-ENH-2495 pattern is already established.** ENH-2494
  (check_events) was widened by ENH-2498 (prompt_opt_events) to absorb
  additional `ll-verify-*` / `ll-check-links` / `ll-deps validate`
  gates. ENH-2495 is the obvious widening target for worktree ops:
  same shape (event discriminator + JSON detail), same producer
  pattern (best-effort, called from the orchestration entry point),
  same read API.
- **Cost is very low.** `scripts/little_loops/cli/parallel.py` and
  `scripts/little_loops/cli/loop/_helpers.py` already wrap worktree
  ops in their own try/except; adding `record_session_lifecycle_event
  (event="worktree_create", detail={...})` is a one-line add per op.

## Current Behavior

- `ll-parallel` (`scripts/little_loops/cli/parallel.py`) creates
  worktrees via `git worktree add`, runs the worker, then merges via
  `git worktree remove` / `git merge --squash`. None of these emit a
  DB row.
- `ll-loop run <loop> --worktree` (the worktree-mode loop runner)
  similarly leaves no trace.
- `scripts/little_loops/cli/cleanup_worktrees.py` (the orphan
  cleaner) reads `.loops/worktrees/` to find stragglers but cannot
  tell which session created each one.
- ENH-2495 proposes the `session_lifecycle_events` table; this issue
  is a scope-widening that adds worktree ops to its event vocabulary.

## Expected Behavior

- `session_lifecycle_events` accepts three new event values:
  `worktree_create`, `worktree_merge`, `worktree_delete`.
- Each worktree op calls `record_session_lifecycle_event(event=...,
  detail={"worktree_path": ..., "branch": ..., "issue_id": ...,
  "parent_sha": ...})` (best-effort, no shell-out for the bash path).
- `ll-session recent --kind session_lifecycle` returns worktree rows
  alongside the existing `handoff_needed`, `compaction`,
  `stale_ref_sweep`, `session_end` rows.
- A new `history_reader.worktree_summary(issue_id=None, since=None)`
  helper aggregates per-issue worktree ops (created/merged/deleted
  counts).

## Proposed Solution

### Schema migration

No new table. Widen ENH-2495's existing `session_lifecycle_events`:

- The migration's `event` column is `TEXT NOT NULL` (already proposed
  in ENH-2495) — no constraint on value. The three new values are
  purely convention; a CHECK constraint isn't needed because producers
  control the value set.
- Optional: add a separate index on `event` for the worktree subset if
  the rollup query becomes hot:
  ```sql
  CREATE INDEX IF NOT EXISTS idx_lifecycle_worktree
      ON session_lifecycle_events(worktree_path) WHERE worktree_path IS NOT NULL;
  ```
  but the JSON-in-`detail` model (ENH-2495 §"Proposed Solution") means
  `worktree_path` lives inside `detail`, not as a top-level column.
  Defer the index unless the rollup justifies it; the JSON path can be
  searched via `json_extract(detail, '$.worktree_path')` with a
  functional index if needed.

### Producer wiring

- In `scripts/little_loops/cli/parallel.py`, wrap each worktree op in
  `record_session_lifecycle_event(event="worktree_create"|"worktree_
  merge"|"worktree_delete", detail={"worktree_path": ...,
  "branch": ..., "issue_id": ..., "parent_sha": ...})`. Best-effort
  per the EPIC-1707 contract.
- In `scripts/little_loops/cli/loop/_helpers.py` (the worktree-mode
  loop runner), same pattern.
- In `scripts/little_loops/cli/cleanup_worktrees.py` (the orphan
  sweeper), emit a `worktree_delete` row when an orphan is removed.
  Note: this is not a producer initiated by a session — pass
  `session_id=None` (the row still has utility for inventory).
- All writes best-effort; a worktree-op failure should not become a
  recorder failure.

### Read API

- `history_reader.recent_lifecycle_events(event="worktree_create",
  since=None, limit=50)` — already supported by ENH-2495's generic
  helper.
- `history_reader.worktree_summary(issue_id=None, since=None)` — new
  helper: `SELECT detail->>'issue_id', COUNT(*) FILTER (WHERE event =
  'worktree_create'), COUNT(*) FILTER (WHERE event = 'worktree_merge'),
  COUNT(*) FILTER (WHERE event = 'worktree_delete') FROM
  session_lifecycle_events WHERE event LIKE 'worktree_%' [AND ts >= ?]
  GROUP BY 1`.

### CLI surface

- `ll-session recent --kind session_lifecycle` already exists (from
  ENH-2495); no new `--kind` value.
- `ll-session worktree-summary [--since 7d]` (optional follow-on) —
  per-issue worktree op counts.

## Acceptance Criteria

- ENH-2495's `session_lifecycle_events` schema accepts the new event
  values without modification.
- `ll-parallel --input BUG-2501` produces a `worktree_create` row with
  the worktree path, branch, issue_id, and parent sha in `detail`.
- A successful merge produces a `worktree_merge` row; a `git worktree
  remove` (or equivalent cleanup) produces a `worktree_delete` row.
- Orphan cleanup emits a `worktree_delete` row (with `session_id=NULL`).
- DB-absent/locked does not change the worktree op exit code.
- `ll-session recent --kind session_lifecycle` returns worktree rows;
  `worktree_summary` returns per-issue counts.
- Tests cover: each op, graceful DB-absent, malformed worktree path
  doesn't raise.

## Sources

- EPIC-2457 review (third-pass expansion, 2026-07-06) — item from the
  user-reported gap list
- ENH-2495 — sibling session_lifecycle_events work; this issue widens
  it
- `scripts/little_loops/cli/parallel.py` — worktree producer
- `scripts/little_loops/cli/loop/_helpers.py` — worktree-mode loop
  runner
- `scripts/little_loops/cli/cleanup_worktrees.py` — orphan sweeper

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table; hook write-paths note |
| `docs/reference/API.md` | `session_store`, `history_reader` modules |
| `docs/reference/CLI.md` | `ll-session --kind session_lifecycle` (already supported by ENH-2495) |

## Status

**Open** | Created: 2026-07-06 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`