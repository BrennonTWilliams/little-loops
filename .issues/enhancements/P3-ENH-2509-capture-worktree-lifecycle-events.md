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
decision_needed: true
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

### Codebase Research Findings — Stale Reference Audit

_Added by `/ll:refine-issue` — based on codebase analysis (2026-07-16):_

The following references in the Sources list above are **stale** and must
be corrected before implementation begins:

- **`scripts/little_loops/cli/cleanup_worktrees.py` does not exist.**
  Per BUG-2324 and `commands/cleanup-worktrees.md`, orphan cleanup is
  delegated to `ll-parallel --cleanup-orphans`, which calls
  `ParallelOrchestrator._cleanup_orphaned_worktrees` at
  `scripts/little_loops/parallel/orchestrator.py:274`. Update the
  producer wiring target accordingly.
- **`scripts/little_loops/cli/loop/_helpers.py` is a layout/display
  helper module** that does not import or call worktree functions. The
  actual worktree-mode loop runner is `cmd_run()` in
  `scripts/little_loops/cli/loop/run.py:416-504`. Update the producer
  wiring target accordingly.
- **ENH-2495 (the parent table this widens) is not yet implemented.**
  `SCHEMA_VERSION = 20` (v17=commit_events/ENH-2458, v18=test_run_events/
  ENH-2459, v19=raw_events/ENH-2581, v20=usage_events/ENH-2461).
  ENH-2495's plan still references "v19"; the next open migration slot
  is **v21**. There is currently no `session_lifecycle_events` table,
  no `record_session_lifecycle_event` function, and no
  `recent_lifecycle_events` or `worktree_summary` reader. ENH-2509
  cannot land independently — see Decision Point below.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table; hook write-paths note |
| `docs/reference/API.md` | `session_store`, `history_reader` modules |
| `docs/reference/CLI.md` | `ll-session --kind session_lifecycle` (already supported by ENH-2495) |

## Status

**Open** | Created: 2026-07-06 | Priority: P3

## Implementation Steps

_Added by `/ll:refine-issue` — based on codebase analysis (2026-07-16):_

### Phase 1 — Pre-requisite (ENH-2495-absorbed work)

1. Append migration **v21** to `_MIGRATIONS` at
   `scripts/little_loops/session_store.py:333` creating
   `session_lifecycle_events` table with the ENH-2495 schema (event,
   detail JSON, head_sha, branch) plus
   `idx_lifecycle_event`/`idx_lifecycle_session` indexes. Bump
   `SCHEMA_VERSION = 20 → 21` at line 207.
2. Add `"session_lifecycle"` to `VALID_KINDS` at
   `session_store.py:209-222` and the matching
   `"session_lifecycle": "session_lifecycle_events"` entry to
   `_KIND_TABLE` at `session_store.py:223-236`.
3. Implement `record_session_lifecycle_event(db_path, *, session_id,
   event, detail=None, head_sha=None, branch=None, ts=None)` in
   `session_store.py`. Mirror the modern internal-suppress pattern from
   `skill_event_context()` at line 1108
   (`try/except sqlite3.Error: logger.warning(...)` inside the
   recorder). Use `_index(...)` at line 705 for FTS. Add to `__all__`
   at line 60-87.
4. Implement `recent_lifecycle_events(*, event=None, limit=20,
   db=DEFAULT_DB_PATH)` and `worktree_summary(issue_id=None, since=None,
   db=DEFAULT_DB_PATH)` in `scripts/little_loops/history_reader.py`.
   Mirror `recent_commit_events` (line 651) and `summarize_skills`
   (line 497). `worktree_summary` uses
   `json_extract(detail, '$.issue_id')` GROUP BY with
   `COUNT(*) FILTER (WHERE event = ...)`.

### Phase 2 — Producer wiring (the ENH-2509 work)

5. In `scripts/little_loops/parallel/worker_pool.py`, wrap
   `_setup_worktree` (line 684) to emit
   `record_session_lifecycle_event(event="worktree_create", detail=
   {"worktree_path": ..., "branch": ..., "issue_id": ..., "parent_sha":
   baseline_head_sha})` on success. Available context: `issue.issue_id`
   (caller), `branch_name` (caller), `worktree_path` (caller),
   `baseline_head_sha` (line 373).
