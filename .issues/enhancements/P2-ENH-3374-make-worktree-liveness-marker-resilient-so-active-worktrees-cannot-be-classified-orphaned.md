---
id: ENH-3374
type: ENH
title: make worktree liveness marker resilient so active worktrees cannot be classified
  orphaned
priority: P2
status: done
discovered_by: claude-code-review
discovered_date: '2026-09-01'
relates_to:
- BUG-3373
- BUG-3375
unproven_mechanism: true
learning_tests_required:
- psutil
verify_verdict: NON_VALID
size: Very Large
---

# ENH-3374: make worktree liveness marker resilient so active worktrees cannot be classified orphaned

## Summary

Orphan-worktree detection (`ll-parallel --cleanup-orphans`, delegated to by
`/ll:cleanup-worktrees`) decides liveness solely from a `.ll-session-<pid>`
marker file written once at `setup_worktree`
(`scripts/little_loops/worktree_utils.py:278-281`) and read in
`parallel/orchestrator.py:334-345`. The marker is a single untracked file
inside the worktree: anything that deletes it — a `git clean -fdx` run by a
dispatched Claude session working in that worktree, a stray cleanup script,
or manual tidying — makes a fully live worktree indistinguishable from an
orphan, and the next cleanup pass deletes it out from under its owning
process. This is the leading suspect for the BUG-3373 incident.

## Current Behavior

- `setup_worktree` writes `worktree_path/.ll-session-<pid>` once at creation
  (BUG-579).
- Orphan detection globs `.ll-session-*` in each `.worktrees/*` dir; if a
  marker's pid is alive, the worktree is skipped. **If no marker file is
  found, the worktree is treated as orphaned** and deleted (worktree dir and
  branch).
- Nothing protects the marker from deletion during the worktree's lifetime,
  and nothing re-verifies liveness by an independent signal before removal.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- `preserve_before_teardown()` (`scripts/little_loops/git_operations.py:851-896`), called from `cleanup_worktree()` (`worktree_utils.py:315`), `_cleanup_orphaned_worktrees()` (`orchestrator.py:373`), and `MergeCoordinator._cleanup_worktree()` (`merge_coordinator.py:1160`), runs immediately before every `git worktree remove --force` in the Python paths. It is not a liveness signal or safety net for this issue's failure mode: it takes no PID/marker/registry argument, performs no liveness check, and only snapshots uncommitted dirty changes to a durable git ref (via `preserve_dirty_tree`) when `has_non_noise_dirty_paths()` finds any — a live process's worktree is still deleted regardless, and any work not yet flushed to disk at snapshot time is not captured. `hooks/scripts/session-cleanup.sh::cleanup()` calls no equivalent — its `git worktree remove --force` (line 52) has no preservation step at all.

## Expected Behavior

Absence of a marker is not treated as proof of orphanhood. Cleanup only
removes a worktree when liveness is positively excluded, e.g.:

