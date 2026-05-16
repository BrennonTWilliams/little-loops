---
discovered_date: "2026-04-22"
discovered_by: issue-size-review

depends_on: [FEAT-1075, ENH-1176]
decision_needed: true
decision_question: "Should ll-loop --worktree worktrees (naming: <timestamp>-<safe-name>) be added to the orchestrator's orphan scan, or should loop cleanup remain atexit-only? Choosing 'yes' requires extending startswith('worker-') filters in orchestrator.py:385 and worker_pool.py:1316."
size: Very Large
confidence_score: 90
outcome_confidence: 56
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 18
parent: ENH-1197
status: done
completed_at: 2026-05-10T00:00:00Z
---

# ENH-1248: ll-loop Worktree Orphan Scan Coverage + worktree-health.yaml Fix

## Summary

Two related gaps: (1) `ll-loop --worktree` worktrees use a `<timestamp>-<safe-name>` naming pattern with no `worker-` prefix, so they are invisible to both `_cleanup_orphaned_worktrees()` (`startswith("worker-")` filter) and `cleanup-worktrees` (`-name "worker-*"`). (2) `worktree-health.yaml:14` greps for `ll-worktree` which matches no actual worktree name, making the built-in loop always report 0 orphaned worktrees.

## Parent Issue

Decomposed from ENH-1197: Harden Worktree Cleanup Against SIGKILL Mid-Teardown

## Decision Needed

**Should loop worktrees be added to the startup orphan scan?**

- `run.py:240` already registers an `atexit` cleanup; if the process is SIGKILLed, atexit does not run — same problem as parallel workers.
- Adding loop worktrees to the scan requires extending `startswith("worker-")` in `orchestrator.py:385` and `worker_pool.py:1316`, or introducing a shared name-predicate utility.
- Alternative: loop worktrees are short-lived and atexit coverage is sufficient; only fix the `worktree-health.yaml` grep.

Set `decision_needed: false` and document the chosen approach before implementing.

## Current Behavior

- `_cleanup_orphaned_worktrees()` in `orchestrator.py:248` uses `startswith("worker-")` — loop worktrees pass through unseen.
- `_check_pending_worktrees()` at `orchestrator.py:385` has the same filter.
- `cleanup_all_worktrees()` in `worker_pool.py:1316` has the same filter.
- `worktree-health.yaml:14` grep pattern `ll-worktree` matches neither `worker-*` nor `<timestamp>-<safe-name>` → always reports 0 orphans.

## Expected Behavior

1. **worktree-health.yaml fix** (always): update grep pattern to match real naming (`worker-*` for parallel, a timestamp prefix for loop). Prefer `git worktree list --porcelain` over a broken grep.
2. **Orphan scan extension** (if decision = yes): add a second scan pattern (or shared predicate) to `_cleanup_orphaned_worktrees()`, `_check_pending_worktrees()`, and `cleanup_all_worktrees()` that catches `<timestamp>-<safe-name>` worktrees belonging to dead processes.
3. **New test**: `test_cli_loop_worktree.py` — add integration test calling `cmd_run(worktree=True)` to cover the currently untested `run.py:201-243` path.

## Proposed Solution

### worktree-health.yaml

Replace the broken grep at line 14 with `git worktree list --porcelain | grep "^worktree" | tail -n +2` to enumerate all non-main worktrees accurately.

### Orphan scan extension (if approved)

Extract a `_is_ll_worktree(name: str) -> bool` predicate:
```python
def _is_ll_worktree(name: str) -> bool:
    return name.startswith("worker-") or re.match(r"^\d{8}-\d{6}-", name)
```
Replace all three `startswith("worker-")` usages in `orchestrator.py` and `worker_pool.py`.

### New integration test

In `test_cli_loop_worktree.py`, add a test that calls `cmd_run` with `args.worktree = True` and a mock loop YAML. This covers the `run.py:201-243` path currently at 0% coverage.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Confirmed naming**: `run.py:211-214` produces names via `datetime.now().strftime("%Y%m%d-%H%M%S")` + `re.sub(r"[^a-zA-Z0-9-]", "-", loop_name)` → e.g. `20260422-153012-worktree-health`. The `worker-` prefix is exclusively produced at `worker_pool.py:249`.
- **No existing predicate utility**: `_is_ll_worktree` does not exist anywhere yet; all three `startswith("worker-")` guards are inlined. Placing the new predicate in `worktree_utils.py` (already a shared module) is consistent with the codebase's shared-utility pattern.
- **Test pattern for `cmd_run(worktree=True)`**: Use `args.dry_run = True` to avoid FSM execution (established in `test_cli_loop_lifecycle.py:715-764`). Capture atexit registration with `patch("little_loops.cli.loop.run.atexit.register", side_effect=registered.append)` (pattern from `test_cli_loop_lifecycle.py:548-561`).
- **worktree-health.yaml fix**: The `tail -n +2` skip is essential — `git worktree list --porcelain` lists the main repo as the first `worktree` entry; skipping it avoids counting the main checkout as an orphan.