6. Same file, `_cleanup_worktree` (line 756): emit
   `event="worktree_delete"` after `cleanup_worktree()` returns
   successfully. Also pass through `WorkerPool.cleanup_all_worktrees`
   at line 1818 (looped).
7. In `scripts/little_loops/parallel/merge_coordinator.py`, after
   `_finalize_merge` (line 1030) succeeds and before
   `_cleanup_worktree` (line 1066) runs, emit
   `event="worktree_merge"` carrying the merge target branch.
8. In `scripts/little_loops/parallel/orchestrator.py`,
   `_merge_pending_worktrees` (lines 552-627): after `git merge --no-ff`
   (line 592-602) succeeds, emit `event="worktree_merge"` with the
   merged branch info; after `git worktree remove` (line 607-611),
   emit `event="worktree_delete"`.
9. Same file, `_cleanup_orphaned_worktrees` (line 274): after each
   orphan is removed (around line 353), emit
   `event="worktree_delete", session_id=None, detail={"worktree_path":
   ..., "branch": ..., "reason": "orphan_cleanup"}`. Skip emission on
   `dry_run=True` paths (line 318-327) — no op was performed.
10. In `scripts/little_loops/cli/loop/run.py`, after `setup_worktree`
    at line 448 inside `cmd_run()`: emit `event="worktree_create",
    detail={"worktree_path": ..., "branch": ..., "loop_name": ...,
    "parent_sha": _base_commit}`.
11. Same file, `_cleanup_worktree_on_exit` closure (line 460), after
    `cleanup_worktree(...)` at line 493: emit
    `event="worktree_delete", detail={"worktree_path": ...,
    "branch": ..., "loop_name": ...}`.

### Phase 3 — Tests

12. In `scripts/tests/test_session_store.py`, add
    `TestRecordSessionLifecycleEvent` (round-trip, FTS searchability,
    event distinctness, db-upgrade gains table) — mirror
    `TestRecordTestRunEvent` at line 4362.
13. In `scripts/tests/test_history_reader.py`, add
    `TestRecentLifecycleEvents` (filter by event value) and
    `TestWorktreeSummary` (per-issue rollup, since filter, empty DB).
14. In `scripts/tests/test_ll_session.py`, add
    `test_recent_subcommand_session_lifecycle_accepted` and
    `test_recent_kind_session_lifecycle_outputs_row` — mirror lines 78
    and 1075.
15. In `scripts/tests/test_worker_pool.py`, add
    `TestWorktreeProducerWiring` asserting `worktree_create` row
    written on setup, `worktree_delete` on cleanup; pass `db_path=
    tmp_path / "history.db"` and verify graceful DB-absent
    degradation.
16. In `scripts/tests/test_cli_loop_worktree.py`, add
    `TestLoopWorktreeProducerWiring` covering lines 416-504 of
    `cmd_run`.
17. In `scripts/tests/test_orchestrator.py`, add
    `TestOrphanCleanupProducerWiring` asserting
    `event="worktree_delete"` rows with `session_id=None`.

### Phase 4 — CLI follow-on (optional)

18. Add `ll-session worktree-summary [--since 7d]` subcommand to
    `scripts/little_loops/cli/session.py` mirroring the
    `skill-stats` shape (subprocess invocation of internal
    `worktree_summary()` helper).

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-07-16):_

### Producer Wiring Targets (Verified Locations)

