---
id: ENH-2866
title: Record dequeue-time commit SHA at orchestrator dequeue and worktree creation
type: ENH
priority: P2
status: done
discovered_by: epic-review
discovered_date: 2026-07-27
epic: EPIC-2856
parent: EPIC-2856
labels:
- rework
- verification
- observability
blocks:
- ENH-2853
confidence_score: 98
outcome_confidence: 61
reconcile_attempted: true
score_complexity: 12
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 9
size: Very Large
decision_needed: false
outcome_gate_waived: true
completed_at: '2026-08-02T02:15:37Z'
---

# ENH-2866: Record dequeue-time commit SHA at orchestrator dequeue and worktree creation

## Summary

Nothing in little-loops records the commit SHA a work item started from. Every
orchestrator — `autodev.yaml`'s `dequeue_next`, `ll-parallel`'s per-issue
worktree creation, `ll-sprint`'s waves — begins work against some tree state and
then discards the fact. (Worktree-mode `ll-sprint` waves delegate execution to
the same `ParallelOrchestrator` as `ll-parallel` — `cli/sprint/run.py:23` — so
stamping `ll-parallel`'s worker creation covers those transitively; the
sequential in-place branch is covered separately via
`process_issue_inplace()` — see § Scope Boundaries, decision 2.)

Stamp that SHA at the point work is dequeued, in a location downstream checks
can read. Carved out of ENH-2853, where it was one of eight workstreams and the
only one that is independently landable and independently useful.

