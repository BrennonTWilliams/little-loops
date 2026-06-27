---
id: BUG-2324
title: cleanup-worktrees command drifts from canonical _is_ll_worktree logic
type: BUG
status: done
priority: P3
captured_at: '2026-06-26T22:26:49Z'
completed_at: '2026-06-27T05:42:28Z'
discovered_date: '2026-06-26'
discovered_by: audit
labels:
- worktree
- commands
- cleanup
relates_to:
- BUG-823
- ENH-1248
- ENH-1249
- ENH-1255
- ENH-2325
- ENH-2326
depends_on:
- BUG-2323
decision_needed: false
confidence_score: 94
outcome_confidence: 80
score_complexity: 14
score_test_coverage: 23
score_ambiguity: 23
score_change_surface: 20
---

# BUG-2324: cleanup-worktrees command drifts from canonical _is_ll_worktree logic

## Summary

`/ll:cleanup-worktrees` (`commands/cleanup-worktrees.md`) reimplements orphan detection and
teardown in bash rather than delegating to the orchestrator's hardened
`_cleanup_orphaned_worktrees` path. Its detection glob is **broader** than the canonical
Python predicate `_is_ll_worktree()` — risking deletion of unrelated directories — and it
only deletes branches for `worker-` worktrees, **leaking branches** for date-prefixed loop
worktrees. As a hand-written copy, it also drifts from the Python path every time the latter
is hardened.

## Motivation

This command is the user-facing recovery tool after an interrupted `ll-parallel`/`ll-loop`
run. It runs `git worktree remove --force` and `rm -rf` against directories it selects, so an
over-broad selector is a data-loss hazard, and a branch leak defeats the command's purpose
(cleaning up after a run). Backing it with the same Python logic the orchestrator already
trusts removes both the hazard and the perpetual drift.

## Current Behavior

In `commands/cleanup-worktrees.md`:

- Detection (`:56` and `:185`):
  ```bash
  WORKTREES=$(find "$WORKTREE_BASE" -maxdepth 1 -type d \( -name "worker-*" -o -name "[0-9]*" \) ...)
  ```
  The `[0-9]*` arm matches **any** directory whose name starts with a digit (e.g.
  `2024-archive`, `123-data`), far broader than the canonical predicate
  `_is_ll_worktree()` in `scripts/little_loops/worktree_utils.py:164-170`, which requires
  the strict form `^\d{8}-\d{6}-`.
- Branch deletion (`:90-91`, `:126-127`) is only derived for `worker-` worktrees:
  ```bash
  if echo "$WORKTREE_NAME" | grep -q "^worker-"; then
      BRANCH_NAME="parallel/$(echo "$WORKTREE_NAME" | sed 's/^worker-//')"
  ```
  Date-prefixed **loop** worktrees (`<ts>-<name>`, whose branch is the bare `<ts>-<name>`)
  get their directory removed but their branch is never deleted.

## Expected Behavior

The command selects exactly the directories `_is_ll_worktree()` would (no broader), and
deletes the branch for every ll-managed worktree it removes (parallel **and** loop), using
the actual branch name where possible.

## Steps to Reproduce

**Over-broad selection hazard:**
1. Create a non-ll directory starting with a digit in the worktree base (e.g. `2024-archive`)
2. Run `/ll:cleanup-worktrees`
3. Observe: `2024-archive` appears in the candidate list because `[0-9]*` matches it

**Branch leak (loop worktrees):**
1. Start an `ll-loop` run — this creates a date-prefixed worktree (e.g. `20260626-143022-my-loop`)
2. Interrupt the run mid-flight (Ctrl-C or kill the process)
3. Run `/ll:cleanup-worktrees`
4. Observe: worktree directory is removed, but `git branch --list 20260626-143022-my-loop` still exists

## Root Cause

