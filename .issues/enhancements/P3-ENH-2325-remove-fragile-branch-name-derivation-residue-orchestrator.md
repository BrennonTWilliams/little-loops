---
id: ENH-2325
title: "Remove residual string-replace branch-name derivation in orchestrator (BUG-823 residue)"
type: ENH
status: open
priority: P3
captured_at: "2026-06-26T22:26:49Z"
discovered_date: "2026-06-26"
discovered_by: audit
decision_needed: false
labels:
- worktree
- parallel
- tech-debt
relates_to:
- BUG-823
---

# ENH-2325: Remove residual string-replace branch-name derivation in orchestrator (BUG-823 residue)

## Summary

BUG-823 replaced fragile string-replacement branch-name derivation
(`name.replace("worker-", "parallel/")`) with `git rev-parse --abbrev-ref HEAD` in the
orphan-cleanup path. One call site was missed:
`scripts/little_loops/parallel/orchestrator.py:391` still derives the branch by string
replacement. Under feature-branch mode the derived name is simply wrong.

## Motivation

This is the exact anti-pattern BUG-823 closed, left in a sibling code path. While the blast
radius is small today (inspection/reporting), it is a correctness landmine: in feature-branch
mode the real branch is `feature/<id>-<slug>` while the worktree directory is still
`worker-<id>-<ts>`, so the derived `parallel/<id>-<ts>` name does not exist. Any future use of
this value for a destructive op (branch delete) would act on a non-existent or wrong branch.
Closing it finishes BUG-823 and removes a divergent derivation from the codebase.

## Current Behavior

`scripts/little_loops/parallel/orchestrator.py:391`:
```python
branch_name = worktree_path.name.replace("worker-", "parallel/")
```
This assumes every `worker-*` worktree is on a `parallel/*` branch, which is false whenever
`use_feature_branches=True` (`worker_pool.py:319` names the branch `feature/<id>-<slug>`).

## Expected Behavior

The branch name is read from the worktree's actual HEAD, matching the BUG-823 remediation
already applied in `_cleanup_orphaned_worktrees`.

## Root Cause

BUG-823's fix updated `_cleanup_orphaned_worktrees` but not this adjacent derivation (in the
worktree-inspection path). The two branch-name lookups were never unified.

## Proposed Solution

Replace the string-replace with an actual-branch lookup, mirroring the BUG-823 path:
```python
result = subprocess.run(
    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
    cwd=worktree_path, capture_output=True, text=True,
)
branch_name = result.stdout.strip() if result.returncode == 0 else None
```
Better: factor a tiny shared helper `worktree_branch_name(worktree_path) -> str | None` used
by both this site and `_cleanup_orphaned_worktrees` so there is one implementation. Preserve
the existing `parallel/`-prefix guard before any branch **deletion** (do not delete
`feature/*` branches here).

## Implementation Steps

1. In `orchestrator.py:_inspect_worktree()`, find the `else` fallback at line 391:
   ```python
   branch_name = worktree_path.name.replace("worker-", "parallel/")
   ```
   Replace with `branch_name = None` — a `None` branch is handled downstream; a fabricated wrong name is worse
2. (Optional but preferred) Extract `worktree_branch_name(worktree_path: Path) -> str | None` helper using bare `subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree_path, ...)` (not `_git_lock.run`); update both `_inspect_worktree` and `_cleanup_orphaned_worktrees` (~line 237) to call it — eliminates the two inlined copies
3. Preserve the `parallel/`-prefix guard in `_cleanup_orphaned_worktrees` at line 301 — only the derivation changes, not the deletion guard
3a. Update `PendingWorktreeInfo.branch_name` in `types.py` from `str` → `str | None`; update its docstring. Update `docs/reference/API.md` to match. The `_merge_pending_worktrees` `None` guard is already implicit: `git merge --no-ff None` returns non-zero → `branch -D` block is skipped by the `returncode == 0` check. No explicit `None` check is required but the implementer should be aware of this mechanism.
4. In `test_orchestrator.py:TestInspectWorktree` (~line 839):
   - Add a `patch("subprocess.run", ...)` alongside the existing `_git_lock.run` mock (the existing tests only patch `_git_lock.run`)
   - **Correct line 863**: the assertion currently expects the buggy derived value `"parallel/enh-042-20260117-150000"` — change to expect `"feature/<id>-<slug>"` (when rev-parse succeeds) or `None` (when it fails)
   - Follow the dual-patch pattern in `TestCleanupOrphanedWorktrees` (lines 500–597) and `test_worker_pool.py` (lines 751–779)
