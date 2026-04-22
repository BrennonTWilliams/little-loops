---
id: ENH-1255
priority: P3
parent_issue: ENH-1248
depends_on: [ENH-1254]
discovered_date: "2026-04-22"
discovered_by: issue-size-review
decision_needed: true
decision_question: "Should ll-loop --worktree worktrees (naming: <timestamp>-<safe-name>) be added to the orchestrator's orphan scan, or should loop cleanup remain atexit-only? Choosing 'yes' requires extracting _is_ll_worktree() predicate and extending three startswith('worker-') guards plus fixing two _inspect_worktree fallbacks in orchestrator.py."
size: Medium
confidence_score: 75
outcome_confidence: 56
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 18
---

# ENH-1255: Orphan Scan Extension for ll-loop Worktrees (Decision-Gated)

## Summary

`ll-loop --worktree` worktrees use a `<timestamp>-<safe-name>` naming pattern with no `worker-` prefix, making them invisible to `_cleanup_orphaned_worktrees()`, `_check_pending_worktrees()`, and `cleanup_all_worktrees()`. If SIGKILLed, the atexit handler does not run and the worktree leaks. This issue decides whether to extend the orphan scan to cover loop worktrees and, if yes, implements the extension.

## Parent Issue

Decomposed from ENH-1248: ll-loop Worktree Orphan Scan Coverage + worktree-health.yaml Fix

## Decision Needed

**Should loop worktrees be added to the startup orphan scan?**

- `run.py:231-240` registers an `atexit` cleanup; if the process is SIGKILLed, atexit does not run — same problem as parallel workers.
- Adding loop worktrees requires a shared `_is_ll_worktree()` predicate replacing three `startswith("worker-")` guards, plus fixing two `_inspect_worktree` fallbacks that assume `worker-` prefix.
- Alternative: loop worktrees are short-lived and atexit coverage is sufficient; only fix `worktree-health.yaml` (already handled in ENH-1254); close this issue as "won't implement".

Set `decision_needed: false` and document the chosen approach before implementing.

## Current Behavior

- `_cleanup_orphaned_worktrees()` at `orchestrator.py:248` uses `startswith("worker-")` — loop worktrees pass through unseen.
- `_check_pending_worktrees()` at `orchestrator.py:385` has the same filter.
- `cleanup_all_worktrees()` at `worker_pool.py:1316` has the same filter.

## Expected Behavior (if decision = yes)

- All three cleanup functions recognise both `worker-*` (parallel) and `<timestamp>-<safe-name>` (loop) worktrees.
- `_inspect_worktree` correctly derives branch names and issue IDs for loop worktrees.
- `commands/cleanup-worktrees.md` `find` and `sed` commands accommodate loop worktree naming.

## Proposed Solution (if decision = yes)

### Extract `_is_ll_worktree()` predicate

Place in `scripts/little_loops/worktree_utils.py` (already a shared module); add `import re` at the top:

```python
def _is_ll_worktree(name: str) -> bool:
    return name.startswith("worker-") or re.match(r"^\d{8}-\d{6}-", name) is not None
```

Replace all three inline `startswith("worker-")` guards with `_is_ll_worktree(name)`.

### Fix `_inspect_worktree` fallbacks

- `orchestrator.py:332` — `replace("worker-", "parallel/")` produces wrong branch name for loop worktrees; add a conditional for timestamp-prefixed names.
- `orchestrator.py:336` — issue-ID regex `r"worker-([a-z]+-\d+)-\d{8}-\d{6}"` won't match loop names; add a separate pattern or fall through gracefully.

### Update `commands/cleanup-worktrees.md`

- `cleanup-worktrees.md:56,156` — `find … -name "worker-*"` must also match `<timestamp>-<safe-name>` dirs.
- `cleanup-worktrees.md:89` — dry-run `sed 's/^worker-//'` branch derivation needs a conditional for loop worktree names.
- `cleanup-worktrees.md:112` — live-run `sed 's/^worker-//'` branch derivation (same fix as line 89, separate code path).

## Implementation Steps (if decision = yes)