The command predates / duplicates the Python orphan-scan path and was written as standalone
bash. There is no shared entrypoint that both the command and the orchestrator call, so the
two implementations diverge — the command already lags BUG-823 (actual-branch detection via
`git rev-parse`) and the loop-worktree handling from ENH-1248/ENH-1255.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Correction to "branch leak for loop worktrees":** The bash command's branch derivation
`else` branch (`BRANCH_NAME="$WORKTREE_NAME"`) is actually correct — since loop worktrees
use the same string for both directory name and branch name (created in
`cli/loop/run.py:cmd_run()` as `f"{timestamp}-{safe_name}"`), the bash command does delete
loop branches. The leak is in the Python paths, not the bash command.

**`_cleanup_orphaned_worktrees()` (`orchestrator.py:ParallelOrchestrator`) has two bugs:**
1. **Rev-parse timing bug**: `git rev-parse --abbrev-ref HEAD` is called *after*
   `git worktree remove --force` and `shutil.rmtree`. The worktree path no longer exists, so
   rev-parse always fails and `branch_name` is always `None`. No branch is ever deleted via
   this path for any worktree type.
2. **`parallel/` prefix guard**: branch deletion is conditional on
   `branch_name.startswith("parallel/")`. Even if the timing were fixed, loop-worktree
   branches (named `YYYYMMDD-HHMMSS-safe-name`) would still be skipped.

**`WorkerPool._cleanup_worktree()` (`worker_pool.py`) has the same `parallel/` prefix
guard** (`delete_branch = branch_name is not None and branch_name.startswith("parallel/")`),
though its rev-parse timing is correct (before removal). It is exposed via
`ll-parallel --cleanup` → `WorkerPool.cleanup_all_worktrees()`.

**Implication for the preferred fix:** Delegating the command to `_cleanup_orphaned_worktrees`
without fixing it first would *regress* loop-branch deletion. The preferred path requires
repairing the rev-parse timing and removing the `parallel/` prefix guard before it can safely
replace the bash logic.

#### Verification Pass (2026-06-26)

_Added by second `/ll:refine-issue` pass — confirmed against current codebase:_

**Exact line sequence in `_cleanup_orphaned_worktrees()` (`orchestrator.py` lines 273–308):**
- Lines 275–279: `git worktree unlock`
- Lines 281–285: `git worktree remove --force`
- Lines 288–289: `shutil.rmtree(worktree_path, ...)` (conditional)
- Lines 292–297: `subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree_path, ...)` ← always fails because `cwd` was just deleted

**Why existing tests don't expose the timing bug:** `test_deletes_branch_via_rev_parse` (line 500) and `test_skips_branch_deletion_for_non_parallel_branch` (line 566) both patch `subprocess.run` but mock `_git_lock.run` to return success *without* actually removing the worktree directory. So `worktree_path` still exists on disk when the patched `subprocess.run` fires, hiding the production failure. The proposed `test_rev_parse_called_before_remove` must use `worktree_path.exists()` as a call-order signal to expose the bug meaningfully.

**Correct reference pattern:** `worktree_utils.cleanup_worktree()` (lines 140–161) calls rev-parse at lines 141–147 *before* any removal — the exact ordering `_cleanup_orphaned_worktrees()` needs to adopt.

**`worker_pool.py:_cleanup_worktree()` timing is correct** (rev-parse at lines 736–744 fires before removal); the bug there is solely the `parallel/` prefix guard at line 744, confirmed by the legacy comment: `# Only delete branches with the parallel/ prefix (legacy behavior for ll-parallel)`. After the safe-guard helper is in place, the pre-check in `_cleanup_worktree()` becomes redundant — `cleanup_worktree()` in `worktree_utils` does its own rev-parse at line 141 when `delete_branch=True`.

**Related issues discovered in the same files:** ENH-2325 (remove fragile branch-name derivation residue in `orchestrator.py`) and ENH-2326 (serialize remaining git calls and add worktree concurrency test) address adjacent tech debt; added to `relates_to`.