| Producer | File | Anchor | Event |
|----------|------|--------|-------|
| Worker setup | `scripts/little_loops/parallel/worker_pool.py` | `_setup_worktree` (line 684) | `worktree_create` |
| Worker cleanup (post-merge) | same | `_cleanup_worktree` (line 756) | `worktree_delete` |
| All-workers cleanup | same | `cleanup_all_worktrees` (line 1818) | `worktree_delete` (looped) |
| Merge finalize | `scripts/little_loops/parallel/merge_coordinator.py` | `_finalize_merge` (line 1030) + `_cleanup_worktree` (line 1066) | `worktree_merge` then `worktree_delete` |
| Pending-merge resume | `scripts/little_loops/parallel/orchestrator.py` | `_merge_pending_worktrees` (lines 552-627) | `worktree_merge` (line 592-602) then `worktree_delete` (line 607-611) |
| Orphan sweep | same | `_cleanup_orphaned_worktrees` (line 274) | `worktree_delete` (`session_id=None`, skip on dry-run) |
| Loop create | `scripts/little_loops/cli/loop/run.py` | `cmd_run` `--worktree` branch (line 448) | `worktree_create` |
| Loop cleanup | same | `_cleanup_worktree_on_exit` (line 460, calls cleanup at 493) | `worktree_delete` |
| EPIC integration merge (optional) | `scripts/little_loops/worktree_utils.py` | `merge_epic_branch_to_base` (line 486) | `worktree_merge` |

### Context Availability at Each Site

| Producer | `session_id` | `issue_id` | `parent_sha` |
|----------|--------------|------------|--------------|
| `WorkerPool` create/cleanup | None (parallel not wrapped in `cli_event_context`) | `issue.issue_id` | `baseline_head_sha` (worker_pool.py:373) |
| `MergeCoordinator` finalize | None | `result.issue_id` | Not available |
| Orchestrator pending-merge | None | `info.issue_id` | Not available |
| Orchestrator orphan sweep | None (orphans belong to past sessions) | Recoverable from path regex `worker-([a-z]+-\d+)-\d{8}-\d{6}` (worktree_utils.py:432) | Not recoverable |
| Loop create/cleanup | None (loop CLI not wrapped in `cli_event_context`) | None — use `loop_name` | `_base_commit` (loop/run.py:436-446) |

**Insight**: `session_id` is `None` for ALL worktree producer sites today
(none are wrapped in `cli_event_context`). This confirms ENH-2509's
stated expectation that worktree rows will have `session_id=NULL`.
Orphan rows remain useful for inventory even without attribution.

### Patterns to Follow

- **Recorder shape** — mirror `record_test_run_event` at
  `session_store.py:1352`: keyword-only args, JSON-in-column for
  `detail`, FTS index via `_index(...)` at line 705.
- **Best-effort contract (modern)** — internal
  `try/except sqlite3.Error: logger.warning(...)` inside the recorder
  (`skill_event_context` at `session_store.py:1108-...`). Call sites do
  NOT need their own `contextlib.suppress`.
- **Reader shape** — `_connect_readonly` + `try/except sqlite3.Error →
  return []` pattern (`history_reader.py:256-277`). Never raises.
- **CLI `--kind session_lifecycle`** — `cli/session.py:103,115` use
  `choices=list(VALID_KINDS)`; adding the kind in `VALID_KINDS`
  propagates to both `recent` and `search` parsers automatically.
- **Per-op `dry_run=True`** — orphan cleanup (orchestrator.py:318-327)
  MUST NOT emit a recorder row; no op was performed.
- **GitLock** — every `git worktree add`/`remove` in parallel goes
  through `self._git_lock.run(...)`. The recorder is not a git op and
  does not need the lock; place it after the git call returns
  successfully.

### Decision Point — ENH-2495 Coordination

The research uncovered a real coordination issue: this issue assumes
ENH-2495 (the parent table) is already in place, but it is not. Three
viable resolutions:

**Option A**: Co-implement — expand ENH-2509's PR to absorb ENH-2495's
schema, recorder, and reader work (Phase 1 of the Implementation Steps
above). Single coordinated change; both ship together. Larger diff but
no blocking dependency.

**Option B**: Wait — block ENH-2509 until ENH-2495 lands first.
Sequential, but ENH-2509's wiring sites have nothing to call in the
interim and the worktree history gap persists.

**Option C**: Land ENH-2509 first as the *first* lifecycle-events
consumer — implement the full schema in this issue's scope, then
ENH-2495 widens further with the handoff/compaction/sweep/end events.
Reverses the parent/child ordering but matches the actual dependency
graph.

**Recommended**: Option A — co-implement. The widening is
conceptually cleanest when both halves land together; the diff is
small (one migration + one recorder + one new column entry), and it
avoids the cross-issue review burden of split landings.

## Session Log
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:refine-issue` - 2026-07-16T16:48:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`