_See "Proposed Solution" below for detailed steps. Wiring phase at the end of this section._

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Update `scripts/tests/test_orchestrator.py:615-637` (`test_extracts_issue_id`) — verify the `_inspect_worktree` fallback fix at `orchestrator.py:332` preserves `worker-` → `parallel/` for `worker-*` names; update assertion if the conditional adds a new branch that changes behavior
2. Update `scripts/little_loops/loops/worktree-health.yaml:29` — change action prompt from "ll-parallel runs" to "ll-parallel and ll-loop --worktree runs"
3. Optionally update `docs/ARCHITECTURE.md:820-826` — add `<timestamp>-<safe-name>/` to the `.worktrees/` layout diagram
4. Optionally update `docs/guides/LOOPS_GUIDE.md:538` — expand orphaned-worktrees description to mention loop worktrees

## Files to Modify (if decision = yes)

- `scripts/little_loops/worktree_utils.py` — add `import re` and `_is_ll_worktree()` predicate
- `scripts/little_loops/parallel/orchestrator.py:248,332,336,385` — replace `startswith("worker-")` guards and fix `_inspect_worktree` fallbacks
- `scripts/little_loops/parallel/worker_pool.py:1316` — replace `startswith("worker-")` guard
- `commands/cleanup-worktrees.md:56,89,112,156` — update `find` and `sed` patterns (line 112 is live-run branch derivation, separate from dry-run at line 89)
- `scripts/tests/test_cli_loop_worktree.py` — add `TestIsLLWorktree` class: `worker-bug-001` → True, `20260101-000000-my-loop` → True, `other-directory` → False
- `scripts/tests/test_orchestrator.py:375,595` — add timestamp-prefixed dir case to the two `test_ignores_non_worker_directories` tests
- `scripts/tests/test_worker_pool.py:791` — add `20260101-000000-my-loop` dir to `test_cleanup_all_worktrees_removes_all` and assert count becomes 3

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/parallel.py:163` — calls `pool.cleanup_all_worktrees()` directly; after the fix, loop worktrees are cleaned through this call path with no code changes needed here
- `scripts/little_loops/cli/sprint/run.py:18` — uses `ParallelOrchestrator`, which calls `_cleanup_orphaned_worktrees()` and `_check_pending_worktrees()` during startup; no code changes needed, but loop worktrees will now be scanned during sprint runs too
- `scripts/little_loops/cli/loop/run.py:204` — imports `setup_worktree`; the worktree it creates is exactly what ENH-1255 extends the scan to cover; no code changes needed here

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_orchestrator.py:615-637` (`test_extracts_issue_id`) — **may break**: exercises the `_inspect_worktree` fallback at `orchestrator.py:332` (the exact fallback ENH-1255 modifies); asserts `result.branch_name == "parallel/enh-042-20260117-150000"` via the string-replace path; survives only if the fix preserves `worker-` → `parallel/` for `worker-*` names and only adds conditional logic for timestamp-prefixed names

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md:820-826` — directory layout diagram shows only `worker-N/` naming under `.worktrees/`; loop worktree directories (`<timestamp>-<safe-name>/`) are absent; low-priority doc update
- `docs/guides/LOOPS_GUIDE.md:538` — `worktree-health` loop description says it monitors orphaned worktrees left by `ll-parallel` runs only; after ENH-1255, loop worktrees appear too

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/worktree-health.yaml:29` — action prompt reads "Remove orphaned worktrees from interrupted ll-parallel runs"; after ENH-1255, loop worktrees that leaked via SIGKILL also appear in the count; update the prompt to mention both `ll-parallel` and `ll-loop --worktree`

## Codebase Research Findings