## Proposed Solution

Preferred: **back the command with a single shared Python entrypoint.** Expose the
orchestrator's orphan-scan/cleanup as a callable (e.g. `ll-parallel cleanup-orphans
[--dry-run]` or a small `ll-worktrees clean` subcommand) that the command invokes, so there
is exactly one implementation of detection + liveness + teardown.

> **Selected:** Preferred path (shared entrypoint) — delegating to `ll-parallel --cleanup-orphans` removes both the over-broad selector hazard and perpetual bash/Python drift

Minimal alternative (if keeping bash): tighten the glob to the strict shape and add
loop-worktree branch deletion:
```bash
# detection — match only canonical ll worktrees
find "$WORKTREE_BASE" -maxdepth 1 -type d \
  \( -name "worker-*" -o -regex '.*/[0-9]\{8\}-[0-9]\{6\}-.*' \) ...
# branch name — prefer the actual branch
BRANCH_NAME=$(git -C "$w" rev-parse --abbrev-ref HEAD 2>/dev/null)
```

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-26.

**Selected**: Preferred path (shared entrypoint)

**Reasoning**: The codebase has strong, consistent precedents for every structural piece this option requires — flat-flag early-exit modes in `cli/parallel.py:183–190`, `add_dry_run_arg()` already wired into `main_parallel()`, and `Bash(ll-parallel:*)` delegation matching six other command files. Option B's 2-line glob fix is appealing for simplicity but its testability is illusory: there is no mechanism in the test suite to exercise the bash `find` command in a `.md` file, so the claimed "add one test" would only re-cover Python predicate behavior already tested in `TestIsLLWorktree`. The shared-entrypoint path also fixes the rev-parse timing bug in `orchestrator.py` that affects `ll-parallel` orchestration runs, not just the user-facing command.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Preferred path (shared entrypoint) | 2/3 | 2/3 | 3/3 | 2/3 | 9/12 |
| Minimal path (bash-only fix) | 1/3 | 3/3 | 1/3 | 3/3 | 8/12 |

**Key evidence**:
- Preferred path: `cli/parallel.py:183–190` (`--cleanup` flat-flag precedent), `cli_args.py:15` (`add_dry_run_arg`), `test_orchestrator.py:334` (11-test `TestOrphanedWorktreeCleanup` class), 6 command files using `Bash(ll-<tool>:*)` delegation
- Minimal path: 2-line fix at `commands/cleanup-worktrees.md:56,185`; `worktree_utils.py:164` (`_is_ll_worktree`) as spec reference only — no bash test coverage mechanism, perpetuates drift

## Integration Map

### Files to Modify
- `commands/cleanup-worktrees.md` — detection glob (`:56`, `:185`) and branch-derivation
  blocks (`:90-91`, `:126-127`); add `Bash(ll-parallel:*)` to `allowed-tools` if delegating.
- `scripts/little_loops/parallel/orchestrator.py:ParallelOrchestrator._cleanup_orphaned_worktrees()` —
  fix rev-parse timing (move before `worktree remove`); remove `parallel/` prefix guard.
- `scripts/little_loops/cli/parallel.py:main_parallel()` — add `--cleanup-orphans` flag
  following the existing flat-flag pattern at lines 183–190; wire to the fixed
  `_cleanup_orphaned_worktrees`; add `--dry-run` via `add_dry_run_arg()` from `cli_args.py`.
- `scripts/little_loops/parallel/worker_pool.py:WorkerPool._cleanup_worktree()` — remove
  `parallel/` prefix guard so loop-worktree branches are also deleted.

### Similar Patterns / Reuse
- `scripts/little_loops/worktree_utils.py:_is_ll_worktree()` — source-of-truth predicate
  (both Python paths already call it; the bash command should match its regex exactly).
- `scripts/little_loops/parallel/orchestrator.py:ParallelOrchestrator._cleanup_orphaned_worktrees()` —
  implements liveness (`.ll-session-<pid>` + `os.kill(pid, 0)`), `unlock`→`remove`, ghost-ref
  prune; needs rev-parse ordering fix and `parallel/` guard removal before delegation.
- `scripts/little_loops/cli_args.py:add_dry_run_arg()` — shared helper used by `ll-parallel`,
  `ll-sprint`; call on the new subparser/flag.
- `scripts/little_loops/cli/sprint/__init__.py:main_sprint()` — canonical subparser-with-`set_defaults`
  pattern if a subcommand shape is preferred over another flat flag.
- `scripts/little_loops/cli/loop/run.py:cmd_run()` (lines 370–409) — confirms loop worktree
  naming: directory name == branch name == `f"{YYYYMMDD-HHMMSS}-{safe_name}"`.
- `commands/review-sprint.md` — example of a command delegating to a Python CLI tool via
  `allowed-tools: [Bash(ll-sprint:*)]` and direct `ll-sprint <subcmd>` calls.

### Dependent Files (Callers/Importers)
- N/A — command invoked directly by users; no programmatic callers in automation code.
- `scripts/little_loops/parallel/orchestrator.py:ParallelOrchestrator.run()` (line 165) —
  calls `_cleanup_orphaned_worktrees()` unconditionally before `_load_state()`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/worktree-health.yaml` — the `cleanup_worktrees` state (`:25-31`,
  `action_type: prompt`) invokes `/ll:cleanup-worktrees`. It inherits the delegated behavior
  automatically once the command body changes — **no YAML edit required**, but it is the one
  loop-ecosystem consumer of this command. [Agent 2/3 finding]
