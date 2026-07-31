---
id: ENH-2866
title: Record dequeue-time commit SHA at orchestrator dequeue and worktree creation
type: ENH
priority: P2
status: deferred
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
decision_needed: true
confidence_score: 82
outcome_confidence: 56
reconcile_attempted: true
score_complexity: 14
score_test_coverage: 20
score_ambiguity: 8
score_change_surface: 14
size: Very Large
deferred_by: automation
deferred_date: '2026-07-31T03:07:04Z'
deferred_reason: readiness_stagnated
---

# ENH-2866: Record dequeue-time commit SHA at orchestrator dequeue and worktree creation

## Summary

Nothing in little-loops records the commit SHA a work item started from. Every
orchestrator — `autodev.yaml`'s `dequeue_next`, `ll-parallel`'s per-issue
worktree creation, `ll-sprint`'s waves — begins work against some tree state and
then discards the fact. (`ll-sprint run` delegates execution to the same
`ParallelOrchestrator` as `ll-parallel` — `cli/sprint/run.py:23` — so stamping
`ll-parallel`'s worker creation covers sprint waves transitively; no separate
`ll-sprint` stamp is needed.)

Stamp that SHA at the point work is dequeued, in a location downstream checks
can read. Carved out of ENH-2853, where it was one of eight workstreams and the
only one that is independently landable and independently useful.

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
`autodev.yaml`'s `dequeue_next` (~L80-141) snapshots pre-refine readiness to
`${context.run_dir}/autodev-pre-readiness.txt` but calls `git rev-parse`
nowhere. `ll-parallel` delegates worktree lifecycle to
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

1. **`autodev.yaml` `dequeue_next`** — write `git rev-parse HEAD` to
   `${context.run_dir}/autodev-dequeue-sha.txt`, alongside the existing
   pre-refine readiness snapshot written by the same state (FEAT-2751). Same
   run-dir handshake-file idiom, no new mechanism.
2. **`ll-parallel`** — capture the SHA at per-issue worktree creation.
   `worker_pool.py` already computes `baseline_head_sha =
   self._get_main_head_sha()` immediately before `_setup_worktree(...)`
   (`~L358-367`); carry that value (plus a new inline dirty-check) through a
   new `base_sha`/`base_dirty` pair on `WorkerResult`
   (`parallel/types.py:52-94`), threaded into every `WorkerResult(...)`
   construction in the worker-start method (success and failure paths alike).
   `orchestrator.py`'s `_record_orchestration_result()` (`~L1016-1036`)
   currently forwards only `branch=result.branch_name` to
   `record_orchestration_run(...)` — it must also forward
   `result.base_sha`/`result.base_dirty`, since that call is the actual
   missing link to persistence, not just the capture site.
3. **`ll-auto`** — `issue_manager.py`'s own sequential dequeue loop, which
   routes through neither `autodev.yaml` nor `ll-parallel`. Its existing
   `_baseline_sha` local (`~L921-926`) is captured *after* Phase 1
   (ready/verify) already ran and is not reusable; add a fresh
   `git rev-parse HEAD` (plus dirty-check) before Phase 1 starts
   (`~L633-635`) and thread it into whatever call records the `ll-auto`
   outcome via `record_orchestration_run(...)`.
4. **Reader helper** — one function that resolves a run's base SHA, returning the
   stamp when present and `None` when not, so consumers implement the
   merge-base fallback once and identically rather than each rolling their own
   lookup.