## Files to Modify

- `scripts/little_loops/loops/worktree-health.yaml` — fix grep pattern at line 14
- `scripts/little_loops/parallel/orchestrator.py` — extend `startswith("worker-")` filter (if decision = yes)
- `scripts/little_loops/parallel/worker_pool.py` — same filter at line 1316 (if decision = yes)
- `scripts/tests/test_cli_loop_worktree.py` — add `cmd_run(worktree=True)` integration test

## Integration Map

### Files to Modify (with line precision)
- `scripts/little_loops/loops/worktree-health.yaml:14` — Replace `grep -c "^worktree.*ll-worktree"` with `git worktree list --porcelain | grep "^worktree " | tail -n +2 | wc -l`
- `scripts/little_loops/parallel/orchestrator.py:248` — `_cleanup_orphaned_worktrees()` filter (if decision = yes)
- `scripts/little_loops/parallel/orchestrator.py:385` — `_check_pending_worktrees()` filter (if decision = yes)
- `scripts/little_loops/parallel/worker_pool.py:1316` — `cleanup_all_worktrees()` filter (if decision = yes)
- `scripts/little_loops/worktree_utils.py` — New `_is_ll_worktree()` predicate (if decision = yes; this module already exists as a shared utility)
- `scripts/tests/test_cli_loop_worktree.py` — New `cmd_run(worktree=True)` test

### Dependent Files (Context)
- `scripts/little_loops/cli/loop/run.py:211-214` — Produces `<timestamp>-<safe-name>` worktree names; format: `%Y%m%d-%H%M%S` + `re.sub(r"[^a-zA-Z0-9-]", "-", loop_name)`
- `scripts/little_loops/cli/loop/run.py:231-240` — Registers `atexit` cleanup handler — the only cleanup mechanism for loop worktrees; SIGKILL bypasses it
- `scripts/little_loops/parallel/worker_pool.py:249` — Produces `worker-<issue-id>-<timestamp>` names (exclusive to ll-parallel; confirms `worker-` prefix is not shared)
- `hooks/scripts/session-cleanup.sh:40` — Separate `git worktree list` cleanup in session hook; no change needed

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/parallel.py` — calls `pool.cleanup_all_worktrees()` at `main_parallel` entry point; automatically inherits predicate change, no direct edit needed
- `scripts/little_loops/parallel/orchestrator.py:332` — `_inspect_worktree` fallback: `worktree_path.name.replace("worker-", "parallel/")` produces wrong branch name for `<timestamp>-<safe-name>` loop worktrees (no `worker-` to replace); must be fixed if decision = yes
- `scripts/little_loops/parallel/orchestrator.py:336` — `_inspect_worktree` issue-ID regex `r"worker-([a-z]+-\d+)-\d{8}-\d{6}"` won't match loop worktree names; falls back to full dir name as `issue_id`; must be fixed if decision = yes
- `scripts/little_loops/worktree_utils.py:7-13` — module has no `import re`; must add before `_is_ll_worktree()` can call `re.match`

### Tests
- `scripts/tests/test_cli_loop_worktree.py` — Existing tests cover helpers and branch-name generation but NOT `cmd_run(worktree=True)` — add here
- `scripts/tests/test_orchestrator.py:350-534` — Existing orphan-cleanup tests using `worker-*`; update predicate tests here if extending
- `scripts/tests/test_worker_pool.py:800-816` — Existing `cleanup_all_worktrees()` tests using `patch.object(worker_pool, "_cleanup_worktree")`; update if extending predicate
- `scripts/tests/test_builtin_loops.py` — Existing tests for built-in loop YAMLs; add `worktree-health.yaml` grep-fix test here

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_orchestrator.py:375` — `TestOrphanedWorktreeCleanup.test_ignores_non_worker_directories`: currently only asserts `other-directory` is skipped; add a timestamp-prefixed dir case (e.g., `20260101-000000-my-loop`) to verify `_is_ll_worktree` correctly identifies it [update]
- `scripts/tests/test_orchestrator.py:595` — `TestCheckPendingWorktrees.test_ignores_non_worker_directories`: same gap, same fix needed [update]
- `scripts/tests/test_worker_pool.py:791` — `test_cleanup_all_worktrees_removes_all`: asserts exactly `len(cleanup_calls) == 2` using `worker-bug-001`/`worker-bug-002`; add timestamp-prefixed dir to verify it is also cleaned [update]
- `scripts/tests/test_cli_loop_worktree.py` — add `TestIsLLWorktree` predicate class: `worker-bug-001` → True, `20260101-000000-my-loop` → True, `other-directory` → False (use pattern from `TestSetupWorktree` class in same file) [new]
- `scripts/tests/test_builtin_loops.py:261` — add `worktree-health.yaml` action content assertion: read `data["states"]["check_worktrees"]["action"]`, assert `git worktree list --porcelain` is present and `ll-worktree` grep pattern is absent; follow `TestBuiltinLoopScratchIsolation` content-inspection pattern [new]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `commands/cleanup-worktrees.md:56,156` — `find "$WORKTREE_BASE" -maxdepth 1 -type d -name "worker-*"` won't enumerate loop worktrees; if decision = yes, update both `find` calls to also match `<timestamp>-<safe-name>` dirs [conditional on decision = yes]
- `commands/cleanup-worktrees.md:89` — `sed 's/^worker-//'` derives `parallel/<suffix>` branch names; loop worktrees use a different branch scheme; must be addressed alongside the `find` fix [conditional on decision = yes]
- `docs/ARCHITECTURE.md:373-375,821-826` — diagrams and filesystem layout examples show only `worker-1`, `worker-2`, `worker-N`; may want to note loop worktree naming pattern [low-priority, informational]
- `docs/development/TROUBLESHOOTING.md:143,174,423` — bash snippets reference `.worktrees/worker-1/`; no urgent change, but context is incomplete once loop worktrees are scanned [low-priority]