5. Run `python -m pytest scripts/tests/test_orchestrator.py -v` to verify

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — `_inspect_worktree` (else-fallback on rev-parse failure); optionally `_cleanup_orphaned_worktrees` (to share a helper)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/types.py` — **required**: `PendingWorktreeInfo.branch_name` is currently annotated `str` (not `str | None` as the issue text implies); after the fix `_inspect_worktree` assigns `None` on rev-parse failure → mypy will flag the type mismatch. Must change to `branch_name: str | None` and update the docstring (currently says `"Git branch name (parallel/<issue-id>-<timestamp>)"` — drop the `parallel/` convention claim)
- `scripts/little_loops/worktree_utils.py` — conditional: only if `worktree_branch_name(worktree_path: Path) -> str | None` is extracted here; no change needed if helper stays private to orchestrator.py

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/orchestrator.py` — `_check_pending_worktrees` calls `_inspect_worktree`; `_merge_pending_worktrees` and the commit-ahead check at `_inspect_worktree` consume the returned `branch_name`

### Similar Patterns
- `_cleanup_orphaned_worktrees` (same file, ~line 293) — already uses `git rev-parse --abbrev-ref HEAD`; source pattern to replicate or extract into a shared helper

### Tests
- `scripts/tests/test_orchestrator.py` — extend worktree-inspection tests: assert a `worker-*` dir on a `feature/*` branch yields the actual `feature/*` name (or `None`), not a derived `parallel/*` string; assert the `parallel/`-prefix guard still prevents deleting it

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_orchestrator.py:TestInspectWorktree.test_extracts_issue_id` (line 863) — **will break**: calls `_inspect_worktree` without mocking `subprocess.run`; the temp dir is not a real git repo, so rev-parse fails after the fix and the function returns `None`. Fix: add `patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="parallel/enh-042-20260117-150000\n"))` wrapping the call. The assertion value on line 863 (`"parallel/enh-042-20260117-150000"`) stays the same — the test verifies the `parallel/` happy path still works when rev-parse returns that name; only the derivation method changes. Follow dual-patch pattern in `TestCleanupOrphanedWorktrees.test_deletes_branch_via_rev_parse` (lines 500–531).
- `scripts/tests/test_orchestrator.py:TestInspectWorktree.test_detects_uncommitted_changes` (~line 865) — **will NOT break**: does not assert `branch_name`; the `_git_lock.run` mock returns `stdout="1\n"` for rev-list regardless of what `branch_name` is (the f-string `"main..None"` is rejected by git → rc != 0 → `commits_ahead=0`, but `has_uncommitted_changes=True` still drives `has_pending_work=True`). No mock addition required, but adding `subprocess.run` mock is good hygiene for test isolation.
- **New test**: `TestInspectWorktree.test_returns_actual_branch_for_feature_branch_mode` — when `subprocess.run` returns `"feature/enh-042-my-issue"`, verify `result.branch_name == "feature/enh-042-my-issue"` (not a fabricated `"parallel/..."`)
- **New test**: `TestInspectWorktree.test_returns_none_when_rev_parse_fails` — when `subprocess.run` returns `returncode=128`, verify `result.branch_name is None`
- **New test (BUG-823 regression)**: `TestInspectWorktree.test_inspect_worktree_uses_rev_parse_not_string_replace` — explicit regression: with a worktree dir named `worker-enh-042-ts` but rev-parse returning `"feature/enh-042-slug"`, verify `branch_name` is the rev-parse output, not `"parallel/enh-042-ts"` (mirrors `TestCleanupOrphanedWorktrees.test_deletes_branch_via_rev_parse`)
- `scripts/tests/test_cli_loop_worktree.py` — informational only; tests `worktree_utils.cleanup_worktree()` and `WorkerPool._cleanup_worktree()`, both already use dual-patch and already correct; only needs updating if `worktree_branch_name()` helper is extracted to `worktree_utils.py`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — **required**: `PendingWorktreeInfo` class block documents `branch_name: str  # Git branch (parallel/<issue-id>-<timestamp>)`. Must change to `str | None` and drop the `parallel/` convention comment now that the value comes from rev-parse and may be any branch prefix or None

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Additional files affected by `branch_name` downstream:**
- `scripts/little_loops/parallel/types.py` — `PendingWorktreeInfo` dataclass holds the `branch_name: str | None` field returned by `_inspect_worktree`
- `scripts/little_loops/parallel/merge_coordinator.py` — downstream consumer: `_cleanup_worktree()` at ~line 1166 uses `branch_name`; `parallel/` prefix guard at ~line 1188
- `scripts/little_loops/parallel/worker_pool.py` — `_cleanup_worktree()` at ~line 718 has a third `rev-parse` → `parallel/` guard pattern (passes `delete_branch` bool into shared utility)

**Existing shared utility — potential extraction target:**
- `scripts/little_loops/worktree_utils.py:cleanup_worktree()` (line 120) already encapsulates the `rev-parse → None` pattern and does the actual worktree removal; the `worktree_branch_name()` helper could live alongside this or delegate to it