- `scripts/little_loops/parallel/orchestrator.py:_cleanup_orphaned_worktrees()` gains a `dry_run`
  param: all 13 call sites in `test_orchestrator.py:TestOrphanedWorktreeCleanup` and the
  production call at `orchestrator.py:165` pass no args, so a `dry_run=False` default keeps them
  valid without edits. [Agent 2/3 finding]

### Tests
- `scripts/tests/test_orchestrator.py:TestOrphanedWorktreeCleanup` — existing test class
  (lines 334–564); extend with: loop-worktree branch deletion case, non-ll digit-prefixed dir
  not selected (e.g. `2024-archive`).
  - **Sensitive to the guard design** — `test_skips_branch_deletion_for_non_parallel_branch`
    (line 566) feeds `"main\n"` and asserts `deleted_branches == []`. With the **safe replacement
    guard** (Impl Step 1 — accept loop+parallel shapes, reject `main`/`master`/`HEAD`) this test
    stays GREEN and is load-bearing: it proves orphan cleanup never deletes `main`. Do NOT flip
    it to assert deletion; instead add a separate `test_deletes_loop_worktree_branch` for the
    loop-branch case. [Agent 1/3 + Agent 3/3 finding]
  - **Missing timing test** — no existing test asserts `git rev-parse` fires *before*
    `worktree remove` (the core of the timing-bug fix); add one (see Impl Step 5). [Agent 3/3]
- `scripts/tests/test_cli.py:TestParallelArgumentParsing` — add `--cleanup-orphans` / `--dry-run`
  arg-parsing test following the `test_dry_run_flag` pattern.
- `scripts/tests/test_worker_pool.py:TestWorktreeSetupCleanup` — existing test class covering
  `WorkerPool._cleanup_worktree()` and `cleanup_all_worktrees()`:
  - `test_cleanup_worktree_deletes_parallel_branch` (line 751) — won't break (still valid for
    `parallel/` branches), but add companion `test_cleanup_worktree_deletes_loop_branch` to
    confirm branch deletion for `YYYYMMDD-HHMMSS-name` style branches. [Agent 1/3 finding]
  - `test_cleanup_all_worktrees_removes_all` (line 792) — already tests timestamp-prefixed loop
    dirs; no structural change needed. [Agent 1/3 finding]