### Similar Patterns
- `scripts/tests/test_cli_loop_lifecycle.py:715-764` — Canonical `cmd_run()` test pattern: real `argparse.Namespace`, minimal loop YAML, `dry_run=True`
- `scripts/tests/test_cli_loop_lifecycle.py:548-561` — `atexit.register` mock pattern: `patch("...atexit.register", side_effect=registered.append)`
- `scripts/tests/test_orchestrator.py:362-368` — Worktree cleanup test pattern: assign `orchestrator._git_lock.run = mock_git_run` directly

## Implementation Steps

1. **Fix `worktree-health.yaml:14`** — Replace the broken grep action with:
   ```yaml
   action: |
     ORPHANED=$(git worktree list --porcelain 2>/dev/null | grep "^worktree " | tail -n +2 | wc -l | tr -d ' ' || echo 0)
     echo "$ORPHANED"
   ```
   Verify with `ll-loop worktree-health --dry-run` after editing.

2. **Resolve the decision** (see Decision Needed section) — set `decision_needed: false` and document the chosen option in the issue before proceeding.

3. **If decision = yes — extract `_is_ll_worktree()` predicate** in `scripts/little_loops/worktree_utils.py`:
   ```python
   def _is_ll_worktree(name: str) -> bool:
       return name.startswith("worker-") or re.match(r"^\d{8}-\d{6}-", name) is not None
   ```
   Replace the three inline guards:
   - `orchestrator.py:248` in `_cleanup_orphaned_worktrees()`
   - `orchestrator.py:385` in `_check_pending_worktrees()`
   - `worker_pool.py:1316` in `cleanup_all_worktrees()`

4. **Add `cmd_run(worktree=True)` test** in `scripts/tests/test_cli_loop_worktree.py`:
   - Construct `args` with `args.worktree = True`, `args.dry_run = True`, and all other required `Namespace` fields (see `test_cli_loop_lifecycle.py:715-764` for field list)
   - Patch `atexit.register` via `patch("little_loops.cli.loop.run.atexit.register", side_effect=registered.append)`
   - Assert that exactly one atexit handler was registered (the `_cleanup_worktree_on_exit` callable)
   - Assert the worktree path follows `<timestamp>-<safe-loop-name>` pattern