**subprocess.run vs _git_lock.run — critical implementation detail:**
The BUG-823 fix in `_cleanup_orphaned_worktrees` uses bare `subprocess.run(cwd=worktree_path)` (not `self._git_lock.run`) to read the branch name. This is intentional: the worktree may be partially torn down and the lock machinery must not block on a dead worktree. Any shared helper must follow the same pattern (bare `subprocess.run`, `cwd=worktree_path`).

**Test patterns — two separate patches required:**
Tests for this path must patch BOTH `self._git_lock.run` AND bare `subprocess.run` separately. The existing `TestCleanupOrphanedWorktrees` class (lines 500–597) demonstrates this dual-patch pattern. The existing `TestInspectWorktree` class at ~line 839 currently patches only `_git_lock.run` and at line 863 **asserts the buggy derived value** `"parallel/enh-042-20260117-150000"` — this assertion must be corrected, not merely extended.

**Reference test in `test_worker_pool.py` (lines 751–779):**
`patch.object(worker_pool._git_lock, "run", side_effect=mock_git_run)` + `patch("subprocess.run")` — the canonical dual-patch shape to replicate for `TestInspectWorktree` updates.

**`_detect_current_branch()` in `cli/sprint/run.py` (line 90):**
A named helper for repo-level branch detection (no `cwd`, fallback `"main"`) — same shell call but different purpose; do not merge the worktree helper with this one.

**`_merge_pending_worktrees` has NO `parallel/` deletion guard (lines 536–540):**
Unlike `_cleanup_orphaned_worktrees` (which gates `branch -D` on `startswith("parallel/")`), `_merge_pending_worktrees` passes `info.branch_name` directly to `git branch -D` with no guard. A fabricated wrong name from the string-replace fallback would attempt deletion of a non-existent branch — or of the wrong branch if it accidentally matched. This amplifies the blast-radius analysis from "inspection error" to "potential wrong-branch deletion on `--merge-pending` runs".

**`has_pending_work` corruption (types.py:300):**
`_inspect_worktree` uses `branch_name` in `git rev-list --count {base}..{branch_name}` to compute `commits_ahead`. A fabricated name that doesn't exist produces a non-zero returncode → `commits_ahead = 0`. The `PendingWorktreeInfo.has_pending_work` property (`types.py:300`) returns `commits_ahead > 0 or has_uncommitted_changes`. If the fabricated branch name causes `commits_ahead` to be under-counted, a worktree with real commits may be skipped by `_merge_pending_worktrees` on `--merge-pending` runs.

**Scope clarification — bug only affects the `--merge-pending` / "resume from crash" path:**
The feature-branch path through `_handle_worker_result` uses `WorkerResult.branch_name` directly from `worker_pool._process_issue` — not from `_inspect_worktree`. The string-replace site is only reachable when processing leftover worktrees from a previous interrupted run with `--merge-pending`.

## Impact

- **Priority**: P3 — tech-debt / latent correctness; finishes BUG-823.
- **Effort**: XS — one call site + optional shared helper.
- **Risk**: Low.
- **Breaking Change**: No.

## Scope Boundaries

- **In scope**: Remove/replace the string-replace fallback in `_inspect_worktree`; optionally extract a shared `worktree_branch_name()` helper reused by `_cleanup_orphaned_worktrees`
- **Out of scope**: Changing the `parallel/`-prefix guard logic for branch deletion; modifying worktree naming conventions (`worker-*`); refactoring `_inspect_worktree` beyond the branch-name derivation; addressing other branch-name derivation patterns outside `orchestrator.py`

## Labels

`worktree`, `parallel`, `tech-debt`

## Verification Notes

_Added by `/ll:verify-issues` (2026-06-27):_ Line numbers in Implementation Step 4 and the wiring note are stale. Current values in `test_orchestrator.py`: `TestOrphanedWorktreeCleanup` starts at line 334 (not 500–597); `TestInspectWorktree` starts at line 926 (not ~839); the assertion `result.branch_name == "parallel/enh-042-20260117-150000"` is at line 951 (not 863). Verify line numbers before implementation.

## Session Log
- `/ll:verify-issues` - 2026-06-27T19:13:21 - `35d33eaf-2aad-4754-8c3e-650bb7940593.jsonl`
- `/ll:wire-issue` - 2026-06-26T22:55:10 - `613d5df7-a8ed-405a-928c-ec037815b530.jsonl`
- `/ll:refine-issue` - 2026-06-26T22:47:54 - `72d2e412-ebe3-4dd9-98d5-4e6aebd0e9c8.jsonl`
- `/ll:format-issue` - 2026-06-26T22:42:32 - `e76e1a58-1ba1-4ea1-8434-33e83d6f08d4.jsonl`
- audit (branch & worktree management) - 2026-06-26 - `thoughts/audits/2026-06-26-branch-worktree-management-audit.md`

---

## Status

- **Status**: open
- **Priority**: P3