- `scripts/tests/test_cli_args.py` — verifies `add_dry_run_arg` wiring across CLI modules;
  update to cover `--cleanup-orphans` + `--dry-run` for `main_parallel`. [Agent 1/3 finding]
- `scripts/tests/test_cli_loop_worktree.py:TestWorkerPoolCleanupBackwardsCompat::test_non_parallel_branch_not_deleted`
  (line 488) — **WILL BREAK** (legitimately): feeds a loop branch `20260101-000000-my-loop` and
  asserts it is NOT deleted by `WorkerPool._cleanup_worktree()`. The fix's whole point is that
  loop branches DO get deleted, so this assertion must invert to assert deletion. The enclosing
  class `TestWorkerPoolCleanupBackwardsCompat` (line 433) and its docstring ("…still only deletes
  parallel/ branches") encode the old contract and must be renamed/rewritten. [Agent 2/3 finding]
- `scripts/tests/test_subprocess_mocks.py:TestWorkerPoolGitOperations::test_cleanup_worktree_removes_worktree`
  (line 679) — **stale comment, won't fail**: mock returns `"main\n"` with a comment claiming the
  `parallel/` guard suppresses deletion. With the safe guard (rejects `main`) the behavior is
  preserved, but the comment's rationale is now wrong — update the comment to reference the
  `main`/`master`/`HEAD` exclusion instead of the `parallel/` prefix. [Agent 2/3 finding]
- Add integration test: live-process-owned worktree is skipped; orphaned one is cleaned.

### Documentation
- `docs/reference/CLI.md` — update `ll-parallel` entry if `--cleanup-orphans` is added (the
  existing `--cleanup` row is at `:343`, usage example at `:379`).
- `commands/help.md` — verify cleanup-worktrees description remains accurate.
- `docs/development/TROUBLESHOOTING.md` — two sections point users at `ll-parallel --cleanup` as
  the post-interruption recovery tool: "Worktree creation fails" (`:131`) and "Too many
  worktrees" (`:200`). After the fix, `--cleanup` (wipes ALL worktrees via
  `cleanup_all_worktrees`) and `--cleanup-orphans` (liveness-aware, skips live-process worktrees
  via `_cleanup_orphaned_worktrees`) have different semantics — clarify which to use for recovery.
  [Agent 2/3 finding]

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` (`:784` `WorkerPool` class diagram) and `docs/reference/API.md`
  (`:2905` methods table) document only the public `cleanup_all_worktrees()` — signature
  unchanged, so **no update required**; recorded here to mark them as audited. [Agent 2/3]
- `docs/reference/COMMANDS.md` — `/ll:cleanup-worktrees` entry at `:513` (section) and
  `:1023` (table row); update section description to reflect that the command now delegates
  to `ll-parallel --cleanup-orphans` instead of running its own bash detection. [Agent 1/2/3 finding]

### Configuration
- N/A — no config keys govern this command's behavior.

## Implementation Steps

### Preferred path (shared entrypoint)

1. **Fix `orchestrator.py:_cleanup_orphaned_worktrees()`** — move `git rev-parse
   --abbrev-ref HEAD` call to *before* `git worktree remove --force` so `branch_name` is
   resolved while the worktree still exists; replace the `branch_name.startswith("parallel/")`
   guard with a **safe replacement guard** (see ⚠️ below) rather than deleting unconditionally.
   - ⚠️ **SAFETY — do not delete unconditionally** [Agent 3/3 finding]: a naive "delete when
     non-empty" would delete the user's `main` branch if an orphaned worktree's HEAD resolves to
     `main` (or returns the literal `HEAD` in detached state). The replacement guard must accept
     ll-managed branch shapes (`parallel/*` **and** `^\d{8}-\d{6}-` loop branches — ideally reuse
     `_is_ll_worktree`'s regex against the branch name) and reject `main`/`master`/`HEAD`. This is
     why `test_skips_branch_deletion_for_non_parallel_branch` (which feeds `"main\n"`) must keep
     asserting *no deletion* — only its loop-branch sibling flips to assert deletion.
2. **Fix `worker_pool.py:WorkerPool._cleanup_worktree()`** — replace the same `parallel/`
   prefix guard (`delete_branch = branch_name is not None and branch_name.startswith("parallel/")`)
   with the identical safe guard from step 1 (accept loop + parallel branch shapes, reject
   `main`/`master`/`HEAD`). Keep the guard logic in one shared helper so both paths stay in sync.
3. **Expose new CLI flag in `cli/parallel.py:main_parallel()`** — add
   `parser.add_argument("--cleanup-orphans", action="store_true", ...)` following the
   `--cleanup` flat-flag pattern at lines 183–190; call `add_dry_run_arg(parser)` from
   `cli_args.py`; construct a minimal `ParallelOrchestrator` and invoke
   `_cleanup_orphaned_worktrees()` (pass `dry_run` as a new parameter).
4. **Update `commands/cleanup-worktrees.md`** — replace the `find … [0-9]*` detection block
   and branch-teardown logic with a single `ll-parallel --cleanup-orphans [--dry-run]` call;
   add `Bash(ll-parallel:*)` to the `allowed-tools` frontmatter; remove now-redundant bash.
   (Skill bridge `skills/ll-cleanup-worktrees/SKILL.md` is a body-less Codex stub — no edit
   needed; it points at this command. [Agent 2/3])
4b. **Update `docs/development/TROUBLESHOOTING.md`** — in "Worktree creation fails" (`:131`) and
   "Too many worktrees" (`:200`), distinguish `--cleanup` (removes ALL worktrees) from the new
   liveness-aware `--cleanup-orphans` and point recovery guidance at the latter. [Agent 2/3]
5. **Tests** — extend `test_orchestrator.py:TestOrphanedWorktreeCleanup` with loop-branch
   deletion and non-ll digit-dir exclusion cases; add `--cleanup-orphans` arg test to
   `test_cli.py:TestParallelArgumentParsing`.
   - **Keep + add sibling** `test_orchestrator.py:test_skips_branch_deletion_for_non_parallel_branch`
     (line 566) — feeds `"main\n"`; with the safe guard (step 1) it should STILL assert no
     deletion (the guard rejects `main`). Add a sibling `test_deletes_loop_worktree_branch` that
     feeds a `20260101-120000-my-loop` branch and asserts deletion. [Agent 3/3 finding —
     corrects the earlier "flip the assertion" note: the `main` case must remain protected]
   - **Add** `test_orchestrator.py:test_rev_parse_called_before_remove` — assert
     `subprocess.run(["git", "rev-parse", ...])` fires while `worktree_path.exists()` is still
     `True`, using the call-order tracking pattern from `test_unlock_called_before_remove`
     (line 599). This is the only test that actually guards the timing-bug fix. [Agent 3/3 finding]
   - **Update** `test_orchestrator.py:test_deletes_branch_via_rev_parse` (line 500) — docstring
     and `patch("subprocess.run")` placement should reflect rev-parse now firing before removal;
     assertion value (`["parallel/bug-001-20260101-120000"]`) stays valid. [Agent 3/3 finding]
   - **Add** `test_worker_pool.py:test_cleanup_worktree_deletes_loop_branch` — companion to
     `test_cleanup_worktree_deletes_parallel_branch` (line 751) verifying `YYYYMMDD-HHMMSS-name`
     branches are deleted; also add a `main` case asserting `_cleanup_worktree` does NOT delete
     `main`. [Agent 3/3 finding]
   - **Update** `test_cli.py:TestParallelArgumentParsing._parse_parallel_args` (line 110) — this
     helper manually re-declares the parser, so it must add
     `parser.add_argument("--cleanup-orphans", action="store_true")`; update `test_default_args`
     (line 127) with `assert args.cleanup_orphans is False`. [Agent 3/3 finding]
   - **Add** `test_cli.py:TestMainParallelIntegration.test_main_parallel_cleanup_orphans_mode` —
     follows `test_main_parallel_cleanup_mode` (line 493) but patches `ParallelOrchestrator` and
     asserts `_cleanup_orphaned_worktrees()` is called (NOT `pool.cleanup_all_worktrees()`, which
     is the existing `--cleanup` path). [Agent 3/3 finding]
   - **Update** `test_cli_loop_worktree.py:TestWorkerPoolCleanupBackwardsCompat::test_non_parallel_branch_not_deleted`
     (line 488) — this asserts a loop branch is NOT deleted; invert it to assert deletion and
     rename the enclosing class/docstring (its "still only deletes parallel/ branches" contract is
     exactly what the fix removes). [Agent 2/3 finding]
   - **Update** `test_subprocess_mocks.py:test_cleanup_worktree_removes_worktree` (line 679
     comment) — fix the stale "skips branch deletion" rationale to reference the `main`/`HEAD`
     exclusion, not the `parallel/` prefix. [Agent 2/3 finding]
   - **Add** `test_cli_args.py` coverage for `--cleanup-orphans` + `--dry-run` combo.

### Minimal path (bash-only fix, no new entrypoint)

1. **Tighten glob** — replace `[0-9]*` with the strict `find … -regex '.*/[0-9]\{8\}-[0-9]\{6\}-.*'`
   form in lines 56 and 185 of `commands/cleanup-worktrees.md`.
