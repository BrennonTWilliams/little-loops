---
id: ENH-1255
priority: P3

depends_on:
- ENH-1254
discovered_date: '2026-04-22'
completed_at: '2026-05-02T20:01:24Z'
discovered_by: issue-size-review
decision_needed: false
decision_question: 'Should ll-loop --worktree worktrees (naming: <timestamp>-<safe-name>)
  be added to the orchestrator''s orphan scan, or should loop cleanup remain atexit-only?
  Choosing ''yes'' requires extracting _is_ll_worktree() predicate and extending three
  startswith(''worker-'') guards plus fixing two _inspect_worktree fallbacks in orchestrator.py.'
size: Medium
confidence_score: 100
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
parent: ENH-1248
status: done
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

> **Selected:** Extend orphan scan — SIGKILL leak is identical to the parallel-worker gap; `_is_ll_worktree()` fits `worktree_utils.py`'s shared-utility pattern and the implementation scope is fully bounded.

### Extract `_is_ll_worktree()` predicate

Place in `scripts/little_loops/worktree_utils.py` (already a shared module); add `import re` at the top:

```python
def _is_ll_worktree(name: str) -> bool:
    return name.startswith("worker-") or re.match(r"^\d{8}-\d{6}-", name) is not None
```

Replace all 5 inline `startswith("worker-")` guards with `_is_ll_worktree(name)` — see Files to Modify for full list.

### `_inspect_worktree` fallbacks — no change required

> **Resolved 2026-05-02** — original draft said these needed conditionals; codebase research shows the existing fallbacks already produce correct behavior for loop worktrees:
>
> - `orchestrator.py:388` — `worktree_path.name.replace("worker-", "parallel/")` is a pure no-op when the name has no `"worker-"` substring, returning `worktree_path.name`. Since `cli/loop/run.py:291-292` defines `_branch_name = f"{_timestamp}-{_safe_name}"; _worktree_path = _worktree_base / _branch_name`, dir name **is** the branch name for loop worktrees — the no-op result is correct.
> - `orchestrator.py:392` — issue-ID regex `r"worker-([a-z]+-\d+)-\d{8}-\d{6}"` won't match loop names; the existing fallthrough sets `issue_id = worktree_path.name`, which is acceptable since loop worktrees have no issue-ID concept (they aren't tied to issues).
>
> **Action: leave both lines unchanged.** The implementation is now strictly guard replacement + predicate extraction.

### Update `commands/cleanup-worktrees.md`

- `cleanup-worktrees.md:56,177` — `find … -name "worker-*"` must also match `<timestamp>-<safe-name>` dirs.
- `cleanup-worktrees.md:90` — dry-run `sed 's/^worker-//'` branch derivation needs a conditional for loop worktree names.
- `cleanup-worktrees.md:122` — live-run `sed 's/^worker-//'` branch derivation (same fix as line 90, separate code path).

**Exact replacements (verified against current file):**

- **Lines 56 and 177** — replace `-name "worker-*"` with `\( -name "worker-*" -o -name "[0-9]*" \)`:
  ```bash
  # Line 56 (discovery)
  WORKTREES=$(find "$WORKTREE_BASE" -maxdepth 1 -type d \( -name "worker-*" -o -name "[0-9]*" \) 2>/dev/null || true)
  # Line 177 (summary REMAINING count)
  REMAINING=$(find "$WORKTREE_BASE" -maxdepth 1 -type d \( -name "worker-*" -o -name "[0-9]*" \) 2>/dev/null | wc -l | tr -d ' ')
  ```
  `[0-9]*` safely selects timestamp-prefixed dirs (`YYYYMMDD-HHMMSS-*`) since no other ll-managed directory names begin with a digit.

- **Lines 90 and 122** — replace inline `sed` with a conditional (both dry-run and live-run paths):
  ```bash
  if echo "$WORKTREE_NAME" | grep -q "^worker-"; then
      BRANCH_NAME="parallel/$(echo "$WORKTREE_NAME" | sed 's/^worker-//')"
  else
      BRANCH_NAME="$WORKTREE_NAME"
  fi
  ```
  Loop worktrees have dir-name == branch-name (`cli/loop/run.py:289-292`), so no prefix stripping is needed.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-04-26.

**Selected**: Extend orphan scan