5. **Persist to `.ll/history.db`** where a run is already recorded, so the stamp
   outlives the run directory. Concretely: additive nullable columns
   (`base_sha TEXT`, `base_dirty INTEGER`) on the existing run rows —
   `loop_runs` (`session_store/schema.py:553`) for the autodev/FSM path and
   `orchestration_runs` (`session_store/schema.py:523`) for both
   `ll-parallel` and `ll-auto` — via a new `_MIGRATIONS` entry in
   `session_store/schema.py` (NULL = "unstamped", matching
   the reader's `None` contract). No new table.

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
- **Resolve the SHA before any mutation.** In `dequeue_next` this means before
  refinement writes to the issue file — a stamp taken after the first commit of
  the run describes the wrong tree.
- **Detached/dirty trees.** Record the SHA plus whether the tree was dirty at
  stamp time; a dirty base means a pre-patch reconstruction is approximate and
  the consumer should be able to say so rather than assert a clean comparison.
- No LLM involvement — this is a `git rev-parse` and a file write.
- **`ll-auto` is a third dequeue site and was missing from the stamp set** (placement review, 2026-07-30). This issue's Motivation names `ll-auto` as a case where a verification step spans multiple commits and merge-base is wrong — but the Proposed Change stamps only `autodev.yaml`'s `dequeue_next` and `ll-parallel`'s worker creation. `ll-auto` routes through neither: `cli/auto.py` → `issue_manager.py`'s `AutoProcessor` is its own sequential dequeue loop, not a wrapper over `autodev.yaml` (a grep of `issue_manager.py` for `autodev` returns only a comment at L905). As written, the one orchestrator the Motivation calls out would always take ENH-2853's merge-base fallback. Stamp `issue_manager.py`'s per-issue dequeue as a third site. Check first whether the `_baseline_sha` it already computes for `verify_work_was_done()` (~L1072, ~L1109) is the same value — if so this is a persistence change, not a new capture.
- **`ll-queue run` is a fourth dequeue site — stamp it or exempt it explicitly** (placement review, 2026-07-30). FEAT-2906's `ll-queue run` serially dequeues `pending` entries and drives each to completion, which makes it an orchestrator by this issue's own definition ("the point work is dequeued"). Decide during implementation: stamp it alongside the other three, or record in § Scope Boundaries why it is exempt. Leaving it unaddressed reproduces exactly the `ll-auto` gap this note corrects.

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

- `worker_pool.py`'s worker-start block (`~L358-361`) already computes
  `baseline_head_sha = self._get_main_head_sha()` before
  `self._setup_worktree(...)` (`~L367`). Add a sibling dirty-check inline
  (no shared helper exists — see Design Notes), following the
  `git status --porcelain` shape at `merge_coordinator.py:151-173`, producing
  a local `baseline_dirty: bool`. Thread both values into every
  `WorkerResult(...)` construction in this method (10+ return sites at
  `~L296, 408, 423, 440, 456, 484, 505, 549, 602, 617` and others) — the
  success path and every early-return failure path alike, since a failed
  worker's base state is equally worth stamping.

- `_record_orchestration_result(result: WorkerResult, status: str, failure_reason: str | None) -> None`
  (`scripts/little_loops/parallel/orchestrator.py:1016-1036`) — extend its
  inner `record_orchestration_run(...)` call (currently forwards only
  `branch=result.branch_name`, no SHA at all) to also pass
  `result.base_sha` and `result.base_dirty`.

- `record_orchestration_run(base_sha: str | None, base_dirty: bool | None) -> bool`
  and `record_loop_run_summary(base_sha: str | None, base_dirty: bool | None) -> bool`
  (`scripts/little_loops/session_store/writers.py:1181-1196`, `1262-1276`) —
  add these two keyword-only params to both existing signatures; thread
  through to the `INSERT ... ON CONFLICT DO UPDATE` (`record_orchestration_run`)
  and `INSERT OR IGNORE` (`record_loop_run_summary`) column lists and
  bound-parameter tuples, following the existing `head_sha`/`branch` pair
  already in both.

- Schema migration — new `_MIGRATIONS` entry appended after the
  `failure_terminal` entry (`schema.py:906-917`, current
  `SCHEMA_VERSION = 37`, `schema.py:21`; the new entry becomes v38), adding:

  - `orchestration_runs.base_sha: str`
  - `orchestration_runs.base_dirty: int`
  - `loop_runs.base_sha: str`
  - `loop_runs.base_dirty: int`

  via `ALTER TABLE ... ADD COLUMN` statements, each nullable (NULL =
  unstamped — orchestrator predates this stamp or opted out; readers fall
  back to merge-base). Fix-forward only, matching the `failure_terminal`
  precedent: existing rows are not backfilled.

- `read_base_sha(db_path: Path | str, run_id: str, issue_id: str | None) -> str | None`
  (new — exact module TBD by implementer; candidate: `session_store/readers.py`
  alongside other typed lookups) — modeled on the None-when-absent contract
  of `read_adapter_gen_version()` (`init/writers.py:786-805`): never raises,
  returns `None` on missing row, NULL column, or any query error.

  Looks up `orchestration_runs.base_sha` (keyed by `run_id`+`issue_id`) or
  `loop_runs.base_sha` (keyed by `run_id`) depending on which table the
  caller's `run_id` belongs to; returns `None` on missing row, NULL column,
  or any query error — never raises, matching every existing reader in this
  module family.

- `issue_manager.py` — new `git rev-parse HEAD` (and a dirty-check) call
  inserted before `Phase 1: Verifying issue` starts (`~L633-635`), separate
  from the existing `_baseline_sha` local (`~L921-926`, computed *after*
  Phase 1 and used only for `verify_work_was_done()` — not reusable for
  this stamp per the Codebase Research Findings above).

### Call Path

- **`ll-parallel`**: `worker_pool.py` worker-start block →
  `_get_main_head_sha()` + new dirty check → `WorkerResult(base_sha=,
  base_dirty=)` at every return site → `orchestrator.py`'s
  `_on_worker_complete()` → `_record_orchestration_result()` →
  `record_orchestration_run(base_sha=, base_dirty=)` → `orchestration_runs`
  columns.
- **`autodev.yaml`**: `dequeue_next`'s shell `action:` → `git rev-parse
  HEAD` → `${context.run_dir}/autodev-dequeue-sha.txt` (run-dir handshake
  file, same idiom as `autodev-pre-readiness.txt`) → read back by whichever
  later state calls `record_loop_run_summary(base_sha=, base_dirty=)` at
  run archival.
- **`ll-auto`**: `issue_manager.py`, before `~L633` → `git rev-parse HEAD`
  → new local (not `_baseline_sha`) → threaded into
  `record_orchestration_run(base_sha=, base_dirty=)` at whatever call
  records the `ll-auto` outcome.
- **Reader**: any consumer (ENH-2853) → `read_base_sha(db_path, run_id=,
  issue_id=)` → `None` (fall back to merge-base, say so) or a SHA string.

## Acceptance Criteria

- [ ] `autodev.yaml`'s `dequeue_next` writes the dequeue-time SHA to the run
      directory, resolved before any state mutates the tree or issue file.
- [ ] `ll-parallel` records the same stamp at per-issue worktree creation, in the
      worker's state rather than inside the shared `setup_worktree()` primitive.
- [ ] `setup_worktree()` / `cleanup_worktree()` signatures remain backward
      compatible; the four existing direct call sites are unchanged or updated
      additively.
- [ ] A single reader helper resolves a run's base SHA and returns `None` when
      unstamped, so the merge-base fallback is implemented once.
- [ ] Whether the tree was dirty at stamp time is recorded alongside the SHA.
- [ ] The stamp is persisted to `.ll/history.db` as additive nullable columns on
      the existing run rows (`loop_runs` / `orchestration_runs`), not a new
      table; NULL means unstamped.
- [ ] An orchestrator or hand-run loop with no stamp continues to work
      unchanged.
- [ ] Tests cover: the stamp written by `dequeue_next`, the stamp written at
      `ll-parallel` worker creation, the reader returning `None` when unstamped,
      and the dirty-tree flag.

_Added 2026-07-30 (placement review) — see Design Notes:_

- [ ] `ll-auto` records the stamp at its own per-issue dequeue in
      `issue_manager.py`, resolved before Phase 1 mutates the issue file. A test
      covers it, and asserts an `ll-auto` run is not left taking the merge-base
      fallback.
- [ ] All three orchestrators write the stamp in a form the *same* reader helper
      resolves — no per-orchestrator lookup logic.
- [ ] `ll-queue run` is either stamped or explicitly exempted in
      § Scope Boundaries with a stated reason.

## Integration Map

### Files to Modify

_`issue_manager.py` added 2026-07-30 (placement review) — see Design Notes,
"`ll-auto` is a third dequeue site."_

- `scripts/little_loops/loops/autodev.yaml` — `dequeue_next` (~L80-141); the
  pre-readiness snapshot at ~L104-117 is the idiom to follow
- `scripts/little_loops/parallel/worker_pool.py` /
  `scripts/little_loops/parallel/orchestrator.py` — per-issue worktree creation
  call sites
- `scripts/little_loops/issue_manager.py` — `ll-auto`'s own sequential dequeue,
  which routes through neither of the two sites above. Stamp at the point the
  issue is taken, before Phase 1 mutates the issue file; check whether the
  existing `_baseline_sha` (~L1072, ~L1109) already holds the right value
- `scripts/little_loops/worktree_utils.py` — only if an additive parameter is
  the cleanest carrier; prefer stamping at the caller
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
  unqualified
- `docs/ARCHITECTURE.md` — the `history.db` schema-versions table (§ "history.db
  schema versions", ~L663-699) is a hand-maintained one-row-per-migration
  changelog; needs a new row for the `base_sha`/`base_dirty` migration,
  following the `v22`/`v23` prose pattern
- `docs/reference/API.md` — `record_orchestration_run` (~L8493) and
  `record_loop_run_summary` (~L8517) are hand-maintained signature blocks
  listing every keyword argument; need `base_sha`/`base_dirty` params inserted

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`issue_manager.py`'s `_baseline_sha` is NOT the value ENH-2866 needs — this
  is a new capture point, not a persistence change.** `_baseline_sha` is
  computed at `issue_manager.py:921-926`, inside the Phase 2 block, via
  `git rev-parse HEAD`. `process_issue_inplace()`'s Phase 1 (ready/verify,
  which can mutate the issue file) starts at `issue_manager.py:633-635` — i.e.
  `_baseline_sha` is captured *after* Phase 1 already ran, not before it as
  this issue's Design Notes hoped. It is also purely a transient local,
  passed only into `verify_work_was_done(baseline_sha=_baseline_sha)`
  (`issue_manager.py:1072`, `1109`) — never persisted. A true dequeue-time
  stamp for `ll-auto` needs a fresh `git rev-parse HEAD` call placed before
  `issue_manager.py:633`, separately persisted.
- **`worker_pool.py` already captures the right value at the right point —
  it just isn't exposed or persisted yet.** `baseline_head_sha =
  self._get_main_head_sha()` runs at `worker_pool.py:359-361`, immediately
  before `self._setup_worktree(...)` at `worker_pool.py:367`.
  `_get_main_head_sha()` (`worker_pool.py:1477-1490`) is a `git rev-parse
  HEAD`. Today this value is only used for leak detection
  (`_detect_committed_leaks()`, `worker_pool.py:1492+`) and logged into the
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
  `scripts/little_loops/init/writers.py:786-805`
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
- `scripts/little_loops/session_store/writers.py:_backfill_commit_events()` (~L781) —
  established `git log` subprocess-invocation shape (timeout, `cwd=repo_root`,
  `capture_output=True, text=True`)
- `scripts/tests/test_worker_pool.py:TestSetupWorktreeAndCleanup` (~L634, e.g.
  `test_setup_worktree_passes_base_branch_in_feature_mode` ~L963) — closest
  analog for a worker-creation-point test; currently asserts only on
  `git worktree add` argv shape

### Tests
- `scripts/tests/test_autodev_loop.py` — follow
  `TestDequeueNextPreReadinessSnapshot` (~L172-186), which does string-containment
  assertions against the raw YAML `action:` block rather than live execution;
  no existing test executes `dequeue_next` live
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
- `scripts/tests/test_session_store_schema.py` — `test_v13_to_v14_migration`
  (~L1130) and `test_v34_db_upgrade_gains_review_events` (~L1880) hardcode
  `SCHEMA_VERSION == 37` / `version == 37` and **will break** once the new
  migration entry is appended — bump alongside it
- `scripts/tests/test_issue_manager.py` — model the new pre-Phase-1 rev-parse
  stamp test on `TestFallbackVerification.test_baseline_sha_passed_to_verify_work_was_done`
  (~L2797-2850)'s `subprocess.run` mock-dispatch pattern (patches
  `little_loops.issue_manager.subprocess.run`, matches
  `cmd == ["git", "rev-parse", "HEAD"]`)
- `scripts/tests/test_worker_pool.py` —
  `TestSetupWorktreeAndCleanup.test_get_main_head_sha_returns_sha` /
  `_returns_empty_on_failure` (~L1638-1671) is the existing mock pattern
  (`patch.object(worker_pool._git_lock, "run", ...)`) to extend for asserting
  the stamp reaches `WorkerResult`
- `scripts/tests/test_init_core.py` — `test_read_adapter_gen_version_*`
  (~L1249-1271, a 4-gate happy-path/missing/malformed/absent-field template) is
  the closest existing test shape for the new reader helper's tests

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

**In scope:** capturing the SHA (plus dirty-tree flag) at `autodev.yaml`'s
`dequeue_next`, `ll-parallel`'s per-issue worktree creation, and (added
2026-07-30, placement review) `issue_manager.py`'s `ll-auto` dequeue; one reader
helper that returns `None` when unstamped; persistence onto the existing run
record.

**Open decision (2026-07-30):** `ll-queue run` (FEAT-2906) also dequeues work
items. Stamp it or move it to *Out of scope* with a stated reason before
implementation — do not leave it unaddressed.

**Out of scope:** the merge-base fallback logic itself and any use of the base
state (ENH-2853 owns both); stamping `ll-loop run --worktree` or the epic-branch
verify path — neither dequeues work items; a separate `ll-sprint` stamp —
`ll-sprint run` delegates to the same `ParallelOrchestrator` as `ll-parallel`
(`cli/sprint/run.py:23`), so the `ll-parallel` stamp covers sprint waves;
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
`TestSetupWorktreeAndCleanup`, `TestSchemaV15SkillCompletionColumns`,
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

## Status

**Open** | Created: 2026-07-27 | Priority: P2


## Session Log
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