2. **Verify branch logic** — the existing `else` branch already handles loop worktrees
   correctly; no change needed. Add a comment documenting this.
3. **Test** — add a `git worktree list`-based test asserting a `2024-archive` dir is not
   selected.

## Impact

- **Priority**: P3 — recovery tool; over-broad selection is a latent data-loss hazard and
  loop branches leak, but the happy path works.
- **Effort**: Small (glob/branch fix) to Medium (shared entrypoint).
- **Risk**: Low — narrowing selection is strictly safer; consolidation is well-scoped.
- **Breaking Change**: No.

## Session Log
- `/ll:ready-issue` - 2026-06-27T05:32:21 - `34129952-4562-46d3-8f9c-64cd8e4081c0.jsonl`
- `/ll:confidence-check` - 2026-06-27T12:00:00Z - `2841a396-d9ad-49fe-b2ad-231892b671df.jsonl`
- `/ll:wire-issue` - 2026-06-27T05:10:05 - `c27a4feb-a659-4f2c-a93b-5a4a6ecb65d3.jsonl`
- `/ll:refine-issue` - 2026-06-27T05:00:18 - `1ca5c0eb-921e-46b2-9d5f-af2ff3ccc1c0.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-27T01:23:43 - `14bc42e7-76a4-4427-8347-44e5b2c9966b.jsonl`
- `/ll:confidence-check` - 2026-06-26T23:50:00Z - `0c53424b-20aa-4cfb-80cf-802b5967df71.jsonl`
- `/ll:wire-issue` - 2026-06-26T23:34:56 - `0ccf7a6a-f985-42f6-bb18-b2c54b21a3f0.jsonl`
- `/ll:decide-issue` - 2026-06-26T23:07:30 - `4c0744ee-e575-4909-b378-3548d491b5eb.jsonl`
- `/ll:refine-issue` - 2026-06-26T22:59:28 - `585197a2-6eeb-4c75-8344-69370d9d5505.jsonl`
- `/ll:format-issue` - 2026-06-26T22:41:43 - `10e91f97-ca13-4435-b4fb-cab31a804f4d.jsonl`
- audit (branch & worktree management) - 2026-06-26 - `thoughts/audits/2026-06-26-branch-worktree-management-audit.md`