5. **Regression run**:
   ```bash
   python -m pytest scripts/tests/test_cli_loop_worktree.py scripts/tests/test_orchestrator.py scripts/tests/test_worker_pool.py scripts/tests/test_builtin_loops.py -v
   ```

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Add `import re` to `scripts/little_loops/worktree_utils.py` imports — prerequisite for `re.match` inside `_is_ll_worktree()`
7. Add `TestIsLLWorktree` unit test class in `scripts/tests/test_cli_loop_worktree.py` — test `worker-bug-001` → True, `20260101-000000-my-loop` → True, `other-directory` → False
8. Update `scripts/tests/test_orchestrator.py:375` and `test_orchestrator.py:595` — add timestamp-prefixed dir cases to the two `test_ignores_non_worker_directories` tests to exercise the new branch of `_is_ll_worktree`
9. Update `scripts/tests/test_worker_pool.py:791` — add a `20260101-000000-my-loop` directory to `test_cleanup_all_worktrees_removes_all` and assert it is included in cleanup (count becomes 3)
10. Add grep-content assertion for `worktree-health.yaml` in `scripts/tests/test_builtin_loops.py` — follow `TestBuiltinLoopScratchIsolation` pattern (line 261); read `data["states"]["check_worktrees"]["action"]`, assert `git worktree list --porcelain` present, assert `ll-worktree` string absent
11. **If decision = yes**: fix `orchestrator.py:332` `_inspect_worktree` branch-name fallback — replace `replace("worker-", "parallel/")` with logic that handles both `worker-` and `<timestamp>-<safe-name>` formats
12. **If decision = yes**: fix `orchestrator.py:336` `_inspect_worktree` issue-ID regex — either broaden or add a separate pattern for loop worktree names
13. **If decision = yes**: update `commands/cleanup-worktrees.md:56,89,156` — `find -name "worker-*"` and `sed 's/^worker-//'` must accommodate loop worktree dir names

## Acceptance Criteria

- `worktree-health.yaml` reports actual orphaned worktree count (not always 0)
- (If decision = yes) `ll-loop --worktree` orphaned worktrees are reclaimed by the startup scan
- `cmd_run(worktree=True)` path has at least one integration test
- Regression run: `python -m pytest scripts/tests/test_cli_loop_worktree.py -v`

## Labels

`parallel`, `worktree`, `loop`, `reliability`, `cleanup`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-22_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 56/100 → LOW

### Concerns
- **Unresolved design decision** (`decision_needed: true`): `worktree-health.yaml` fix is unambiguous and can start immediately, but the orphan-scan extension must wait for the decision. Recommend sequencing: YAML fix first, then decide.
- **Stale `depends_on` links**: FEAT-1075 and ENH-1176 are both deferred. Physical code targets (`orchestrator.py`, `worker_pool.py`) already exist — verify these are not true blockers before automation gates block on them.

### Outcome Risk Factors
- **Scope bifurcation**: decision=no is ~3 files; decision=yes is 9+ files across multiple subsystems. Plan time accordingly.
- **`_inspect_worktree` fallback** (`orchestrator.py:332,336`): `replace("worker-", "parallel/")` and the issue-ID regex have no clean analogue for `<timestamp>-<safe-name>` names; requires new conditional logic, not just a regex extension.
- **`commands/cleanup-worktrees.md` `sed` rewrite** (decision=yes): `sed 's/^worker-//'` for branch name derivation has no direct equivalent for loop worktree naming — likely needs a conditional branch in the script.

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-22T16:48:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/79aadd9e-32c2-44ea-be52-e9ec9bcff212.jsonl`
- `/ll:confidence-check` - 2026-04-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38129e4c-36a0-4f26-8372-94c74c5d520d.jsonl`
- `/ll:wire-issue` - 2026-04-22T16:43:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad23f624-a3c7-4b2d-af9f-9177a61c7d00.jsonl`
- `/ll:refine-issue` - 2026-04-22T16:37:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fdea6d06-afca-4b59-bf37-4de8c4f35cbe.jsonl`
- `/ll:issue-size-review` - 2026-04-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a4392751-fe1e-4762-b307-86db43c577b3.jsonl`
- `/ll:issue-size-review` - 2026-04-22T17:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/79aadd9e-32c2-44ea-be52-e9ec9bcff212.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-22
- **Reason**: Issue too large for single session (score 11/11 — Very Large)

### Decomposed Into

- ENH-1254: worktree-health.yaml Grep Fix + cmd_run(worktree=True) Integration Test
- ENH-1255: Orphan Scan Extension for ll-loop Worktrees (Decision-Gated)

---

**Decomposed** | Created: 2026-04-22 | Priority: P3