- keep an authoritative registry *outside* the worktree (e.g.
  `.worktrees/.registry/<worktree-name>.json` in the repo, or under the
  run's `run_dir`) mapping worktree → owning pid + run id, written at
  `setup_worktree` and removed at `cleanup_worktree`, so a `git clean`
  inside the worktree cannot erase the liveness record; and/or
- have cleanup cross-check independent signals before deleting a
  marker-less worktree: a live process whose cwd is inside the worktree
  (`lsof +D` / `psutil`), or a `.loops/runs/*` run dir referencing the
  worktree path with a live pid.

A worktree whose liveness cannot be positively excluded is skipped with a
warning, never deleted.

## Motivation

Deleting an active worktree is silent data loss waiting to happen: it kills
dispatched sessions mid-flight and (per BUG-3373) truncates batch runs with
no error pointing at the cause. The current design makes the safety of every
long-running epic/sprint run depend on no process ever removing one
untracked dotfile — a guarantee nothing enforces, least of all dispatched
LLM sessions that legitimately run `git clean` while implementing issues.

## Proposed Solution

1. Move the authoritative liveness record outside the worktree: at
   `setup_worktree`, write `<worktree_base>/.registry/<worktree-name>` (pid
   + run id); at `cleanup_worktree`, remove it. Keep writing the in-tree
   `.ll-session-<pid>` marker for backward compatibility.
2. In `_cleanup_orphaned_worktrees` (`parallel/orchestrator.py`), consult
   the registry first, then the in-tree marker; treat "registry entry with
   live pid" as live regardless of in-tree state.
3. For worktrees with neither record, add a conservative fallback check
   (any live process cwd inside the path) before deletion; skip + warn when
   the check is unavailable rather than deleting.
4. Tests: registry written/removed by setup/cleanup; cleanup skips a
   registry-live worktree whose in-tree marker was deleted; marker-less +
   registry-less worktree still cleaned (regression for the original
   BUG-579 behavior).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- A third, independent implementation of the same liveness check exists and is not named anywhere in this issue: `hooks/scripts/session-cleanup.sh` (`cleanup()`, wired as a Claude Code Stop hook) re-implements the `.ll-session-*` marker check in bash. Its zero-marker path is *stricter* than the Python orchestrator's — it has no `_is_ll_worktree()`-equivalent name filter, and when `ls "${w}/.ll-session-"*` finds nothing it falls straight through to `git worktree remove --force "$w"` unconditionally, with no dry-run and no orphan-list/logging gate. A fix scoped only to `_cleanup_orphaned_worktrees` in `orchestrator.py` leaves this second, independently-triggered deletion path exposed to the same failure mode.
- `commands/cleanup-worktrees.md` needs no separate fix: per BUG-2324 it is already a thin delegator to `ll-parallel --cleanup-orphans` and inherits `_cleanup_orphaned_worktrees()` behavior verbatim.
- The proposed `.worktrees/.registry/<worktree-name>.json` location is structurally sound against the exact failure mode in Current Behavior: it sits as a sibling of the per-worktree checkout directories under `.worktrees/`, not inside any one of them, so a `git clean -fdx` run from inside e.g. `.worktrees/worker-3` cannot reach `.worktrees/.registry/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add a registry-removal call to `MergeCoordinator._cleanup_worktree()` (`scripts/little_loops/parallel/merge_coordinator.py`), or redirect it to call `worktree_utils.cleanup_worktree()` — it currently bypasses that function entirely.
- Harden `hooks/scripts/session-cleanup.sh`'s `cleanup()` to consult the registry before its unconditional zero-marker deletion, using its existing `jq`-optional fallback pattern.
- Add test coverage for the `ParallelOrchestrator.run()` → `_cleanup_orphaned_worktrees()` auto-invocation path (`orchestrator.py:245`) — no existing test in `TestRunMethod` asserts this call happens.
- Rewrite `test_session_cleanup_removes_worktree_with_no_marker` (`test_hooks_integration.py:3261`) to assert the new safe (skip+warn) behavior instead of unconditional deletion.
- Update `docs/guides/BUILTIN_HOOKS_GUIDE.md` § "Session cleanup" and `docs/reference/COMMANDS.md` § `/ll:cleanup-worktrees` liveness descriptions; sync the `ll-adapt` mirror files (`.qwen/commands/ll/cleanup-worktrees.md`, `.gemini/commands/cleanup-worktrees.toml`) if `commands/cleanup-worktrees.md` prose changes.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- Findings grouped by category below.

### Behavior Parity
| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `worktree_utils.py::setup_worktree()` (line 278-281) | Writes in-tree `.ll-session-<pid>` unconditionally once the worktree exists | PRESERVED | Proposed Solution step 1: kept for backward compatibility |
| `worktree_utils.py::setup_worktree()` | No out-of-tree registry write exists today | CHANGED | Proposed Solution step 1 adds `<worktree_base>/.registry/<worktree-name>` write (pid + run id) alongside the marker |
| `worktree_utils.py::setup_worktree()` signature (line 160) | `(repo_path, worktree_path, branch_name, copy_files, logger, git_lock, base_branch=None, checkout_existing=False) -> None` — no `run_id` parameter or source | UNSPECIFIED | Program Design's registry shape is `{pid, run_id}`, but `run_id` exists nowhere in this module today (only as `ParallelOrchestrator.run_id`, `orchestrator.py:124`); issue does not say whether the signature grows a param or where non-orchestrator callers (`setup_prepatch_worktree`, `ensure_epic_branch`) source one |
| `worktree_utils.py::cleanup_worktree()` (lines 300-329) | Unconditional-teardown primitive: no-op if path missing, `preserve_before_teardown()`, `git worktree remove --force`, `shutil.rmtree` fallback, `git branch -D`; never itself reads a marker/registry to decide whether to proceed | PRESERVED | Proposed Solution only adds a registry write/remove here, not a liveness check — gating logic stays in `_cleanup_orphaned_worktrees()`/`session-cleanup.sh` |
| `worktree_utils.py::cleanup_worktree()` | No explicit registry-removal step (none exists yet) | CHANGED | Proposed Solution step 1: "at `cleanup_worktree`, remove it" — issue's own Integration Map already flags this site |
| `merge_coordinator.py::MergeCoordinator._cleanup_worktree()` (lines 1148-1192) | Independent reimplementation that never calls `worktree_utils.cleanup_worktree()` — no marker/registry interaction | UNSPECIFIED | Wiring Phase names this as needing "a registry-removal call ... or redirect it" but does not commit to which |
| `session-cleanup.sh::cleanup()` (lines 44-51, marker present + live PID) | `kill -0 "$PID"`; if alive, skip | PRESERVED (signal), precedence CHANGED | Proposal's Decision Rules put registry-check ahead of this marker check |
| `session-cleanup.sh::cleanup()` (lines 44-51, marker present + dead PID) | No `continue` — falls through to unconditional `git worktree remove --force` | UNSPECIFIED | Structurally identical to the zero-marker path the issue names, but not explicitly called out for hardening |
| `session-cleanup.sh::cleanup()` (line 45-52, no marker) | Falls straight through to unconditional `git worktree remove --force "$w"`, no further check | CHANGED | The exact behavior the issue targets: "consult the registry before its unconditional zero-marker deletion" |
| `session-cleanup.sh::cleanup()` zero-marker path | No `_is_ll_worktree()`-equivalent name filter, no dry-run, no removal logging (unlike the Python orchestrator) | UNSPECIFIED | Named as a contrast in this issue's own Codebase Research Findings, but not committed to as part of the fix |
| `session-cleanup.sh::cleanup()` (line 57, `cleanup \|\| true` at line 61) | Always returns 0; "must NEVER fail" invariant | PRESERVED | Issue doesn't spell out the failure-mode contract for a new registry read under this invariant |

### Files to Modify
- `scripts/little_loops/worktree_utils.py` — `setup_worktree()` writes the in-tree `.ll-session-<pid>` marker at line ~280 (`marker_path = worktree_path / f".ll-session-{os.getpid()}"`); this is the site where an out-of-tree registry write would be added, alongside (not replacing) the existing marker write per the issue's own backward-compatibility requirement.
- `scripts/little_loops/worktree_utils.py` — `cleanup_worktree()` (line 284) currently has no explicit marker-removal step; the in-tree marker disappears only as a side effect of `git worktree remove --force` / `shutil.rmtree` tearing down the whole directory. A registry-entry removal needs an explicit call here, since a `git clean -fdx` run from inside the worktree never goes through this function.
- `scripts/little_loops/parallel/orchestrator.py` — `_cleanup_orphaned_worktrees()` (starts at line 317) is where registry-first consultation and the conservative fallback would be added, ahead of the existing `.ll-session-*` marker glob (line 337) and `os.kill(pid, 0)` liveness probe.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/merge_coordinator.py` — `MergeCoordinator._cleanup_worktree()` (~line 1148-1192) independently reimplements worktree removal via direct git calls + `shutil.rmtree`; it does **not** call `worktree_utils.cleanup_worktree()` (corrects the "Conventions in Force" claim below that it wraps the shared function). Any registry-removal logic added only inside `worktree_utils.cleanup_worktree()` will silently not run on this path — it needs its own registry-removal call, or must be redirected to call the shared function.
- `hooks/scripts/session-cleanup.sh` — `cleanup()` needs to consult the new out-of-tree registry before its unconditional `git worktree remove --force` on the zero-marker path, using a `jq`-optional fallback matching its existing `command -v jq` pattern (line 24), since this script has no guaranteed JSON parser. Already identified in this issue's own Codebase Research Findings above as a third, unfixed reimplementation of the same liveness check.

### Conventions in Force
- An out-of-worktree, atomic-write JSON registry already exists and works: `ParallelOrchestrator._load_state`/`_save_state` (`scripts/little_loops/parallel/orchestrator.py:720-782`), persisting to `self.parallel_config.state_file` (default `.parallel-manage-state.json` at repo root, gitignored) via `tempfile.mkstemp` + `os.replace`. It stores an untyped JSON dict, not a dataclass — evidence that a bespoke schema/dataclass is optional for a new registry, not required.
- PID liveness is already checked with stdlib `os.kill(pid, 0)` in `_cleanup_orphaned_worktrees()` — `ProcessLookupError`/`ValueError` treated as not-live, `PermissionError` treated as live. No `psutil` or `lsof` usage exists anywhere in the worktree-liveness code path (repo-wide search for both found zero hits in this context) — there is no existing "live process cwd" primitive to extend.
- `session_lifecycle_events` (SQLite, via `record_session_lifecycle_event()`/`resolve_history_db()`) already records `worktree_create`/`worktree_delete` events, but it is write-only/audit-shaped — no function anywhere reads it back to answer "is worktree X still active." It is not a drop-in substitute for a liveness registry without adding a new query path.
- `WorkerPool._active_worktrees` (`scripts/little_loops/parallel/worker_pool.py`) is an in-memory `set[Path]` guarding same-process teardown races (BUG-142); it is per-process only and not consulted by `_cleanup_orphaned_worktrees()`, which runs at the start of a *new* process specifically to reap worktrees left by *previous, now-dead* processes — a new registry must be persisted to disk, not in-memory, to be visible cross-process.

### Tests
- `scripts/tests/test_orchestrator.py::TestOrphanedWorktreeCleanup` — existing marker/liveness coverage (`test_cleans_up_orphaned_worktrees`, `test_skips_worktree_owned_by_live_process`, `test_removes_worktree_with_dead_process_marker`, `test_detects_orphaned_worktrees`, plus branch-deletion variants) is the class a registry-consult test would extend.
- `scripts/tests/test_worktree_utils.py` — covers `setup_worktree`/`cleanup_worktree`; a registry write/remove test would live alongside these.
- `scripts/tests/test_cli_loop_worktree.py` — has a docstring-level assertion that `setup_worktree()` writes the `.ll-session-<pid>` marker (~line 265) and explicit marker-path construction (~line 289).
- `scripts/tests/test_hooks_integration.py::TestSessionCleanupWorktrees`-style tests cover the bash `session-cleanup.sh` marker check independently — these would need an equivalent fallback test if that script is also hardened (see Proposed Solution finding on the third implementation).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_worktree_concurrency.py::TestWorktreeConcurrency::test_concurrent_setup_cleanup_leaves_no_orphans` — direct, non-mocked concurrent caller of both `setup_worktree`/`cleanup_worktree` (BUG-140/142/579 regression guard); extend to assert no stray registry entries survive the same concurrent race.
- `scripts/tests/test_orchestrator.py::TestRunMethod` (~lines 2239-2293) — none of its existing tests (`test_run_returns_zero_on_dry_run`, `test_run_calls_cleanup`, etc.) assert that `_cleanup_orphaned_worktrees()` is invoked during `run()`; add coverage for the auto-invocation path at `orchestrator.py:245` (see new Dependent Files entry above).
- `scripts/tests/test_cli.py` (~lines 547-592) — `test_main_parallel_cleanup_orphans_mode` / `_dry_run_mode` assert `_cleanup_orphaned_worktrees.assert_called_once_with(dry_run=...)`; will break if registry-consult logic changes this method's signature.
- `scripts/tests/test_hooks_integration.py::TestSessionCleanupWorktrees::test_session_cleanup_removes_worktree_with_no_marker` (line 3261) — currently asserts the unsafe no-marker-means-delete behavior as *correct*; must be **rewritten**, not just extended, once `session-cleanup.sh` is hardened per the new Files to Modify entry above.
- `scripts/tests/test_merge_coordinator.py::TestCleanupWorktreeFallback` (`test_cleanup_nonexistent_worktree`, `test_cleanup_unlock_before_remove`, `test_cleanup_worktree_emits_worktree_delete`) — covers the independent `MergeCoordinator._cleanup_worktree()` path; needs new coverage once a registry-removal call is added there.
- `scripts/tests/test_test_tamper_guard.py:333,342,356` and `scripts/tests/test_git_operations.py:403,408` — additional direct, non-mocked callers of `setup_prepatch_worktree`/`cleanup_worktree`; verify unaffected by the new (optional) registry parameters.
- Closest precedent for the process-liveness fallback test shape (Proposed Solution step 3, flagged "unproven" in Program Design): `scripts/little_loops/cli/queue.py::_verify_owner_alive` + `scripts/tests/test_cli_queue_run.py` (lines 609-692) use `patch("<module>.psutil.Process", ...)` — the closest existing shape (cmdline-identity, not cwd-based) to mirror. No cwd-based precedent exists anywhere in the codebase, confirming the Program Design gap.

### Documentation
- `commands/cleanup-worktrees.md` — describes the `.ll-session-<pid>` marker and delegates to `ll-parallel --cleanup-orphans`.
- `docs/reference/API.md` — `setup_worktree`/`cleanup_worktree` reference entries describe the marker.
- `docs/development/TROUBLESHOOTING.md` — has `ll-parallel --cleanup-orphans` usage guidance.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` § "Session cleanup" — documents current liveness semantics in prose ("skipping any worktree owned by a live parallel worker"); also names a second config key, `automation.worktree_base` (via `Config.get_worktree_base()`), used by a different consumer (ll-auto/FSM sub-loop worktrees) — confirm during implementation whether that consumer also needs registry consultation.
- `docs/reference/COMMANDS.md` § `/ll:cleanup-worktrees` — separately restates the marker/liveness semantics from `commands/cleanup-worktrees.md`; needs the same update if the mechanism prose changes.
- `.qwen/commands/ll/cleanup-worktrees.md`, `.gemini/commands/cleanup-worktrees.toml` — git-tracked `ll-adapt`-generated mirrors that duplicate `commands/cleanup-worktrees.md`'s liveness prose verbatim, with no drift test (per ENH-2968); update alongside the source if its prose changes.

### Configuration
- `parallel.worktree_base` (`scripts/little_loops/config-schema.json`, default `.worktrees`) is the directory `_cleanup_orphaned_worktrees()` iterates over; `.worktrees/` itself is gitignored.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/parallel.py:212-225` — `main_parallel()`'s `--cleanup-orphans` handler calls `orchestrator._cleanup_orphaned_worktrees(dry_run=args.dry_run)` directly (private-method access is the established pattern here, per BUG-2324/BUG-2614).
- `scripts/little_loops/worktree_utils.py:388,551,857` — `setup_prepatch_worktree`, `verify_epic_branch_before_merge`, `ensure_epic_branch` all call `setup_worktree()`; each would pick up any registry write added there.
- `scripts/little_loops/worktree_utils.py:212,409,626,921` — the same four call sites (plus `setup_worktree`'s own failure-path cleanup) call `cleanup_worktree()`; each would pick up any registry-removal added there.
- `scripts/little_loops/parallel/worker_pool.py` (`_setup_worktree`/`_cleanup_worktree`) and `scripts/little_loops/parallel/merge_coordinator.py` (`_cleanup_worktree`) wrap the same `worktree_utils` functions — no separate marker/registry logic of their own to update.
- `scripts/little_loops/fsm/executor.py:1021,1665` — imports `worktree_utils` and calls `cleanup_worktree` directly for loop-run worktrees.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/orchestrator.py:245` — `ParallelOrchestrator.run()` calls `self._cleanup_orphaned_worktrees()` unconditionally (no `dry_run` guard) at the top of every `ll-parallel`/`ll-sprint` run, immediately before `self._load_state()` and before the `dry_run` branch that only gates `_execute()` vs `_dry_run()`. This is a second, independent invocation path from the `--cleanup-orphans` CLI handler (`cli/parallel.py:224`, which constructs its own orchestrator and calls `_cleanup_orphaned_worktrees(dry_run=args.dry_run)` directly, never reaching `.run()`). Any normal run also triggers real orphan deletion — directly relevant to the BUG-3373 mechanism, where a worktree was deleted mid-run by an unidentified concurrent actor.
- `scripts/little_loops/work_verification.py:227,235` — `_prepatch_teardown()` calls `cleanup_worktree()` inside a `try/except Exception: pass`.
- `scripts/little_loops/parallel/merge_coordinator.py:1148-1192` — `MergeCoordinator._cleanup_worktree()` does **not** delegate to `worktree_utils.cleanup_worktree()`; see corrected Files to Modify entry above.
- `hooks/scripts/session-cleanup.sh` (`cleanup()`, Claude Code Stop hook, `hooks/hooks.json:225,235`) — see corrected Files to Modify entry above.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- Findings grouped by category below.

### Types
- New registry entry shape (signature-shaped only, no existing symbol) — `{pid: int, run_id: str}` keyed by worktree name, mirroring the existing untyped JSON-dict convention `ParallelOrchestrator._load_state`/`_save_state` already write to `.parallel-manage-state.json` (`scripts/little_loops/parallel/orchestrator.py:720-782`). No new dataclass is required to match that convention.

### Signatures
- `setup_worktree(repo_path: Path, worktree_path: Path, branch_name: str, copy_files: ..., logger: Logger, git_lock: GitLock, base_branch: str | None = None, checkout_existing: bool = False) -> None` — `scripts/little_loops/worktree_utils.py:160`; existing signature the in-tree marker write is nested inside (~line 280).
- `cleanup_worktree(worktree_path: Path, repo_path: Path, logger: Logger, git_lock: GitLock, delete_branch: bool = True) -> None` — `scripts/little_loops/worktree_utils.py:284`; existing signature with no current marker/registry-removal step.
- `ParallelOrchestrator._cleanup_orphaned_worktrees(self, dry_run: bool = False) -> None` — `scripts/little_loops/parallel/orchestrator.py:317`; existing signature that performs the `.ll-session-*` glob (line 337) and `os.kill(pid, 0)` liveness probe.
- `ParallelOrchestrator._load_state(self) -> dict` / `_save_state(self, state: dict) -> None` — `scripts/little_loops/parallel/orchestrator.py:720-782`; existing atomic-write (`tempfile.mkstemp` + `os.replace`) JSON registry read/write pair — the closest existing precedent for a new out-of-tree registry.

### Decision Rules
- Liveness precedence order implied by Proposed Solution steps 2-3: registry entry with live pid -> live regardless of in-tree marker state; else in-tree `.ll-session-*` marker with live pid (existing `os.kill(pid, 0)` check) -> live; else the proposed process-cwd fallback -> live; else skip + warn, never delete.
- The process-cwd fallback ("a live process whose cwd is inside the worktree") has no confirming precedent in this codebase: repo-wide search found zero `lsof` usage and no `psutil` usage anywhere in the worktree-liveness code path — no existing site exercises process-cwd-based liveness detection, so this specific mechanism is unproven here.
  ⚠ Unproven mechanism — no precedent for process-cwd liveness check
- The registry-write/consult mechanism (steps 1-2) is not subject to the same gap — it directly extends the already-proven `_load_state`/`_save_state` atomic-write pattern (`scripts/little_loops/parallel/orchestrator.py:720-782`) with a different keyed shape.

### Call Path
`setup_worktree` (`worktree_utils.py:160`) -> [new registry write, alongside existing `.ll-session-<pid>` marker write at ~line 280] -> `cleanup_worktree` (`worktree_utils.py:284`) -> [new registry-entry removal] -> `ParallelOrchestrator._cleanup_orphaned_worktrees` (`orchestrator.py:317`) -> [new registry consult, before existing `.ll-session-*` glob at line 337] -> `os.kill(pid, 0)` (existing liveness probe, reused for both registry and marker pids)

## Impact

Closes the misclassification hole regardless of which actor deleted the
marker in the BUG-3373 incident; makes `ll-parallel --cleanup-orphans` safe
to run (manually or from automation) while epic/sprint runs are in flight.

## Related Key Documentation

- `scripts/little_loops/worktree_utils.py` (setup/cleanup, BUG-579 marker)
- `scripts/little_loops/parallel/orchestrator.py` (orphan detection)
- `commands/cleanup-worktrees.md`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-09-01
- **Reason**: Issue too large for single session (score 11/11, Very Large) —
  split into a proven core fix, an unproven fallback mechanism requiring a
  spike, and an independent bash-subsystem hardening pass.

### Decomposed Into
- ENH-3376: registry-based worktree liveness survives in-tree marker deletion
- ENH-3377: process-cwd fallback liveness check for marker-less and registry-less worktrees
- ENH-3378: harden session-cleanup.sh to consult the liveness registry before deleting

## Status

**Done** | Created: 2026-09-01 | Priority: P2


## Session Log
- `/ll:issue-size-review` - 2026-09-01T15:20:23 - `9c0fcbc0-a053-4d0e-b64f-70b69247e895.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-01T15:09:14 - `fa68ec03-cfff-4ad2-98dd-89441816e2c8.jsonl`
- `/ll:verify-issues` - 2026-09-01T15:02:59 - `f4e5bc48-e0c9-4a2a-a42a-bf5740564cd8.jsonl`
- `/ll:wire-issue` - 2026-09-01T14:59:11 - `a4d6cb8e-9d1d-452c-b878-6abe11cb342e.jsonl`
- `/ll:refine-issue` - 2026-09-01T14:47:46 - `0f67bee2-bbc4-4504-9d5f-1b8359cad82a.jsonl`