Two capture points cover all four orchestrators: `ll-parallel`'s per-issue
worktree creation, and `process_issue_inplace()` (shared by `ll-auto` and
`ll-sprint`'s sequential branch). `autodev.yaml` is covered transitively —
its `implement_current` state shells out to `ll-auto --only "$CURRENT"`
(`autodev.yaml:833`), so every issue autodev implements already produces a
stamped `orchestration_runs` row (§ Scope Boundaries, decision 3).

## Motivation

"What did this change start from?" is the base-state question underneath several
things this epic wants:

- ENH-2853's pre-patch test-failure check needs a base tree to run candidate
  tests against. Without a stamp, its primary path is dead code and every run
  silently takes the merge-base fallback — which is wrong whenever a
  verification step spans multiple commits (routine under `ll-auto` and
  `ll-sprint`), and `HEAD~1` is wrong for the same reason.
- FEAT-2855's maintainability windows and any rework-rate measurement are more
  precisely attributable when a run's starting tree is known rather than inferred
  from commit timestamps.

Landing the stamp first means ENH-2853 exercises its real path from day one
instead of shipping a fallback and a TODO.

## Current Behavior

No orchestrator records the commit SHA a work item started from.
`ll-parallel` delegates worktree lifecycle to
`little_loops.parallel.worker_pool` / `orchestrator`, which call the shared
`setup_worktree()` primitive; no SHA is captured at the point a per-issue
worker's worktree is created. A downstream consumer asking "what tree did this
change start from?" has only `HEAD~1` or a merge-base guess, both of which are
wrong whenever a step spans multiple commits.

## Expected Behavior

Each orchestrator writes the dequeue-time SHA — plus whether the tree was dirty
— at the moment it takes work, before anything mutates the tree or the issue
file. A single reader helper resolves that stamp for a run and returns `None`
when absent, so consumers implement the merge-base fallback once and identically
rather than each rolling their own. The stamp is persisted onto the existing run
record so it outlives the run directory. An orchestrator or hand-run loop that
does not stamp keeps working unchanged.

## Proposed Change

1. **`autodev.yaml` — no stamp; covered transitively** (decision 3,
   2026-08-01). A per-state stamp there is unimplementable as originally
   drafted: `dequeue_next` fires once per issue (~20 states route back to it),
   but `loop_runs` is one row per run (`run_id TEXT NOT NULL UNIQUE`,
   `session_store/schema.py:554`) with no issue dimension, so a run-dir file
   could only ever persist the last issue's SHA — and no *state* calls
   `record_loop_run_summary` anyway; `FSMExecutor._finish()` does, generically
   (`fsm/executor.py:3111-3126`). `implement_current` shells out to
   `ll-auto --only` (`autodev.yaml:833`), so site 2 below stamps every
   autodev-implemented issue, per-issue, at a strictly better moment. See
   § Scope Boundaries, decision 3.
2. **The stamp is WRITTEN at dequeue, not at end-of-run** (decision 4,
   2026-08-01 — the correctness fix that makes this issue useful at all). All
   three existing `record_orchestration_run(...)` call sites fire *after* the
   issue finishes: `issue_manager.py:1691` (after `process_issue_inplace()`
   returns), `orchestrator.py:1044` via `_on_worker_complete` (L1072/L1245),
   and `cli/sprint/run.py:713`/`879` (after `issue_result` exists). ENH-2853's
   pre-patch check runs *during* that same issue's verification step, so a
   stamp persisted only at completion is never readable by its only consumer.
   Each capture site therefore performs an **early upsert at dequeue** —
   `record_orchestration_run(..., status="running", started_at=<now>,
   base_sha=…, base_dirty=…)` — and the existing terminal call later upserts
   the outcome onto the same `(run_id, issue_id)` row. This is what makes the
   COALESCE-on-retry rule in Design Notes load-bearing rather than merely
   defensive. See § Scope Boundaries, decision 4, for the two behavioral
   consequences (`ended_at` semantics for an in-flight row, and permanent
   `status='running'` rows for crashed runs).
3. **`ll-parallel`** — capture the SHA at per-issue worktree creation.
   `worker_pool.py` already computes `baseline_head_sha =
   self._get_main_head_sha()` (`L362`) immediately before `_setup_worktree(...)`
   (`L367`); carry that value (plus a new inline dirty-check) through a
   new `base_sha`/`base_dirty` pair on `WorkerResult`
   (`parallel/types.py:51-94`), threaded into every `WorkerResult(...)`
   construction **inside `_process_issue`** (success and failure paths alike).
   `orchestrator.py`'s `_record_orchestration_result()` (`L1034-1055`)
   currently forwards only `branch=result.branch_name` to
   `record_orchestration_run(...)` — it must also forward
   `result.base_sha`/`result.base_dirty`, since that call is the actual
   missing link to persistence, not just the capture site. Per decision 4 the
   `ll-parallel` early upsert cannot ride on `WorkerResult` (which only exists
   once the worker finishes): it is issued from `_process_issue` directly,
   right after `baseline_head_sha` is computed, using the pool's
   `run_id`/`driver`.
4. **`ll-auto` + `ll-sprint` sequential path** — `issue_manager.py`'s own
   sequential dequeue loop routes through neither `autodev.yaml` nor
   `ll-parallel`, and `cli/sprint/run.py`'s
   `_run_issue_with_wall_clock_timeout()` calls the same
   `process_issue_inplace()` directly. The existing `_baseline_sha` local
   (`L936-941`) is captured *after* Phase 1 (ready/verify) already ran and
   is not reusable; add a fresh `git rev-parse HEAD` (plus dirty-check)
   inside `process_issue_inplace()` before Phase 1 starts (`L646-648`),
   expose it as `base_sha`/`base_dirty` fields on `IssueProcessingResult`,
   and have each caller — `ll-auto`'s `AutoProcessor._process_issue`
   (`issue_manager.py:1691`) and `cli/sprint/run.py`'s two
   `record_orchestration_run(driver="ll-sprint")` calls (`L713`, `L879`) —
   forward those fields via `record_orchestration_run(...)` (scope decision
   2, 2026-07-31). Per decision 4 the same two fields also feed the
   dequeue-time early upsert issued from inside `process_issue_inplace()`,
   which is what makes the stamp readable mid-run.
5. **Reader helper** — one function that resolves a base SHA from
   `orchestration_runs`, returning the stamp when present and `None` when not,
   so consumers implement the merge-base fallback once and identically rather
   than each rolling their own lookup. Single-table by construction (decision 3
   removed the `loop_runs` path), so there is no
   which-table-does-this-`run_id`-belong-to dispatch to guess at. **`run_id` is
   optional** (decision 4): it is a process-local `uuid4().hex`
   (`issue_manager.py:1282`, `orchestrator.py:123`) that is never exported to
   env, run-dir, or subprocess, so ENH-2853 — which hosts the check in an FSM
   oracle loop, a separate process — cannot supply it. When omitted the reader
   resolves the most recent stamped row for the issue.
6. **Persist to `.ll/history.db`** where a run is already recorded, so the stamp
   outlives the run directory. Concretely: additive nullable columns
   (`base_sha TEXT`, `base_dirty INTEGER`) on `orchestration_runs`
   (`session_store/schema.py:523`) — the one table all three stamped drivers
   (`ll-parallel`, `ll-auto`, `ll-sprint`) already write per-issue rows to —
   via a new `_MIGRATIONS` entry in `session_store/schema.py` (NULL =
   "unstamped", matching the reader's `None` contract). No new table, and no
   `loop_runs` change.

## Design Notes

- **Additive only.** `setup_worktree()` / `cleanup_worktree()` are called
  directly by `scripts/little_loops/fsm/executor.py`,
  `scripts/little_loops/cli/loop/run.py`,
  `scripts/little_loops/parallel/orchestrator.py`, and the epic-branch verify
  path. Any signature change must be backward compatible or those four call
  sites break.
- **The stamp is advisory, never a hard dependency.** A consumer that finds no
  stamp falls back to merge-base and *says which base it used*. An orchestrator
  that hasn't been taught to stamp (or a hand-run loop) must keep working.
- **Resolve the SHA before any mutation.** In `process_issue_inplace()` this
  means before Phase 1 writes to the issue file (`issue_manager.py:646-648`);
  in `worker_pool.py` before `_setup_worktree()` (`L367`). A stamp taken after
  the first commit of the work item describes the wrong tree.
- **Persist it before any mutation too — capture time ≠ write time was the
  original design's fatal flaw** (decision 4, 2026-08-01). Every existing
  `record_orchestration_run(...)` call fires at end-of-issue. ENH-2853 reads
  mid-issue. Resolving the SHA early but only persisting it late leaves the
  reader returning `None` on every single run — the issue would land, pass its
  own tests, and still leave ENH-2853's primary path dead. The early upsert is
  therefore part of the contract, not an optimization: **an AC asserts the row
  is readable while the issue is still in flight**, not merely after it
  completes.
- **`ended_at` on an in-flight row.** `record_orchestration_run` does
  `effective_ended_at = ended_at or _now()` (`writers.py:1213`), so a naive
  dequeue-time call stamps `ended_at` at dequeue. The terminal upsert
  overwrites it, so a completed run is unaffected — but an abandoned run would
  read as `ended_at == started_at`. The early-upsert path must leave `ended_at`
  NULL for an in-flight row; adjust the `or _now()` default so it applies only
  when a terminal status is being written, or pass an explicit sentinel.
- **`started_at` must survive the terminal upsert — it does not today**
  (review 2026-08-01). The DO UPDATE clause sets
  `started_at=excluded.started_at` (`writers.py:1227`) and **none of the three
  terminal call sites pass `started_at`** (`issue_manager.py:1691`,
  `orchestrator.py:1044`, `cli/sprint/run.py:713`/`879` — verified). So the
  dequeue-time `started_at` written by the early upsert is nulled the instant
  the issue completes. That is harmless today only because no row has ever had
  a `started_at`; under decision 4 it silently discards the one timestamp the
  early write earns for free. It is actively harmful for the abandoned-run case
  decision 4 exists to serve: both `recent_orchestration_runs` (`history_reader.py:1748`)
  and `aggregate_orchestration_runs` (`history_reader.py:1788`) window `since`
  on `COALESCE(ended_at, started_at)`, so a row that takes any second upsert
  without `started_at` has *both* timestamps NULL and drops out of every
  windowed query. Give `started_at` the same
  `started_at=COALESCE(excluded.started_at, started_at)` treatment as
  `base_sha`/`base_dirty`. (Forwarding `started_at` from all three terminal
  callers is the alternative, but it is three edits to preserve a value the
  write-once COALESCE preserves in one.)
- **The early upsert also creates a `search_index` FTS row** with the text
  `"<driver> <run_id> <issue_id> running"` (`writers.py:1246-1252`). This is
  benign — the terminal upsert deletes and recreates the row in the same
  transaction — but it means a mid-run `ll-session search` can surface a
  `running` orchestration row where none existed before. Expected, not a defect.
- **`ll-auto`'s write is gated on `if not self.dry_run`**
  (`issue_manager.py:1680`). The dequeue-time early upsert inherits the same
  guard — a dry run must not become the one mode that persists rows.
- **Detached/dirty trees.** Record the SHA plus whether the tree was dirty at
  stamp time; a dirty base means a pre-patch reconstruction is approximate and
  the consumer should be able to say so rather than assert a clean comparison.
- **"Dirty" excludes untracked files.** Use
  `git status --porcelain --untracked-files=no`. ENH-2853's reconstruction is
  checkout-based, so only *tracked* modifications make the base approximate; an
  untracked scratch file does not. The cited `merge_coordinator.py:151-173`
  shape is the subprocess idiom to copy, not its flag set — it counts untracked
  (`??`) lines because it is answering a different question.
- **Normalize a failed `git rev-parse` to `None`, never `""`.**
  `worker_pool._get_main_head_sha()` returns the empty string on failure
  (`worker_pool.py:1528`; see the existing
  `test_get_main_head_sha_returns_empty_on_failure`). Threading that straight
  through writes `''` rather than NULL, which silently breaks the
  NULL-means-unstamped contract — the reader would hand consumers a falsy
  string instead of `None` and the merge-base fallback would never engage. Every
  capture site coerces falsy → `None` before it reaches `WorkerResult` /
  `IssueProcessingResult`.
- **The UPSERT must not clobber a stamp on retry.**
  `record_orchestration_run` is an `ON CONFLICT(run_id, issue_id) DO UPDATE SET
  … head_sha=excluded.head_sha` (`session_store/writers.py:1223-1228`), and its
  own docstring states retries reuse `(run_id, issue_id)`. A later call passing
  `base_sha=None` would null a previously stamped value. The new columns use
  `base_sha=COALESCE(excluded.base_sha, base_sha)` (and the same for
  `base_dirty`) in the DO UPDATE clause — deliberately unlike the existing
  `head_sha`/`branch` pair, which are end-of-run values where last-write-wins is
  correct. A dequeue-time stamp is write-once.
- No LLM involvement — this is a `git rev-parse` and a file write.
- **`ll-auto` is a third dequeue site and was missing from the stamp set** (placement review, 2026-07-30). This issue's Motivation names `ll-auto` as a case where a verification step spans multiple commits and merge-base is wrong — but the Proposed Change stamps only `autodev.yaml`'s `dequeue_next` and `ll-parallel`'s worker creation. `ll-auto` routes through neither: `cli/auto.py` → `issue_manager.py`'s `AutoProcessor` is its own sequential dequeue loop, not a wrapper over `autodev.yaml` (a grep of `issue_manager.py` for `autodev` returns only a comment at L905). As written, the one orchestrator the Motivation calls out would always take ENH-2853's merge-base fallback. Stamp `issue_manager.py`'s per-issue dequeue as a third site. Check first whether the `_baseline_sha` it already computes for `verify_work_was_done()` (~L1072, ~L1109) is the same value — if so this is a persistence change, not a new capture.
- **`autodev.yaml`'s `dequeue_next` was a fourth stamp site — RESOLVED:
  removed, covered transitively** (design review 2026-08-01). Three findings
  killed it: (a) `dequeue_next` runs once per issue but `loop_runs` holds one
  row per run with no issue dimension, so the run-dir file
  `autodev-dequeue-sha.txt` is overwritten each iteration and only the last
  issue's SHA could persist; (b) no loop *state* calls
  `record_loop_run_summary` — `FSMExecutor._finish()` does, generically at
  archival (`fsm/executor.py:3111-3126`), with no knowledge of loop-specific
  run-dir filenames, so the drafted read-back had no implementer; (c)
  `implement_current` invokes `ll-auto --only "$CURRENT"` (`autodev.yaml:833`),
  which reaches `process_issue_inplace()` and writes a per-issue
  `orchestration_runs` row anyway. The transitive stamp is also *more* correct
  for ENH-2853: it is taken after refine/wire/size-review have committed their
  issue-file churn and immediately before the implementation patch, which is
  the base a pre-patch test check actually wants. See § Scope Boundaries,
  decision 3.
- **`ll-queue run` is a fourth dequeue site — RESOLVED: exempted** (placement review 2026-07-30; decided 2026-07-31). FEAT-2906's `ll-queue run` serially dequeues `pending` entries, which makes it an orchestrator by this issue's own definition — but it has no `session_store.writers` path and its `LOOP` entries are stamped by the loop they drive. See § Scope Boundaries, decision 1, and decision fragment `61df2043` in `.ll/decisions.d/`.

## Program Design

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Signatures

- `WorkerResult` (`scripts/little_loops/parallel/types.py:51-94`) gains two
  new fields, added after the existing `epic_branch: str | None = None`
  (line 94), both defaulting to `None`:

  - `base_sha: str | None`
  - `base_dirty: bool | None`

  Both `to_dict()` (lines 92-116) and `from_dict()` (lines 119-140) hand-list
  every field explicitly and must be extended in lockstep or the values
  silently drop on JSON round-trip (`WorkerResult` is serialized across the
  worker-subprocess boundary).

- `worker_pool.py`'s `_process_issue()` (`L319-709`) already computes
  `baseline_head_sha = self._get_main_head_sha()` at `L362`, before
  `self._setup_worktree(...)` (`L367`). Add a sibling dirty-check inline
  (no shared helper exists — see Design Notes), following the
  `git status --porcelain --untracked-files=no` shape at
  `merge_coordinator.py:151-173` (the subprocess idiom, not its flag set — see
  Design Notes on why untracked is excluded), producing
  a local `baseline_dirty: bool`. Coerce a falsy `baseline_head_sha` to `None`
  here — `_get_main_head_sha()` returns `""` on failure, and `""` is not NULL.
  Issue the decision-4 early upsert immediately after both locals exist, then
  thread them into **every `WorkerResult(...)` construction inside this
  method** — 12 sites at `L409, 424, 441, 457, 485, 506, 570, 628, 643, 665,
  679, 696` — the success path and every early-return failure path alike,
  since a failed worker's base state is equally worth stamping.

  **Not the `WorkerResult(...)` at `L297`**: that construction lives in
  `_handle_completion()` (`L283-316`), a different method with no
  `baseline_head_sha` in scope — it is the fallback for a worker future that
  raised. It stays unstamped (`base_sha=None`), which is correct: the early
  upsert already recorded the stamp for that issue, and COALESCE keeps the
  terminal upsert from nulling it. A prior draft of this section listed `~L296`
  among the stampable sites; it is not one.

- `_record_orchestration_result(result: WorkerResult, status: str, failure_reason: str | None) -> None`
  (`scripts/little_loops/parallel/orchestrator.py:1034-1055`) — extend its
  inner `record_orchestration_run(...)` call (currently forwards only
  `branch=result.branch_name`, no SHA at all) to also pass
  `result.base_sha` and `result.base_dirty`.

- `record_orchestration_run(..., base_sha: str | None = None, base_dirty: bool | None = None) -> bool`
  (`scripts/little_loops/session_store/writers.py:1181-1208`) — add these two
  keyword-only params after the existing `branch` (line 1195); thread through
  to the `INSERT ... ON CONFLICT DO UPDATE` column list and bound-parameter
  tuple (`writers.py:1219-1244`), following the existing `head_sha`/`branch`
  pair. Also adjust the `effective_ended_at = ended_at or _now()` default at
  `L1213` so an in-flight (`status="running"`) row leaves `ended_at` NULL —
  see Design Notes. **The DO UPDATE clause differs from that pair**: use
  `base_sha=COALESCE(excluded.base_sha, base_sha)` and
  `base_dirty=COALESCE(excluded.base_dirty, base_dirty)` so a retry upsert
  that passes no stamp cannot null a recorded one (see Design Notes).
  **`started_at` gets the same COALESCE** — `started_at=COALESCE(excluded.started_at,
  started_at)` — because no terminal caller passes it and the current
  last-write-wins clause would null the dequeue-time value (see Design Notes).
  `record_loop_run_summary` is **unchanged** — decision 3 removed the
  `loop_runs` path.

- Schema migration — new `_MIGRATIONS` entry appended after the
  `failure_terminal` entry (`schema.py:906-917`, current
  `SCHEMA_VERSION = 37`, `schema.py:21`; the new entry becomes v38), adding:

  - `orchestration_runs.base_sha: str`
  - `orchestration_runs.base_dirty: int`

  via `ALTER TABLE ... ADD COLUMN` statements, both nullable (NULL =
  unstamped — orchestrator predates this stamp or opted out; readers fall
  back to merge-base). Fix-forward only, matching the `failure_terminal`
  precedent: existing rows are not backfilled. No `loop_runs` columns.

- `read_base_sha(issue_id: str, *, run_id: str | None = None, db: Path | str = DEFAULT_DB_PATH) -> str | None`
  (new — `scripts/little_loops/history_reader.py`, alongside the existing
  `recent_orchestration_runs` (`L1720`) and `aggregate_orchestration_runs`
  (`L1763`)) — modeled on the None-when-absent contract of
  `read_adapter_gen_version()` (`init/writers.py:790-809`): never raises,
  returns `None` on missing row, NULL column, or any query error.

  **Placement corrected 2026-08-01 (review).** A prior draft put this in
  `scripts/little_loops/session_store/queries.py`. That module is search /
  `recent()` / `export_history()` plumbing: it connects read-write via
  `_pkg.connect` and lets `sqlite3.Error` escape, the opposite of this
  function's never-raise contract. Every existing typed read of
  `orchestration_runs` already lives in `history_reader.py`, which has the
  `_connect_readonly` helper and the degrade-to-empty error handling this
  reader needs. Putting it in `queries.py` would split one table's read
  surface across two modules and force the reader to hand-roll what
  `history_reader` already provides. Argument order follows that module's
  convention (positional identity, keyword-only `db=`), not
  `session_store.writers`'s `db_path`-first shape.

  Single-table by construction: `SELECT base_sha FROM orchestration_runs`.
  With `run_id` supplied, `WHERE run_id = ? AND issue_id = ?` — the
  `UNIQUE(run_id, issue_id)` constraint (`schema.py:537`) makes that the row
  identity. Deliberately **not** a dual-table dispatch: with `loop_runs` out of
  scope there is no ambiguity about which table a caller's `run_id` belongs to,
  which is what makes the "same reader for every orchestrator" AC true by
  construction rather than by probing.

  **`run_id` is optional, and that is load-bearing** (decision 4, 2026-08-01).
  It is a process-local `uuid4().hex` (`issue_manager.py:1282`,
  `orchestrator.py:123`) never written to env, run-dir, or any subprocess
  argv. ENH-2853 hosts the pre-patch check in an FSM oracle loop — a separate
  process — so it can never supply one; and under decision 3's transitive path,
  `implement_current`'s `ll-auto --only` subprocess mints its *own* `run_id`,
  so even plumbing autodev's through would not match the row. A
  required-`run_id` reader is unreachable by its only consumer. When `run_id`
  is omitted the reader resolves the most recent stamp for the issue:
  `WHERE issue_id = ? AND base_sha IS NOT NULL ORDER BY id DESC LIMIT 1`.
  The `base_sha IS NOT NULL` filter matters — without it an unstamped later row
  would shadow a stamped earlier one and the reader would report `None` for an
  issue that was in fact stamped.

- `issue_manager.py` — new `git rev-parse HEAD` (and a dirty-check) call
  inserted inside `process_issue_inplace()` before `Phase 1: Verifying issue`
  starts (`L646-648`), separate from the existing `_baseline_sha` local
  (`L936-941`, computed *after* Phase 1 and used only for
  `verify_work_was_done()` — not reusable for this stamp per the Codebase
  Research Findings above). `IssueProcessingResult` (`issue_manager.py:563-574`)
  gains `base_sha: str | None = None` / `base_dirty: bool | None = None`
  fields carrying the stamp back to callers (scope decision 2, 2026-07-31):
  `ll-auto`'s `AutoProcessor._process_issue` (`L1691`) and
  `cli/sprint/run.py`'s two `record_orchestration_run(driver="ll-sprint")`
  calls (`L713`, `L879`) both forward them.

  Per decision 4, `process_issue_inplace()` also issues the dequeue-time early
  upsert itself, right after resolving the two values — it is the only place
  that runs before Phase 1 for both `ll-auto` and `ll-sprint`-sequential. That
  requires `run_id`/`driver` **and a database path** to reach
  `process_issue_inplace()`. Its current signature (`issue_manager.py:577-590`)
  has none of the three: `run_id` and the DB path live on `AutoProcessor`
  (`self.run_id` / `self.db_path`, `L1281-1282`) and `history_db` is a
  `cli/sprint/run.py` local. Add all three as optional keyword params
  (`run_id: str | None = None`, `driver: str | None = None`,
  `db_path: Path | str | None = None`) — **the early upsert is skipped unless
  all three are present**, so any other caller keeps today's behavior and only
  the caller-side terminal forwarding applies. A prior draft named only
  `run_id`/`driver`, which would have left the write with no destination.
  Honor `dry_run` here as `AutoProcessor` does at `L1680`.

### Call Path

- **`ll-parallel`**: `worker_pool._process_issue()` (`L362`) →
  `_get_main_head_sha()` + new dirty check → **early
  `record_orchestration_run(status="running", base_sha=, base_dirty=)`** (row
  now exists and is readable mid-run) → `WorkerResult(base_sha=, base_dirty=)`
  at every return site inside `_process_issue` → `orchestrator.py`'s
  `_on_worker_complete()` → `_record_orchestration_result()` → terminal
  `record_orchestration_run(base_sha=, base_dirty=)` COALESCE-upsert onto the
  same row.
- **`autodev.yaml`**: no capture of its own. `implement_current` →
  `ll-auto --only "$CURRENT"` subprocess (`autodev.yaml:833`) → the `ll-auto`
  path below → `orchestration_runs` row with `driver="ll-auto"`. Nothing to
  build for this orchestrator.
- **`ll-auto` / `ll-sprint` sequential**: `process_issue_inplace()`, before
  `L646` → `git rev-parse HEAD` + dirty check → new local (not
  `_baseline_sha`) → **early `record_orchestration_run(status="running",
  base_sha=, base_dirty=)`** → `IssueProcessingResult(base_sha=, base_dirty=)`
  → each caller forwards into its own terminal
  `record_orchestration_run(base_sha=, base_dirty=)` call
  (`issue_manager.py:1691`; `cli/sprint/run.py` `L713` and `L879`).
- **Reader**: any consumer (ENH-2853, running in a separate oracle-loop
  process) → `read_base_sha(db_path, issue_id=)` with no `run_id` → most-recent
  stamped `orchestration_runs` row for that issue → `None` (fall back to
  merge-base, say so) or a SHA string. In-process callers that do hold a
  `run_id` may pass it for an exact-row lookup.

## Acceptance Criteria

- [ ] `ll-parallel` records the stamp at per-issue worktree creation, in the
      worker's state rather than inside the shared `setup_worktree()` primitive.
- [ ] `setup_worktree()` / `cleanup_worktree()` signatures remain backward
      compatible; the four existing direct call sites are unchanged or updated
      additively.
- [ ] A single reader helper resolves a base SHA and returns `None` when
      unstamped, so the merge-base fallback is implemented once. It is callable
      **without a `run_id`** — a test resolves a stamp given only `issue_id`,
      proving an out-of-process consumer (ENH-2853's oracle loop) can reach it.
      When several rows exist for one issue, the most recent *stamped* row
      wins; a test covers an unstamped later row not shadowing a stamped
      earlier one.
- [ ] Whether the tree was dirty at stamp time is recorded alongside the SHA,
      computed with `--untracked-files=no` so an untracked scratch file does not
      mark the base dirty.
- [ ] The stamp is persisted to `.ll/history.db` as additive nullable columns on
      the existing `orchestration_runs` rows, not a new table and not on
      `loop_runs`; NULL means unstamped.
- [ ] A failed `git rev-parse` is persisted as NULL, never as an empty string —
      a test asserts the reader returns `None` (not `""`) when
      `_get_main_head_sha()` fails.
- [ ] A second `record_orchestration_run(...)` upsert for the same
      `(run_id, issue_id)` that passes no `base_sha` leaves the previously
      recorded stamp intact. A test covers this retry path.
- [ ] An orchestrator or hand-run loop with no stamp continues to work
      unchanged.
- [ ] Tests cover: the stamp written at `ll-parallel` worker creation, the
      reader returning `None` when unstamped, and the dirty-tree flag.

_Added 2026-07-30 (placement review) — see Design Notes:_

- [ ] `ll-auto` records the stamp at its own per-issue dequeue in
      `issue_manager.py`, resolved before Phase 1 mutates the issue file. A test
      covers it, asserting `orchestration_runs.base_sha` is non-NULL after an
      `ll-auto` run.
- [ ] All stamped drivers write into the same column on the same table, so the
      *same* reader helper resolves every one — no per-orchestrator lookup
      logic and no table dispatch.
- [ ] An `autodev.yaml` run produces a stamped row per implemented issue via its
      `ll-auto --only` subprocess, with no autodev-specific capture code. A test
      asserts `autodev.yaml` writes no `autodev-dequeue-sha` run-dir artifact
      (naming the removed design's specific artifact, rather than grepping for
      `rev-parse`, which a legitimate future change would trip).
- [ ] `ll-queue run` is either stamped or explicitly exempted in
      § Scope Boundaries with a stated reason. _(Resolved 2026-07-31:
      exempted — see § Scope Boundaries, decision 1.)_

_Added 2026-07-31 (scope decision 2) — see Scope Boundaries:_

- [ ] `process_issue_inplace()` captures the stamp before Phase 1 and returns
      it via `IssueProcessingResult.base_sha`/`.base_dirty`;
      `cli/sprint/run.py`'s sequential path forwards both fields into its
      `record_orchestration_run(driver="ll-sprint")` calls. A test covers the
      sprint-sequential forwarding.

_Added 2026-08-01 (decision 4, write-timing) — see Scope Boundaries:_

- [ ] The stamp is **readable while the issue is still in flight**, not only
      after it completes. For each stamped driver a test asserts that after the
      dequeue-time write and before any terminal
      `record_orchestration_run(...)`, `read_base_sha(db, issue_id=...)`
      returns the SHA. This is the AC that keeps ENH-2853's primary path from
      being dead code.
- [ ] The terminal upsert for the same `(run_id, issue_id)` replaces `status`,
      `duration_s`, `ended_at`, `head_sha`, and `branch` while preserving
      `base_sha`/`base_dirty` — one row per issue, not two. A test asserts the
      row count is 1 after both writes.
- [ ] An in-flight row leaves `ended_at` NULL; only a terminal write populates
      it. A test asserts an abandoned run does not read as
      `ended_at == started_at`.
- [ ] A `--dry-run` `ll-auto` invocation writes no `orchestration_runs` row at
      dequeue, matching the existing `if not self.dry_run` guard on the
      terminal write.

_Added 2026-08-01 (review) — see Design Notes, "`started_at` must survive":_

- [ ] The terminal upsert preserves the dequeue-time `started_at`. A test
      asserts that after an early upsert followed by a terminal
      `record_orchestration_run(...)` that passes no `started_at` (as all three
      existing call sites do), the row's `started_at` is still the dequeue
      timestamp and is not NULL — so the row stays inside
      `recent_orchestration_runs` / `aggregate_orchestration_runs`' `since`
      windows, which key on `COALESCE(ended_at, started_at)`.
- [ ] The reader helper lives in `history_reader.py` alongside the existing
      `orchestration_runs` reads, not in `session_store/queries.py`, and never
      raises — a test asserts it returns `None` rather than propagating a
      `sqlite3.Error` against a missing or malformed DB.

## Integration Map

### Files to Modify

_`issue_manager.py` added 2026-07-30 (placement review) — see Design Notes,
"`ll-auto` is a third dequeue site."_

- ~~`scripts/little_loops/loops/autodev.yaml`~~ — **not modified** (decision 3,
  2026-08-01); covered transitively via `implement_current`'s
  `ll-auto --only` shell-out at ~L829
- `scripts/little_loops/parallel/worker_pool.py` /
  `scripts/little_loops/parallel/orchestrator.py` — per-issue worktree creation
  call sites
- `scripts/little_loops/issue_manager.py` — `ll-auto`'s own sequential dequeue,
  which routes through neither of the two sites above. Stamp at the point the
  issue is taken, before Phase 1 mutates the issue file; check whether the
  existing `_baseline_sha` (~L1072, ~L1109) already holds the right value
- `scripts/little_loops/worktree_utils.py` — only if an additive parameter is
  the cleanest carrier; prefer stamping at the caller
- `scripts/little_loops/history_reader.py` — the new `read_base_sha()` reader,
  alongside the existing `recent_orchestration_runs` / `aggregate_orchestration_runs`
  (placement corrected 2026-08-01; see Program Design)
- `scripts/little_loops/session_store/schema.py` — the `_MIGRATIONS` entry adding
  the nullable stamp columns — and `scripts/little_loops/session_store/writers.py`
  — persist the stamp on the run record (note: `session_store.py` was split into
  the `session_store/` package by ENH-2890; the former flat-module line refs in
  this issue's research are stale)

_Wiring pass added by `/ll:wire-issue` (2026-07-30):_
- `scripts/little_loops/parallel/types.py` — `WorkerResult` (dataclass ~L52-141)
  needs the new `base_sha`/`base_dirty` fields, and its `to_dict()`/`from_dict()`
  hand-list every field explicitly — both must be extended or the new fields
  silently drop on JSON round-trip
- `scripts/little_loops/parallel/orchestrator.py` — `_record_orchestration_result()`
  (~L1016-1037) is the actual write path to the DB, and **today it forwards only
  `branch=result.branch_name` — no git/SHA context at all** — to its
  `record_orchestration_run(...)` call. `worker_pool.py` already computes
  `baseline_head_sha` before `_setup_worktree()` (per the existing Codebase
  Research Findings above), but that value never reaches this call. Without
  updating `_record_orchestration_result()` to pass
  `base_sha=result.base_sha, base_dirty=result.base_dirty`, the `ll-parallel`
  stamp is captured but never persisted — this is the actual missing link, not
  just "wire an existing value through" at the capture site alone
- `scripts/little_loops/cli/sprint/run.py` — `_run_issue_with_wall_clock_timeout()`
  (~L49) calls `process_issue_inplace()` **directly**, sequentially, with no
  worktree — a code path distinct from `ParallelOrchestrator`. Its result feeds
  two separate `record_orchestration_run(...)` calls (`~L694`, `~L842`,
  `driver="ll-sprint"`) that pass no `head_sha`/base SHA today. This contradicts
  the Scope Boundaries claim below that "`ll-sprint run` delegates to the same
  `ParallelOrchestrator` as `ll-parallel`" — that delegation is true for
  worktree-mode sprint execution, but this sequential in-place branch is a
  distinct, currently-unstamped surface. Worth resolving explicitly in Scope
  Boundaries (stamp it as a variant of the `ll-auto` site, since it also calls
  `process_issue_inplace()` directly, or state why it's exempt) rather than
  leaving the existing "no separate `ll-sprint` stamp is needed" claim
  unqualified. _(Resolved 2026-07-31: in scope — the stamp is captured inside
  `process_issue_inplace()` and returned on `IssueProcessingResult`; this file
  forwards it at both call sites. See § Scope Boundaries, decision 2.)_
- `docs/ARCHITECTURE.md` — the `history.db` schema-versions table (§ "history.db
  schema versions", ~L663-699) is a hand-maintained one-row-per-migration
  changelog; needs a new row for the `base_sha`/`base_dirty` migration,
  following the `v22`/`v23` prose pattern
- `docs/reference/API.md` — `record_orchestration_run` (~L8493) is a
  hand-maintained signature block listing every keyword argument; needs the
  `base_sha`/`base_dirty` params inserted. `record_loop_run_summary` (~L8517)
  is untouched per decision 3

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`issue_manager.py`'s `_baseline_sha` is NOT the value ENH-2866 needs — this
  is a new capture point, not a persistence change.** `_baseline_sha` is
  computed at `issue_manager.py:936-941`, inside the Phase 2 block, via
  `git rev-parse HEAD`. `process_issue_inplace()`'s Phase 1 (ready/verify,
  which can mutate the issue file) starts at `issue_manager.py:646-648` — i.e.
  `_baseline_sha` is captured *after* Phase 1 already ran, not before it as
  this issue's Design Notes hoped. It is also purely a transient local,
  passed only into `verify_work_was_done(baseline_sha=_baseline_sha)`
  (`issue_manager.py:1107`, `1156`) — never persisted. A true dequeue-time
  stamp for `ll-auto` needs a fresh `git rev-parse HEAD` call placed before
  `issue_manager.py:646`, separately persisted.
- **`worker_pool.py` already captures the right value at the right point —
  it just isn't exposed or persisted yet.** `baseline_head_sha =
  self._get_main_head_sha()` runs at `worker_pool.py:361-362`, immediately
  before `self._setup_worktree(...)` at `worker_pool.py:367`.
  `_get_main_head_sha()` (`worker_pool.py:1528-1541` — an earlier draft of this
  line cited `1477-1490`, which is stale) is a `git rev-parse
  HEAD`. Today this value is only used for leak detection
  (`_detect_committed_leaks()`, `worker_pool.py:1566+`) and logged into the
  `worktree_create` session-lifecycle event detail dict as `"parent_sha"`
  (`worker_pool.py:377-388`) — not written to `orchestration_runs`. The
  stamp for this site is closer to "wire an existing value through" than
  "add a new git call." The natural carrier is a new field on `WorkerResult`
  (`parallel/types.py:52-94`, alongside the existing `epic_branch: str |
  None = None` at line 94), since no other longer-lived per-worker state
  struct exists (`WorkerStage` is a per-issue enum in a dict, not a
  dataclass to extend).
- **`orchestration_runs` and `loop_runs` already have `head_sha TEXT` /
  `branch TEXT` columns** (`schema.py:523-544`, `schema.py:553-567`), but
  both are populated at end-of-run, not dequeue-time — reusing `head_sha`
  for the new stamp would conflate two different meanings on the same
  column. The Proposed Change's plan for distinctly-named additive columns
  (`base_sha`, `base_dirty`) is correct and necessary; do not repurpose
  `head_sha`.
- **`ll-queue run`'s actual dequeue site, for the open Scope Boundaries
  decision**: `_drain_once()` in `scripts/little_loops/cli/queue.py:428-507`
  (not a `cli/queue/run.py` submodule — no such path exists). `claim_entry`
  fires at `cli/queue.py:463-465`, dispatch at `472-476`, write-back via
  `update_entry_result` at `498`. `QueueEntry` (`queue_store.py:257-298`)
  has no SHA/dirty field, and `cli/queue.py` never imports or calls
  `session_store.writers` anywhere — unlike the other three sites (which
  all eventually reach `record_orchestration_run`/`record_loop_run_summary`
  via their respective producer paths), a stamp here would need either (a)
  a new field folded into the `result` JSON blob already written back per
  entry, or (b) a first-ever direct call from `cli/queue.py` into
  `session_store.writers`. This is a materially different persistence path
  than the other three sites, not just a fourth call site of the same shape
  — worth weighing when the Scope Boundaries decision is made.
- **No reusable dirty-tree-check helper exists.** A grep for
  `is_dirty`/`worktree_dirty`/`dirty_tree` across `scripts/little_loops`
  returns nothing. Existing dirty-tree checks (`merge_coordinator.py:151-173`,
  `codequery/codegraph.py:107`) each inline their own `git status
  --porcelain` parse rather than calling a shared function — the new
  `base_dirty` capture will need its own inline check too, following that
  same shape (no new git-utility module to build first).
- **Reader-with-None-when-absent contract to model on**:
  `scripts/little_loops/init/writers.py:790-809`
  (`read_adapter_gen_version()`) — three sequential degrade-to-`None` gates
  (file absent / parse error / wrong type), no exception ever escapes, and
  a docstring `Returns:` section spelling out every `None`-triggering
  condition. This is a closer analog than the queue/lock-file example
  because it's a single-stamp read, matching the shape of "resolve a run's
  base SHA."
- **Additive nullable-column migration to model on**: `schema.py:906-917`
  (ENH-2814's `failure_terminal INTEGER` column) — leading comment cites
  the issue ID, documents what NULL means for pre-existing rows, and states
  "fix-forward only... not backfilled" explicitly. The new `base_sha`/
  `base_dirty` migration entry should follow the same comment shape.

### Dependent Files (Callers of the shared worktree primitives)
- `scripts/little_loops/fsm/executor.py` (~L927)
- `scripts/little_loops/cli/loop/run.py` (~L472, `cleanup_worktree` via `atexit`
  ~L535/560)
- `scripts/little_loops/parallel/merge_coordinator.py` (~L1061) — has a private
  `_cleanup_worktree` wrapper; confirm whether it needs updating
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` (~L462, ~L653) —
  calls `verify_epic_branch_before_merge()`

### Similar Patterns
- `autodev.yaml`'s `autodev-pre-readiness.txt` snapshot (FEAT-2751) — run-dir
  handshake-file convention this stamp copies
- `scripts/little_loops/session_store/writers.py:_backfill_commit_events()` (~L813) —
  established `git log` subprocess-invocation shape (timeout, `cwd=repo_root`,
  `capture_output=True, text=True`)
- `scripts/tests/test_worker_pool.py:TestWorkerPoolWorktreeManagement` (~L633, e.g.
  `test_setup_worktree_passes_base_branch_in_feature_mode` ~L963) — closest
  analog for a worker-creation-point test; currently asserts only on
  `git worktree add` argv shape

### Tests
- `scripts/tests/test_autodev_loop.py` — only for the negative guard AC (assert
  `autodev.yaml` grows no SHA-stamping shell action); follow
  `TestDequeueNextPreReadinessSnapshot` (~L172-186), which does
  string-containment assertions against the raw YAML `action:` block rather
  than live execution
- `scripts/tests/test_worker_pool.py`, `scripts/tests/test_orchestrator.py` —
  the latter patches `setup_worktree` at ~7 sites (L1761-1888)
- `scripts/tests/test_session_store_writers.py` / `test_session_store_schema.py` —
  stamp persistence (the flat `test_session_store.py` no longer exists; the suite
  was split alongside the ENH-2890 package split)

_Wiring pass added by `/ll:wire-issue` (2026-07-30):_
- `scripts/tests/test_session_store_schema.py` — new
  `TestSchemaV3xBaseShaColumns`-style class modeled on
  `TestSchemaV15SkillCompletionColumns` (~L1157-1211, the closer analog: an
  additive-`ALTER TABLE ADD COLUMN` migration on an existing table, not a new
  table like `TestSchemaV35ReviewEvents`); use the shared `_bootstrap_schema_at`
  fixture (~L1134-1154) for the upgrade-from-prior-version case
- `scripts/tests/test_session_store_schema.py` hardcodes `37` at roughly ten
  sites — `L650`, `L664-665`, `L716-717`, `L795`, `L812-813`, `L1034-1035` and
  others — all of which break once the new migration entry is appended.
  `SCHEMA_VERSION` is also referenced from seven further test modules
  (`test_session_store_writers.py`, `test_session_store_lifecycle.py`,
  `test_assistant_messages.py`, `test_queue_store.py`,
  `test_hook_session_start.py`, `test_enh_2511_mcp_telemetry.py`,
  `test_enh_2497_agent_type.py`). **Grep the suite for `37` / `SCHEMA_VERSION`
  and bump every site** — an earlier draft of this section named only two
  tests, which materially under-counted the work
- `scripts/tests/test_issue_manager.py` — model the new pre-Phase-1 rev-parse
  stamp test on `TestFallbackVerification.test_baseline_sha_passed_to_verify_work_was_done`
  (~L2797-2850)'s `subprocess.run` mock-dispatch pattern (patches
  `little_loops.issue_manager.subprocess.run`, matches
  `cmd == ["git", "rev-parse", "HEAD"]`)
- `scripts/tests/test_worker_pool.py` —
  `TestWorkerPoolHelpers.test_get_main_head_sha_returns_sha` /
  `_returns_empty_on_failure` (~L1898-1935) is the existing mock pattern
  (`patch.object(worker_pool._git_lock, "run", ...)`) to extend for asserting
  the stamp reaches `WorkerResult`
- `scripts/tests/test_init_core.py` — `test_read_adapter_gen_version_*`
  (~L1249-1271, a 4-gate happy-path/missing/malformed/absent-field template) is
  the closest existing test shape for the new reader helper's tests

_Added 2026-08-01 (decision 4, write-timing):_
- `scripts/tests/test_session_store_writers.py` — the decision-4 ACs land
  mostly here: dequeue-then-terminal upsert leaves one row with `base_sha`
  intact; an in-flight row has NULL `ended_at`; `read_base_sha` resolves with
  `run_id` omitted; an unstamped later row does not shadow a stamped earlier
  one. All are pure writer/reader tests against a temp DB, no orchestrator
  needed
- `scripts/tests/test_issue_manager.py` — a dry-run assertion (no
  `orchestration_runs` row written at dequeue) alongside the pre-Phase-1
  rev-parse test
- `scripts/tests/test_history_reader.py` — confirm
  `aggregate_orchestration_runs` still behaves sanely once `status='running'`
  rows can persist for crashed runs (decision 4's accepted consequence)

_Added 2026-08-01 (review):_
- `scripts/tests/test_history_reader.py` also hosts the **reader helper's own
  tests** (placement corrected — `read_base_sha` lives in `history_reader.py`,
  not `session_store/queries.py`): the 4-gate happy-path / missing-row /
  NULL-column / unreadable-DB shape modeled on
  `test_read_adapter_gen_version_*` (`test_init_core.py:1249-1271`), plus the
  `run_id`-omitted and unstamped-row-does-not-shadow cases
- `scripts/tests/test_session_store_writers.py` — add the `started_at`
  preservation case alongside the `base_sha` COALESCE one: early upsert with
  `started_at`, terminal upsert without it, assert `started_at` is still
  non-NULL. Without this the regression is invisible on the happy path, since
  `ended_at` alone satisfies the `COALESCE(ended_at, started_at)` windows for a
  *completed* run — it only surfaces on the abandoned run

### Documentation

_Wiring pass added by `/ll:wire-issue` (2026-07-30):_
- `docs/ARCHITECTURE.md` — add a `history.db` schema-versions row for the new
  migration
- `docs/reference/API.md` — update `record_orchestration_run`/
  `record_loop_run_summary` signature blocks with the new params

### Consumers
- `ENH-2853` — pre-patch test-failure check (primary consumer; blocked on this)
- `FEAT-2855` / `FEAT-2867` — *optional* window-attribution precision; neither is blocked on this stamp, and FEAT-2867 intentionally sequences first using commit-timestamp windows. Both must work without it.

## Scope Boundaries

**In scope:** capturing the SHA (plus dirty-tree flag) at exactly two points —
`ll-parallel`'s per-issue worktree creation, and inside
`process_issue_inplace()`, which covers both `ll-auto` and `ll-sprint`'s
sequential in-place branch (decision 2 below) and, transitively via
`ll-auto --only`, `autodev.yaml` (decision 3 below); one reader helper that
returns `None` when unstamped; persistence onto the existing per-issue
`orchestration_runs` record, **written at dequeue rather than at end-of-run**
(decision 4 below) so the stamp is readable while the issue is in flight.

**Resolved decisions (2026-07-31, manual). Decision fragments —
`.ll/decisions.d/ab3358ac-830c-4e62-bf28-a112b624b5bd.json` (entry id
`61df2043-…`) and `.ll/decisions.d/244d23c4-4464-4ef7-8f04-fdc85cedcea2.json`
(entry id `4f66ef35-…`). Cite the *filename*: a fragment's filename is a
distinct UUID from its `id` field, and three successive
`/ll:confidence-check` passes wrongly reported "no decision fragment for
ENH-2866 exists" after globbing `.ll/decisions.d/` by entry id.**

1. **`ll-queue run` (FEAT-2906) is exempt — out of scope.** `cli/queue.py`
   never calls `session_store.writers`: no `orchestration_runs`/`loop_runs`
   row exists for a queue entry, so the shared reader helper (which resolves
   only those two tables) could never surface a queue-side stamp — a stamp
   there would violate the single-reader AC by construction. There is also no
   unstamped issue-work path: a `LOOP` entry is driven via a subprocess
   `ll-loop run`, whose own run (e.g. `autodev.yaml`'s `dequeue_next`) is
   stamped at site 1; `SKILL`/`CMD`/`MCP`/`PROMPT` entries are not issue
   orchestration and have no run row to stamp. Rejected alternatives:
   stamping into the `QueueEntry` `result` JSON blob (unreadable by the
   shared reader), or a first-ever direct writers call from `cli/queue.py`
   (new persistence surface with no consumer).
2. **`ll-sprint`'s sequential `process_issue_inplace()` path is IN scope**,
   covered as a variant of the `ll-auto` site rather than a fourth capture:
   the pre-Phase-1 `git rev-parse HEAD` + dirty check is captured *inside*
   `process_issue_inplace()` and exposed as new `base_sha: str | None = None`
   / `base_dirty: bool | None = None` fields on `IssueProcessingResult`
   (`issue_manager.py:563-574`). `ll-auto`'s own loop and
   `cli/sprint/run.py`'s two `record_orchestration_run(driver="ll-sprint")`
   calls (~L694, ~L842 — which today pass no SHA) each forward those fields.
   One capture point, two forwarding sites. Worktree-mode sprint waves remain
   covered transitively by the `ll-parallel` stamp; the prior unqualified
   "no separate `ll-sprint` stamp is needed" claim applied only to that
   worktree-mode delegation and is superseded by this decision for the
   sequential branch.

**Resolved decision (2026-08-01, design review):**

3. **`autodev.yaml`'s `dequeue_next` stamp is REMOVED from scope — autodev is
   covered transitively.** The originally-drafted site 1 was unimplementable
   as specified and redundant once implemented correctly:
   - *No per-issue home.* `dequeue_next` fires once per issue (~20 states
     route back to it), but `loop_runs` is one row per run
     (`run_id TEXT NOT NULL UNIQUE`, `schema.py:554`) with no issue column.
     `${context.run_dir}/autodev-dequeue-sha.txt` is overwritten every
     iteration, so at most the last issue's SHA could persist — and ENH-2853
     needs a per-issue base.
   - *No writer.* No loop *state* calls `record_loop_run_summary`;
     `FSMExecutor._finish()` does (`fsm/executor.py:3111-3126`), generically
     at archival, with no knowledge of loop-specific run-dir filenames.
     Wiring it would mean inventing a loop-agnostic run-dir filename
     convention in the executor — new mechanism, for one loop.
   - *Already covered, and better.* `implement_current` runs
     `ll-auto --only "$CURRENT"` (`autodev.yaml:833`), reaching
     `process_issue_inplace()` and writing a per-issue `orchestration_runs`
     row. That stamp is taken *after* refine/wire/size-review commit their
     issue-file churn and immediately before the implementation patch — the
     base a pre-patch test check actually wants, not a several-commits-stale
     dequeue-time tree.

   Consequences: `loop_runs` gains no columns, `record_loop_run_summary` is
   unchanged, and the reader collapses to a single `orchestration_runs`
   lookup keyed by `(run_id, issue_id)` — which is what makes the
   "same reader for every orchestrator" AC true by construction instead of by
   run_id-shape probing. Rejected alternative: a generic
   `${context.run_dir}/base-sha.txt` convention read by `_finish()` — still
   one-row-per-run, so it does not solve (a), and adds executor surface for a
   value no consumer can key by issue.

**Resolved decision (2026-08-01, second design review):**

4. **The stamp is written at dequeue, and the reader's `run_id` is optional.**
   Two defects that would each have made the delivered feature unusable by its
   only consumer:

   - *Write timing.* All three `record_orchestration_run(...)` call sites are
     post-completion — `issue_manager.py:1691`, `orchestrator.py:1044` (via
     `_on_worker_complete`, `L1072`/`L1245`), `cli/sprint/run.py:713`/`879`.
     ENH-2853's pre-patch check runs mid-issue, during the verification step of
     the very issue being stamped, so no row exists at read time and every run
     silently takes the merge-base fallback. Resolving the SHA early is not
     enough; it must be *persisted* early. Each site now issues a dequeue-time
     `status="running"` upsert, with the existing terminal call
     COALESCE-upserting the outcome onto the same `(run_id, issue_id)` row.
   - *Reader key.* `run_id` is a process-local `uuid4().hex`
     (`issue_manager.py:1282`, `orchestrator.py:123`) never exported anywhere.
     ENH-2853 runs in a separate FSM-oracle process and cannot supply one; and
     the decision-3 transitive path makes it moot anyway, since
     `ll-auto --only` mints its own `run_id`. `run_id` becomes optional, with
     an `issue_id`-only most-recent-stamped-row lookup.

   Two behavioral consequences, accepted:
   - `record_orchestration_run`'s `effective_ended_at = ended_at or _now()`
     (`writers.py:1213`) must not fire for an in-flight row, or an abandoned
     run reads as `ended_at == started_at`.
   - A crashed or interrupted run now leaves a permanent `status='running'`
     row where today no row exists at all. `history_reader.aggregate_orchestration_runs`
     computes `completed / COUNT(*)` (`history_reader.py:1783`/`1807`), so
     reported success rates will drop slightly. This is judged an accuracy
     improvement — a crashed run *is* a non-completion — but it is a visible
     change to existing analytics, not a silent one, and should be called out
     in the changelog entry.
   - An in-flight or abandoned row is invisible to a windowed
     `ll-session export --since`: `_EXPORT_TABLE_MAP` keys `orchestration_run`
     on `ended_at` (`session_store/queries.py:101`) with no `started_at`
     fallback, unlike `history_reader`'s `COALESCE(ended_at, started_at)`.
     Accepted as-is — widening the export key is a separate change with its own
     compatibility surface — but recorded here so it is a known property rather
     than a later discovery. This is also *why* the `started_at` COALESCE in
     Design Notes matters: `history_reader`'s windowed queries do fall back to
     `started_at`, and that fallback only works if the terminal upsert has not
     nulled it.

   Both 2026-08-01 decisions are now recorded as fragments:
   `.ll/decisions.d/20d75e61-7e0f-48c5-8db8-2fba7752ad82.json` (decision 3,
   entry id `8bb5147f-…`) and
   `.ll/decisions.d/9de33ea4-ebb4-409e-ac31-19c910236b2d.json` (decision 4,
   entry id `59a24610-…`).

   Rejected alternative: exporting `run_id` into subprocess env
   (`LL_RUN_ID`) so the reader could keep a required key. It does not solve the
   autodev case (the `ll-auto --only` child mints its own), and it adds a new
   cross-process contract for a lookup that `issue_id` alone answers
   adequately given the stamp is advisory.

**Out of scope:** the merge-base fallback logic itself and any use of the base
state (ENH-2853 owns both); stamping `ll-loop run --worktree` or the epic-branch
verify path — neither dequeues work items; `ll-queue run` (decision 1 above);
a separate stamp for worktree-mode `ll-sprint` waves — those delegate to the
same `ParallelOrchestrator` as `ll-parallel` (`cli/sprint/run.py:23`), so the
`ll-parallel` stamp covers them (the sequential in-place branch is in scope
per decision 2 above); any `autodev.yaml` change and any `loop_runs` /
`record_loop_run_summary` change (decision 3 above);
changing `setup_worktree()` /
`cleanup_worktree()` semantics for their four existing callers.

## Impact

Turns ENH-2853's base-state resolution from a fallback-only path into its
intended one, and offers FEAT-2855 / FEAT-2867 an *optional* precise window
boundary instead of one inferred from commit timestamps — an additive refinement
those two do not depend on. Small and self-contained: a
`git rev-parse`, a run-dir file write in the same idiom `dequeue_next` already
uses for its readiness snapshot, and one reader.

## Confidence Check Notes

_Added by `/ll:confidence-check` (2026-07-30):_

**Gaps to Address:**
- Program Design section is missing. The Program Design gate is armed
  (`.ll/program-design-cutover.json`, stamped 2026-07-30) and
  `ll-issues format-check ENH-2866 --format json` reports `"missing": ["Program
  Design"]`. This is a hard override regardless of the aggregate readiness
  score: populate `## Program Design` with concrete types/signatures and the
  call path (e.g. the reader helper's signature, the `WorkerResult` field
  additions, the `_MIGRATIONS` entry shape) via `/ll:refine-issue` or
  `/ll:reconcile-issue`, or set `program_design_not_applicable: true` if this
  is judged genuinely trivial (unlikely given the four-site fanout).

**Outcome Risk Factors:**
- **Open decision left unresolved**: the Scope Boundaries section states "`ll-queue
  run` (FEAT-2906) also dequeues work items. Stamp it or move it to *Out of
  scope* with a stated reason before implementation — do not leave it
  unaddressed." This is a genuine open decision point that must be resolved
  before implementation starts, not just documented as a risk.
- **Change-surface ambiguity**: four distinct dequeue sites
  (`autodev.yaml`, `ll-parallel`/`worker_pool.py`/`orchestrator.py`,
  `issue_manager.py`, and the still-undecided `ll-queue`) each need
  differently-shaped capture/persistence wiring — `issue_manager.py` needs a
  brand-new `git rev-parse` call, `worker_pool.py` needs an existing value
  threaded through `WorkerResult`/`_record_orchestration_result()`, and
  `ll-queue` has no existing `session_store.writers` call at all. This is
  Pattern A (each site requires site-specific judgment), not a uniform
  mechanical substitution, which caps the change-surface score even though
  every individual site is well-researched.
- **Complexity breadth**: the wiring pass identified that `WorkerResult.to_dict()`/
  `from_dict()` hand-list fields and `_record_orchestration_result()` currently
  forwards no SHA at all to `record_orchestration_run(...)` — both are easy to
  miss if implementation proceeds site-by-site without checking the full
  round-trip chain end to end.

Test coverage is strong: every site names an existing test file and a close
analog test pattern to model (`TestDequeueNextPreReadinessSnapshot`,
`TestWorkerPoolWorktreeManagement`, `TestSchemaV15SkillCompletionColumns`,
`TestFallbackVerification.test_baseline_sha_passed_to_verify_work_was_done`),
so Criterion B scored high despite the ambiguity/complexity risk factors above.

_Re-run by `/ll:confidence-check` (2026-07-30) — Program Design gap closed;
re-scored 82/56:_

**Concerns:**
- The Program Design gate (2026-07-30) now passes — `## Program Design` was
  added by a subsequent `/ll:refine-issue`/`/ll:wire-issue` pass and
  `ll-issues format-check ENH-2866 --format json` reports no missing/nonspecific
  sections. That hard override no longer applies.
- The "Open decision" on `ll-queue run` scope, flagged in the prior pass, is
  still unresolved in the Scope Boundaries text verbatim ("Stamp it or move it
  to *Out of scope* with a stated reason before implementation — do not leave
  it unaddressed") despite a `/ll:decide-issue` session entry appearing after
  the prior confidence check — no decision fragment for ENH-2866 exists in
  `.ll/decisions.d/`, and `decision_needed: true` is still set. Resolve this
  before implementation starts.
- The wiring pass surfaced a second unresolved contradiction: Scope Boundaries
  claims `ll-sprint run` needs no separate stamp because it delegates to the
  same `ParallelOrchestrator` as `ll-parallel`, but `cli/sprint/run.py`'s
  `_run_issue_with_wall_clock_timeout()` calls `process_issue_inplace()`
  directly and sequentially — a distinct, currently-unstamped code path. This
  compounds the ambiguity score alongside the `ll-queue` open decision.

**Outcome Risk Factors:**
- Both open decisions above (`ll-queue` scope, `ll-sprint`'s sequential path)
  remain unresolved going into implementation, which is why Criterion C
  (Ambiguity) scored 8/25 this pass, slightly lower than the prior 10/25.
- Change surface stays Pattern A (site-specific judgment per dequeue site);
  no change from the prior pass's reasoning.

## Confidence Check Notes

_Re-run by `/ll:confidence-check` (2026-07-31) — post-reconcile pass; scores
unchanged at 82/56:_

**Readiness Score**: 82/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 56/100 → LOW

### Concerns
- The `/ll:reconcile-issue` pass (2026-07-31T03:03:58) rewrote the Proposed
  Change section to add `ll-auto` as a third stamp site but did **not** touch
  the open `ll-queue run` scope decision — Scope Boundaries still reads
  verbatim "Stamp it or move it to *Out of scope* with a stated reason before
  implementation — do not leave it unaddressed." A `/ll:decide-issue` session
  ran after that (2026-07-31T02:57:31, before the reconcile pass) but no
  decision fragment for ENH-2866 exists in `.ll/decisions.d/`, and
  `decision_needed: true` is still set in frontmatter.
- The `ll-sprint`/`cli/sprint/run.py` contradiction flagged by the prior
  `/ll:wire-issue` pass — "Scope Boundaries claims no separate `ll-sprint`
  stamp is needed, but `_run_issue_with_wall_clock_timeout()` calls
  `process_issue_inplace()` directly and sequentially, a distinct unstamped
  path" — is also still unresolved in the current Scope Boundaries text.
- Program Design gate now passes (`ll-issues format-check` reports no
  missing/nonspecific sections), so that prior hard override no longer
  applies.

### Outcome Risk Factors
- Two open decisions (`ll-queue` scope, `ll-sprint`'s sequential
  `process_issue_inplace()` path) remain unresolved going into
  implementation. Resolve both before implementation starts — this is what
  caps Criterion C (Ambiguity) at 8/25.
- Change surface stays Pattern A: four-plus distinct dequeue sites each need
  site-specific wiring judgment (`issue_manager.py` needs a brand-new
  `git rev-parse`, `worker_pool.py` needs an existing value threaded through
  `WorkerResult`/`_record_orchestration_result()`, `ll-queue` has no existing
  `session_store.writers` call at all) rather than one uniform mechanical
  substitution.

## Confidence Check Notes

_Re-run by `/ll:confidence-check` (2026-08-01) — post-decision-4 pass; readiness
unchanged at 98, outcome confidence 61 (down from 67):_

**Readiness Score**: 98/100 → GO
**Outcome Confidence**: 61/100 → below the 65 outcome threshold

### Outcome Risk Factors
- Decision 4 adds a third write per stamped site — a dequeue-time
  `status="running"` early upsert issued directly from `_process_issue`
  (`ll-parallel`) / `process_issue_inplace()` (`ll-auto`/`ll-sprint`),
  separate from the existing terminal upsert those sites already made. This
  is on top of the already-Pattern-A per-site wiring the prior pass scored,
  and pushes Complexity/Change-Surface lower than the 82/56-era estimate.
- The early-upsert/terminal-upsert coordination is subtle:
  `record_orchestration_run`'s `effective_ended_at = ended_at or _now()`
  default (`writers.py:1213`) must be conditioned on a terminal status being
  written, or an in-flight row gets `ended_at` stamped at dequeue time. A
  wrong conditional here reads green on the happy path (the terminal upsert
  overwrites it) and only surfaces on an abandoned/crashed run, exactly the
  case decision 4 exists to make readable.
- Accepted behavioral change: a crashed or interrupted run now leaves a
  permanent `status='running'` row where today no row exists at all,
  measurably lowering `aggregate_orchestration_runs`' reported success rate
  (`history_reader.py:1783`/`1807`). The issue judges this an accuracy
  improvement and flags it for the changelog, but it's a visible analytics
  shift a reviewer should confirm is expected rather than a regression.

## Confidence Check Notes

_Re-run by `/ll:confidence-check` (2026-08-01) — post decision-3/4-fragment
verification pass; readiness unchanged at 98, outcome confidence unchanged at
61:_

**Readiness Score**: 98/100 → GO
**Outcome Confidence**: 61/100 → below the 65 outcome threshold

### Outcome Risk Factors
- Verified all four decision fragments now exist on disk
  (`.ll/decisions.d/20d75e61-…`, `7920ac07-…`, `9de33ea4-…`, `d67300a2-…`) and
  every line reference cited in Program Design / Codebase Research Findings
  (`writers.py:1181-1244`, `worker_pool.py:362`, `issue_manager.py:577/646-648`,
  `types.py:94`, three `record_orchestration_run(...)` call sites) matches the
  current tree exactly. Ambiguity is no longer capped by open decisions — all
  are resolved — but Criterion C stays at 18/25 rather than higher because the
  early-upsert/terminal-upsert coordination (the `ended_at` conditional, the
  `started_at`/`base_sha` COALESCE pair) is subtle enough that a wrong
  conditional reads green on the happy path and only surfaces on an
  abandoned/crashed run — an inherent property of the design, not an
  unresolved question.
- Change surface remains Pattern A: five-plus files each need site-specific
  wiring judgment (schema migration, writer COALESCE logic, `WorkerResult`
  round-trip fields, `IssueProcessingResult` new params, reader placement in
  `history_reader.py`) rather than one uniform mechanical substitution — this
  caps Criterion D at 9/25 independent of how well each site is documented.
- Complexity (12/25) reflects genuine breadth (6+ files) even though every
  site names an existing analog to model from, which is why Test Coverage
  scores much higher (22/25) than the other three outcome criteria.

## Resolution

_Implemented 2026-08-01 via `/ll:manage-issue`._

Landed in the order the pre-implementation review prescribed: writer/schema/reader
first (their COALESCE and `ended_at` conditioning fail green on the happy path and
have no orchestrator dependency), then the two capture sites.

**Schema (v38)** — `session_store/schema.py`: `SCHEMA_VERSION` 37 → 38 plus a
`_MIGRATIONS` entry adding nullable `orchestration_runs.base_sha TEXT` /
`base_dirty INTEGER`. Fix-forward, no backfill, no `loop_runs` change.

**Writer** — `record_orchestration_run(..., base_sha=, base_dirty=)`. Three columns
became write-once via `COALESCE(excluded.X, X)` in the DO UPDATE clause:
`base_sha`, `base_dirty`, and `started_at` (the last because no terminal caller
passes it, and last-write-wins would have nulled the dequeue timestamp and dropped
abandoned rows out of `history_reader`'s `COALESCE(ended_at, started_at)` windows).
An in-flight (`status="running"`) row leaves `ended_at` NULL and defaults its own
`started_at` — that default lives in the writer rather than in each capture site,
so no caller duplicates timestamp formatting. A falsy `base_sha` normalizes to NULL.

**Reader** — `history_reader.read_base_sha(issue_id, *, run_id=None, db=...)`,
never-raising, placed alongside the other `orchestration_runs` reads.
`OrchestrationRun` and `recent_orchestration_runs` also gained the two columns so
the dirty flag is readable.

**`ll-parallel`** — `WorkerResult` gained `base_sha`/`base_dirty` (plus both
hand-listed dict mappings); `WorkerPool.__init__` gained `run_id`/`driver`, which
`ParallelOrchestrator` now passes. `_process_issue` coerces `_get_main_head_sha()`'s
`""` to `None`, adds a `_is_main_repo_dirty()` check, issues the dequeue-time
upsert, and threads both values into all 12 in-method returns via a local
`_stamped_result` closure — the `_handle_completion` fallback at `worker_pool.py:307`
stays unstamped by design. `_record_orchestration_result()` forwards both.

**`ll-auto` / `ll-sprint` sequential** — `IssueProcessingResult` gained the two
fields; `process_issue_inplace()` gained `run_id`/`driver`/`db_path` (early upsert
skipped unless all three are present, and under `dry_run`), captures via a new
module-level `_resolve_base_state()` before Phase 1, and carries the stamp onto all
14 returns. `AutoProcessor._process_issue` and both
`cli/sprint/run.py` terminal calls forward it.

**`autodev.yaml`** — unchanged, per decision 3; a negative-guard test asserts no
`autodev-dequeue-sha` artifact and that `implement_current` still shells out to
`ll-auto --only`, which is what makes the transitive stamp hold.

Verification: `python -m pytest scripts/tests/` → 17783 passed, 42 skipped.
`ruff check scripts/` clean. `python -m mypy scripts/little_loops/` reports only
two pre-existing errors in `cli/issues/normalize.py`, a file this change does not
touch.

**Analytics note for the changelog:** a crashed or interrupted run now leaves a
permanent `status='running'` row where previously no row existed, so
`aggregate_orchestration_runs`' reported success rate drops slightly. This is the
accepted, deliberate consequence of decision 4 — a crashed run *is* a
non-completion — not a regression.

Two implementation notes worth carrying forward:

- The `replace_all` edit used to stamp the 12 `WorkerResult` / 14
  `IssueProcessingResult` return sites also rewrote each stamping closure's own
  body into a self-call. Caught by tests in both files, but the pattern
  (define-closure-then-bulk-rewrite-constructor) needs the closure body excluded.
- `ruff format scripts/` reformats ~30 files unrelated to any given change; run it
  only against the files a change touches, or revert the rest before committing.

## Status

**Done** | Created: 2026-07-27 | Completed: 2026-08-01 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-02T02:15:23 - `747c15d9-755c-4079-bcf7-8e0b958348f7.jsonl`
- `/ll:ready-issue` - 2026-08-02T01:30:05 - `6c4807ec-5dc9-473c-8026-65d5738daba7.jsonl`
- outcome-gate waiver (manual, no skill) - 2026-08-01 - stamped
  `outcome_gate_waived: true` at 98/61. A `/ll:confidence-check` re-run after
  the pre-implementation review below returned *identical* subscores
  (12/22/18/9), including no movement on ambiguity despite decisions 3 and 4
  gaining real fragments — so the 61 is pinned by `score_complexity` and
  `score_change_surface`, the two size dimensions, and no further specification
  will move it. Splitting is the only thing that would, and it was rejected on
  substance: the natural boundary (schema+writer+reader / capture sites) would
  unblock ENH-2853 against a reader that always returns `None` — the exact
  dead-primary-path failure this issue was carved out of ENH-2853 to prevent —
  and it puts the SCHEMA_VERSION churn and the subtle early/terminal upsert
  coordination in the same half, buying no risk isolation. Wide is not the same
  as uncertain; the only genuinely open item is decision 4's deliberate,
  documented, reversible analytics shift. **Implementation order:** land
  `writers.py` and its tests first (the `started_at`/`base_sha` COALESCE and
  `ended_at` conditioning fail green on the happy path, and have no
  orchestrator dependency) before touching any capture site. Not an autodev
  candidate even with the gate waived — 12 `WorkerResult` construction sites
  and Pattern-A per-site judgment; drive it manually or via `/ll:manage-issue`
- flag correction (manual, no skill) - 2026-08-01 - cleared `decision_needed`
  again (set by this same `/ll:confidence-check` pass): recurrence of the
  already-diagnosed `set-flags` false positive below — it matched "open
  decision"/"decision point" from stale, already-resolved historical
  `## Confidence Check Notes` blocks earlier in the file rather than the
  current one. Verified all four decision fragments
  (`20d75e61`/`7920ac07`/`9de33ea4`/`d67300a2`) exist and every cited
  line/signature in Program Design still matches the tree exactly.
- `/ll:confidence-check` - 2026-08-02T01:22:51 - `b10f0b3a-574a-4cd1-aefd-c6a613922849.jsonl`
- pre-implementation review (manual, no skill) - 2026-08-01 - three code-level
  corrections: (a) `started_at` is clobbered by the terminal upsert
  (`writers.py:1227` last-write-wins + no terminal caller passes it), which
  under decision 4 nulls the dequeue timestamp and drops abandoned rows out of
  `history_reader`'s `COALESCE(ended_at, started_at)` windows — needs the same
  COALESCE as `base_sha`; (b) `process_issue_inplace()` needs a `db_path` param
  too, not just `run_id`/`driver` (verified signature `L577-590` has none of
  the three); (c) `read_base_sha` moved from `session_store/queries.py` to
  `history_reader.py`, where the other `orchestration_runs` reads and the
  `_connect_readonly`/never-raise contract already live. Also recorded
  decisions 3 and 4 as decision fragments, fixed the fragment citations to use
  filenames rather than entry ids, corrected the stale `_get_main_head_sha`
  line ref, and documented the `search_index` and `export --since` consequences
  of the early upsert
- flag correction (manual, no skill) - 2026-08-01 - cleared `decision_needed`
  (set by this same `/ll:confidence-check` pass): `ll-issues set-flags` matched
  "open decision"/"decision point" from a stale, already-resolved 2026-07-30
  `## Confidence Check Notes` block still present earlier in the file, not a
  live open decision — decision 4 and the `ll-queue`/`ll-sprint` scope
  questions are all resolved with recorded rationale. Root cause looks like
  `set-flags` scanning from the *first* `## Confidence Check Notes` header
  through `## Status` on an issue with multiple stacked historical notes
  sections, rather than just the most recent one; worth a bug report.
- `/ll:confidence-check` - 2026-08-02T01:05:29 - `8b2aecad-5678-4f40-8b5b-a1be3ec862a6.jsonl`
- design review (manual, no skill) - 2026-08-01 - decision 4: stamp is written
  at dequeue (`status="running"` early upsert) rather than end-of-run, since all
  three existing `record_orchestration_run` sites fire after the issue completes
  and ENH-2853 reads mid-issue; `read_base_sha`'s `run_id` made optional
  (process-local `uuid4().hex`, unreachable from ENH-2853's oracle-loop process);
  corrected `worker_pool.py:297` as a non-stampable site, expanded the
  `SCHEMA_VERSION` test-bump scope from 2 sites to ~10 plus 7 modules, narrowed
  the autodev negative-guard AC, and refreshed drifted line refs
- `/ll:confidence-check` - 2026-08-02T00:46:46 - `b0869093-304a-4a68-b09f-0b4e513fe075.jsonl`
- design review (manual, no skill) - 2026-08-01 - decision 3: removed the
  `autodev.yaml` `dequeue_next` stamp (no per-issue home on `loop_runs`, no
  state-level writer, redundant with the `ll-auto --only` shell-out); collapsed
  the reader to a single `orchestration_runs` lookup; added COALESCE-on-retry,
  empty-SHA→NULL normalization, and `--untracked-files=no` dirty semantics to
  Program Design + ACs
- scope-decision resolution (manual, no skill) - 2026-07-31 - resolved both open decisions: `ll-queue run` exempted, `ll-sprint` sequential path in scope via `IssueProcessingResult.base_sha`/`.base_dirty`; cleared `decision_needed`; fragments `61df2043` / `4f66ef35` in `.ll/decisions.d/`
- `/ll:confidence-check` - 2026-07-31T00:00:00 - `f11a8fcc-5588-45b0-a78b-50012a4879e9.jsonl`
- `/ll:reconcile-issue` - 2026-07-31T03:03:58 - `2e6be344-18cc-4ac2-a67d-7bcec83bcb6a.jsonl`
- `/ll:confidence-check` - 2026-07-30T00:00:00 - `6aef3121-54b6-416e-8fef-c0e5ebfab7b4.jsonl`
- `/ll:decide-issue` - 2026-07-31T02:57:31 - `ffa285f4-3818-4fef-a251-cc2e4a030e29.jsonl`
- `/ll:refine-issue` - 2026-07-31T02:53:31 - `5686b38e-c45d-4f6b-a63d-631c66bc6ea9.jsonl`
- `/ll:confidence-check` - 2026-07-30T00:00:00 - `54a79976-1e3b-404f-8cc3-9d58d0fb1a04.jsonl`
- `/ll:wire-issue` - 2026-07-31T02:47:37 - `9cc9e23c-e1c8-45ff-b1c6-0837a2da5075.jsonl`
- `/ll:refine-issue` - 2026-07-31T02:39:25 - `e804a137-5adf-4d3f-be2b-f3df4029965c.jsonl`
- gate-placement review (manual, no skill) - 2026-07-30 - added `issue_manager.py` (`ll-auto`) as a third stamp site and `ll-queue run` as an open decision; Design Notes, Files to Modify, 3 ACs, Scope Boundaries
- `/ll:audit-issue-conflicts` - 2026-07-27T19:42:08 - `e2303183-4e52-4649-af90-4b53254bbda4.jsonl`