**Reasoning**: The SIGKILL leak gap for loop worktrees is the same failure mode as the parallel-worker gap, which already has orphan-scan coverage. Choosing to leave loop worktrees uncovered creates an inconsistency between two worktree types that share the same `.ll-session-<pid>` marker and the same liveness-check recovery mechanism — the marker is written unconditionally in `setup_worktree()` (worktree_utils.py:97-99), so the PID check already works correctly for loop worktrees once the naming guard is fixed. The `_is_ll_worktree()` predicate fits directly into `worktree_utils.py` alongside `setup_worktree`/`cleanup_worktree`, and all four guard replacements plus two `_inspect_worktree` conditionals are fully bounded and documented in this issue.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Extend orphan scan | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |
| Atexit-only (won't implement) | 1/3 | 3/3 | 3/3 | 3/3 | 10/12 |

**Key evidence**:
- Extend orphan scan: `worktree_utils.py` has `setup_worktree`/`cleanup_worktree` as the direct pattern model; `.ll-session-<pid>` marker confirmed written unconditionally (worktree_utils.py:97-99); `orchestrator.py` already imports `re` (line 11); `TestBranchNameGeneration` (test_cli_loop_worktree.py:516-537) is the exact structural model for `TestIsLLWorktree`. Note: there are four `startswith("worker-")` guards across two files (not three), and the `_inspect_worktree` fallbacks are at lines 388 and 392-393 (not 332/336 as cited in the issue).
- Atexit-only: `register_loop_signal_handlers` covers SIGTERM, but SIGKILL bypasses all handlers — the leak is real. Closing without implementing leaves `cleanup-worktrees.md` and `worktree-health.yaml` incomplete for loop worktrees, creating inconsistent tool coverage between the two worktree types.

## Implementation Steps (if decision = yes)

_See "Proposed Solution" below for detailed steps. Wiring phase at the end of this section._

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Verify `scripts/tests/test_orchestrator.py:768` (`test_extracts_issue_id`) still passes — exercises `_inspect_worktree` fallback at `orchestrator.py:388`; no code change needed here since `_inspect_worktree` is not modified by this issue (see Refinement Pass 2026-05-02)
2. Update `scripts/little_loops/loops/worktree-health.yaml:29` — change action prompt from "ll-parallel runs" to "ll-parallel and ll-loop --worktree runs"
3. Optionally update `docs/ARCHITECTURE.md:820-826` — add `<timestamp>-<safe-name>/` to the `.worktrees/` layout diagram
4. Optionally update `docs/guides/LOOPS_GUIDE.md:538` — expand orphaned-worktrees description to mention loop worktrees
5. Update `scripts/tests/test_orchestrator.py:595` (`test_prunes_ghost_worktree_refs`) — add timestamp-prefixed worktree dir case alongside existing `worker-bug-001-20260101-120000`; covers guard replacements at `orchestrator.py:340,349` inside `_prune_ghost_worktree_refs()`
6. Fix implementation reference: `test_ignores_non_worker_directories` (pending check, `_check_pending_worktrees`) is at line 748, not 595 as listed in Files to Modify; line 595 is `test_prunes_ghost_worktree_refs` — update the `test_orchestrator.py:375,595` reference to `test_orchestrator.py:375,595,748`

## Files to Modify (if decision = yes)

> **Updated 2026-05-02** — line numbers re-verified; ghost-ref guards added; `_inspect_worktree` changes removed (no-op for loop worktrees).

- `scripts/little_loops/worktree_utils.py` — add `import re` and `_is_ll_worktree()` predicate
- `scripts/little_loops/parallel/orchestrator.py:248,340,349,441` — replace 4 `startswith("worker-")` guards (`_cleanup_orphaned_worktrees`, two in `_prune_ghost_worktree_refs`, `_check_pending_worktrees`)
- `scripts/little_loops/parallel/worker_pool.py:1316` — replace `startswith("worker-")` guard in `cleanup_all_worktrees()`
- `commands/cleanup-worktrees.md:56,90,122,177` — update `find` and `sed` patterns (line 122 is live-run branch derivation, separate from dry-run at line 90)
- `scripts/tests/test_cli_loop_worktree.py` — add `TestIsLLWorktree` class modelled after `TestBranchNameGeneration` (line 516): imports inside test bodies, no fixtures:
  ```python
  class TestIsLLWorktree:
      """Verify _is_ll_worktree() predicate matches both naming patterns."""

      def test_worker_prefix_matches(self) -> None:
          from little_loops.worktree_utils import _is_ll_worktree
          assert _is_ll_worktree("worker-bug-001") is True

      def test_timestamp_prefix_matches(self) -> None:
          from little_loops.worktree_utils import _is_ll_worktree
          assert _is_ll_worktree("20260101-000000-my-loop") is True

      def test_other_directory_does_not_match(self) -> None:
          from little_loops.worktree_utils import _is_ll_worktree
          assert _is_ll_worktree("other-directory") is False
  ```
- `scripts/tests/test_orchestrator.py:378,595,748` — add timestamp-prefixed dir case to the three `test_ignores_non_worker_directories` tests (378=orphan cleanup, 595=ghost-ref prune, 748=pending check)
- `scripts/tests/test_worker_pool.py:791` — add `20260101-000000-my-loop` dir to `test_cleanup_all_worktrees_removes_all` and assert count becomes 3
- _Not modified_: `orchestrator.py:388,392` (`_inspect_worktree` fallbacks) — existing string-replace and regex naturally fall through to correct behavior for loop worktrees because dir name == branch name (`cli/loop/run.py:289-292`)

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/parallel.py:163` — calls `pool.cleanup_all_worktrees()` directly; after the fix, loop worktrees are cleaned through this call path with no code changes needed here
- `scripts/little_loops/cli/sprint/run.py:18` — uses `ParallelOrchestrator`, which calls `_cleanup_orphaned_worktrees()` and `_check_pending_worktrees()` during startup; no code changes needed, but loop worktrees will now be scanned during sprint runs too
- `scripts/little_loops/cli/loop/run.py:204` — imports `setup_worktree`; the worktree it creates is exactly what ENH-1255 extends the scan to cover; no code changes needed here

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_orchestrator.py:768` (`test_extracts_issue_id`) — **should pass unchanged**: exercises `_inspect_worktree` fallback at `orchestrator.py:388`; since `_inspect_worktree` is NOT modified by this issue (Refinement Pass 2026-05-02), this test needs no update — just run as regression check
- `scripts/tests/test_orchestrator.py:595` (`test_prunes_ghost_worktree_refs`) — **must update**: covers `_prune_ghost_worktree_refs()` (defined at `orchestrator.py:316`); both guards at lines 340 and 349 inside that function are being replaced by `_is_ll_worktree()`; add a timestamp-prefixed dir case to verify ghost refs for loop worktrees are pruned [Wire pass 2]
- `scripts/tests/test_orchestrator.py:748` (`test_ignores_non_worker_directories` in `TestCheckPendingWorktrees`) — **line-number correction**: "Files to Modify" lists this test at line 595, but line 595 is `test_prunes_ghost_worktree_refs` (entry above); the `_check_pending_worktrees` ignore test is at line 748; update implementation reference from `375,595` to `375,595,748` [Wire pass 2]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md:820-826` — directory layout diagram shows only `worker-N/` naming under `.worktrees/`; loop worktree directories (`<timestamp>-<safe-name>/`) are absent; low-priority doc update
- `docs/guides/LOOPS_GUIDE.md:538` — `worktree-health` loop description says it monitors orphaned worktrees left by `ll-parallel` runs only; after ENH-1255, loop worktrees appear too
- `docs/ARCHITECTURE.md:381-384` — mermaid `subgraph Worktrees` diagram hardcodes `".worktrees/worker-1/"`, `".worktrees/worker-2/"`, `".worktrees/worker-N/"` node labels; second location in the same file beyond the already-noted 820-826 layout section; optional [Wire pass 2]
- `docs/development/TROUBLESHOOTING.md:117` — "Worktree cleanup fails on locked worktree" manual-fix block uses `git worktree unlock .worktrees/worker-<name>` / `git worktree remove .worktrees/worker-<name>`; same steps apply to loop worktrees with `.worktrees/<timestamp>-<safe-name>` path; optional [Wire pass 2]

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

- `cleanup-worktrees.md:122` — `BRANCH_NAME="parallel/$(echo "$WORKTREE_NAME" | sed 's/^worker-//')"` (live-run path; same fix as dry-run line 90, separate code branch)
- `orchestrator.py:247-248` — `for item in worktree_base.iterdir(): if item.is_dir() and item.name.startswith("worker-"):`
- `orchestrator.py:382-385` — list comprehension: `[item for item in worktree_base.iterdir() if item.is_dir() and item.name.startswith("worker-")]`
- `worker_pool.py:1315-1316` — `for worktree_dir in worktree_base.iterdir(): if worktree_dir.is_dir() and worktree_dir.name.startswith("worker-"):`
- `test_orchestrator.py:375-387` — `test_ignores_non_worker_directories` (orphan cleanup): creates `"other-directory"`, asserts it still exists after `_cleanup_orphaned_worktrees()` — add timestamp-dir case here with opposite assertion (removed)
- `test_orchestrator.py:595-608` — `test_ignores_non_worker_directories` (pending): same pattern for `_check_pending_worktrees()`, asserts `result == []`
- `test_worker_pool.py:791-816` — `test_cleanup_all_worktrees_removes_all`: uses `patch.object(worker_pool, "_cleanup_worktree", side_effect=mock_cleanup)` + `cleanup_calls: list[Path]`, asserts `len == 2`; add timestamp dir and change assertion to `== 3`
- `test_cli_loop_worktree.py:458-479` — `TestBranchNameGeneration` (closest analog): pure-logic class, no fixtures, imports inside test bodies — model `TestIsLLWorktree` after this style

### Refinement Pass 2026-05-02 (resolves Confidence Check open items)

_Added by `/ll:refine-issue` — addresses risks flagged in Confidence Check Notes:_

- **Ghost-ref-scan guards confirmed at `orchestrator.py:340` and `:349`** (inside `_prune_ghost_worktree_refs()`, defined at line 316). Both guards filter `git worktree list --porcelain` output to find dangling `.git/worktrees/<name>` refs whose backing directory is gone. Same SIGKILL-leak logic that motivates `_cleanup_orphaned_worktrees()` applies here — a SIGKILLed loop worktree leaves both an orphan dir AND a ghost ref. **Decision: extend `_is_ll_worktree()` to both ghost-ref guards too.** This brings the guard total to 5 (not 3-4): `orchestrator.py:248,340,349,441` + `worker_pool.py:1316`.
- **Branch-name derivation for loop worktrees in `_inspect_worktree` is a no-op fix.** `cli/loop/run.py:289-292` sets `_branch_name = f"{_timestamp}-{_safe_name}"` and `_worktree_path = _worktree_base / _branch_name` — i.e., **for loop worktrees, dir name == branch name**. The existing fallback at `orchestrator.py:388` (`worktree_path.name.replace("worker-", "parallel/")`) is a string-replace that becomes a pure no-op when the name has no `"worker-"` substring, returning `worktree_path.name` unchanged — which is the correct branch name for loop worktrees. **No conditional needed at line 388.** Similarly at line 392, the issue-id regex won't match loop names and the fallback `issue_id = worktree_path.name` is acceptable since loop worktrees have no issue ID concept. **Recommendation: leave both `_inspect_worktree` fallbacks alone.** This removes one risk vector and simplifies the change to a pure guard-replacement plus predicate extraction.
- **Current authoritative line numbers** (verified 2026-05-02):
  - `orchestrator.py:248` — `_cleanup_orphaned_worktrees()` guard
  - `orchestrator.py:340,349` — `_prune_ghost_worktree_refs()` guards (was unscoped in original Files to Modify)
  - `orchestrator.py:388,392` — `_inspect_worktree` fallbacks (leave unchanged)
  - `orchestrator.py:441` — `_check_pending_worktrees()` guard (was 385 in earlier draft)
  - `worker_pool.py:1316` — `cleanup_all_worktrees()` guard
- **Updated guard-replacement count: 5** (`orchestrator.py:248,340,349,441` + `worker_pool.py:1316`); **`_inspect_worktree` changes: 0** (down from 2 in original Proposed Solution).

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

## Impact

- **Priority**: P3 - Low-priority reliability improvement; atexit handles most cases, but SIGKILL leaves a real leak gap
- **Effort**: Medium - 7+ file changes (worktree_utils, orchestrator, worker_pool, cleanup-worktrees.md, 3 test files, worktree-health.yaml)
- **Risk**: Low - pure guard replacements with a simple predicate; no behavior change for existing `worker-*` worktrees
- **Breaking Change**: No

## Scope Boundaries

- `_inspect_worktree` fallbacks at `orchestrator.py:388,392` — **not modified** (loop dir name == branch name, existing behavior is correct)
- Signal handler registration (`register_loop_signal_handlers`) — not in scope
- `worktree-health.yaml` structural fix — covered by ENH-1254 (already completed); this issue only updates the action prompt text
- Loop worker session lifecycle — no changes to how loop worktrees are created; only the startup orphan scan is extended

## Labels

`parallel`, `worktree`, `loop`, `reliability`, `cleanup`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-26_

**Readiness Score**: 96/100 → PROCEED
**Outcome Confidence**: 64/100 → MODERATE

### Outcome Risk Factors
- **Complexity is the primary risk driver (10/25)**: 7+ files span worktree_utils, orchestrator, worker_pool, cleanup-worktrees.md, and three test files — expect meaningful integration work even though each individual change is simple
- ~~**Ghost-ref-scan guards at `orchestrator.py:340,349` are unaccounted for**~~: **RESOLVED 2026-05-02** — confirmed both sites belong to `_prune_ghost_worktree_refs()` and the same SIGKILL-leak logic applies; `_is_ll_worktree()` will replace these guards too (now in Files to Modify)
- ~~**Branch-name derivation for loop worktrees in `_inspect_worktree` is unspecified**~~: **RESOLVED 2026-05-02** — for loop worktrees, dir name == branch name (`cli/loop/run.py:289-292`), so the existing `replace("worker-", "parallel/")` no-op already produces the correct result; no code change needed at lines 388 or 392

## Session Log
- `/ll:ready-issue` - 2026-05-02T19:55:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f796fee3-8b88-4699-bb0b-8ba376b85aea.jsonl`
- `/ll:confidence-check` - 2026-05-02T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3dc73644-56ce-485c-9743-074873fcaa8f.jsonl`
- `/ll:wire-issue` - 2026-05-02T19:50:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9b1fee64-5798-4b35-82d5-d17a1e52d8d4.jsonl`
- `/ll:refine-issue` - 2026-05-02T19:44:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/22b8f0dd-e355-4cc0-93b5-3fa545866dec.jsonl`
- `/ll:confidence-check` - 2026-05-02T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00db13ea-6bab-4b46-be19-afae31f720a7.jsonl`
- `/ll:refine-issue` - 2026-05-02T18:52:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ab38a044-b629-4607-845e-54c5a6ef505d.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:confidence-check` - 2026-04-26T19:35:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cf03929d-b936-46f6-9fc6-0edf5cab2290.jsonl`
- `/ll:decide-issue` - 2026-04-26T19:26:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ae825d2a-b598-42e3-8f2e-583ed68c3209.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
- `/ll:wire-issue` - 2026-04-22T17:09:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/509cc566-db9f-4e7a-a3c5-21f738bb3a0b.jsonl`
- `/ll:refine-issue` - 2026-04-22T17:04:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8c3dd3b0-98a8-494a-8720-4fa7296292d6.jsonl`

- `/ll:issue-size-review` - 2026-04-22T17:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/79aadd9e-32c2-44ea-be52-e9ec9bcff212.jsonl`

---

## Verification Notes

**Verdict**: VALID — Verified 2026-04-26

- `orchestrator.py:248` — `startswith("worker-")` guard confirmed ✓
- `orchestrator.py:441` — `_check_pending_worktrees` guard confirmed (was 385 in issue; line numbers shifted) ✓
- `worker_pool.py:1316` — `startswith("worker-")` guard confirmed ✓
- `worktree_utils.py` has no `_is_ll_worktree()` predicate ✓
- Loop worktrees (timestamp-named) would not be scanned ✓
- Feature not yet implemented ✓

**Completed** | Created: 2026-04-22 | Completed: 2026-05-02 | Priority: P3

## Resolution

Implemented 2026-05-02. Extended orphan scan to cover `ll-loop --worktree` worktrees via a shared `_is_ll_worktree()` predicate in `worktree_utils.py`. Replaced all 5 inline `startswith("worker-")` guards across `orchestrator.py` (4 sites) and `worker_pool.py` (1 site). Updated `cleanup-worktrees.md` shell patterns and `worktree-health.yaml` action prompt. Added `TestIsLLWorktree` and extended tests in all 3 affected test files. All 234 tests pass.