- **Confirmed naming**: `run.py:211-214` produces `datetime.now().strftime("%Y%m%d-%H%M%S")` + `re.sub(r"[^a-zA-Z0-9-]", "-", loop_name)`.
- **No existing predicate**: all three `startswith("worker-")` guards are inlined; placing the predicate in `worktree_utils.py` is consistent with the shared-utility pattern.
- **`worker-` prefix exclusive to ll-parallel**: `worker_pool.py:249` is the only producer.
- **`worktree_utils.py` has no `import re`**: the proposed `_is_ll_worktree()` requires adding it.
- **Loop worktrees do get the `.ll-session-<pid>` marker**: `worktree_utils.setup_worktree()` at `worktree_utils.py:98-99` writes it unconditionally; the live-PID check in `_cleanup_orphaned_worktrees` will work correctly once the naming guard is fixed.
- **`cleanup-worktrees.md` has 4 locations to fix** (issue originally listed 3): `find -name "worker-*"` at lines 56 and 156; dry-run `sed 's/^worker-//'` at line 89; live-run `sed 's/^worker-//'` at line 112.
- **`_inspect_worktree` fallback at `orchestrator.py:332`**: uses `worktree_path.name.replace("worker-", "parallel/")` — loop names have no `"worker-"` substring so the replace is a no-op, leaving the full dir name as the branch string (incorrect).
- **`_inspect_worktree` fallback at `orchestrator.py:336`**: regex `r"worker-([a-z]+-\d+)-\d{8}-\d{6}"` anchors on `"worker-"` so loop names fall through to `issue_id = worktree_path.name` (the full timestamp dir string as the ID).
- **`test_cli_loop_worktree.py` already exists** (480 lines, 4 test classes); `TestIsLLWorktree` is a new class to add to it — no new file needed.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `cleanup-worktrees.md:112` — `BRANCH_NAME="parallel/$(echo "$WORKTREE_NAME" | sed 's/^worker-//')"` (live-run path; same fix as dry-run line 89, separate code branch)
- `orchestrator.py:247-248` — `for item in worktree_base.iterdir(): if item.is_dir() and item.name.startswith("worker-"):`
- `orchestrator.py:382-385` — list comprehension: `[item for item in worktree_base.iterdir() if item.is_dir() and item.name.startswith("worker-")]`
- `worker_pool.py:1315-1316` — `for worktree_dir in worktree_base.iterdir(): if worktree_dir.is_dir() and worktree_dir.name.startswith("worker-"):`
- `test_orchestrator.py:375-387` — `test_ignores_non_worker_directories` (orphan cleanup): creates `"other-directory"`, asserts it still exists after `_cleanup_orphaned_worktrees()` — add timestamp-dir case here with opposite assertion (removed)
- `test_orchestrator.py:595-608` — `test_ignores_non_worker_directories` (pending): same pattern for `_check_pending_worktrees()`, asserts `result == []`
- `test_worker_pool.py:791-816` — `test_cleanup_all_worktrees_removes_all`: uses `patch.object(worker_pool, "_cleanup_worktree", side_effect=mock_cleanup)` + `cleanup_calls: list[Path]`, asserts `len == 2`; add timestamp dir and change assertion to `== 3`
- `test_cli_loop_worktree.py:458-479` — `TestBranchNameGeneration` (closest analog): pure-logic class, no fixtures, imports inside test bodies — model `TestIsLLWorktree` after this style

## Similar Patterns

- `scripts/tests/test_orchestrator.py:350-373` — `test_cleans_up_orphaned_worktrees`: creates `worker-*` dirs, mocks `_git_lock.run`, verifies no exception
- `scripts/tests/test_orchestrator.py:350-534` — existing orphan-cleanup tests using `worker-*`
- `scripts/tests/test_worker_pool.py:800-816` — existing `cleanup_all_worktrees()` tests

## Acceptance Criteria

- `_is_ll_worktree("20260422-153012-my-loop")` returns `True`
- `_is_ll_worktree("other-directory")` returns `False`
- `_cleanup_orphaned_worktrees()` removes a leaked `<timestamp>-<safe-name>` directory
- All three test files updated with timestamp-prefixed dir cases pass
- Regression: `python -m pytest scripts/tests/test_orchestrator.py scripts/tests/test_worker_pool.py scripts/tests/test_cli_loop_worktree.py -v`

## Labels

`parallel`, `worktree`, `loop`, `reliability`, `cleanup`

## Session Log
- `/ll:wire-issue` - 2026-04-22T17:09:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/509cc566-db9f-4e7a-a3c5-21f738bb3a0b.jsonl`
- `/ll:refine-issue` - 2026-04-22T17:04:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8c3dd3b0-98a8-494a-8720-4fa7296292d6.jsonl`

- `/ll:issue-size-review` - 2026-04-22T17:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/79aadd9e-32c2-44ea-be52-e9ec9bcff212.jsonl`

---

**Open** | Created: 2026-04-22 | Priority: P3
