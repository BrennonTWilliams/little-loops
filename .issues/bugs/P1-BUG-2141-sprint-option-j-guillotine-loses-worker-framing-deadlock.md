---
id: BUG-2141
type: BUG
priority: P1
captured_at: '2026-06-14T03:50:03Z'
completed_at: '2026-06-14T15:39:08Z'
discovered_date: '2026-06-14'
discovered_by: capture-issue
status: done
relates_to:
- BUG-1386
- ENH-1996
confidence_score: 98
outcome_confidence: 72
score_complexity: 18
score_test_coverage: 15
score_ambiguity: 20
score_change_surface: 19
implementation_order_risk: true
decision_needed: false
---

# BUG-2141: Sprint Option J guillotine loses worker framing → fresh session deadlock

## Summary

When a sprint worker running in sequential mode hits the context limit and Option J fires,
the guillotine resume file (`guillotine-prompt.md`) contains only generic continuation
instructions — no sprint worker framing. The fresh session spawned via `/ll:resume` does
not know it is a sprint worker, does not know to stop after ONE issue, and does not know
to exit when done. It implements whichever issues look interesting, then blocks asking
"What next?" — deadlocking the sprint orchestrator indefinitely.

## Steps to Reproduce

1. Run a sprint with sequential workers: `ll-sprint run <sprint-file.yaml>` (any mode using `process_issue_inplace()`)
2. Allow a worker session to reach the context limit (≥4095%)
3. Option J fires automatically, calling `run_with_continuation()` which invokes `assemble_guillotine_prompt()` in `subprocess_utils.py`
4. Observe: the prompt blob contains only generic continuation instructions — no sprint worker framing
5. A fresh session is started using the guillotine prompt string as its command
6. Observe: fresh session processes multiple visible issues (not just the assigned one), then blocks with "What next?"
7. Sprint orchestrator waits indefinitely for `process_issue_inplace()` to return → deadlock requiring manual kill

## Current Behavior

`subprocess_utils.assemble_guillotine_prompt()` (line 153) assembles a continuation prompt with:
```
## Original Task
{original_command}
...
## Instructions for This Session
1. Check git log ...
2. Check the issue file status — if already done/cancelled, stop
3. Review .loops/tmp/scratch/ for partial progress notes
4. Continue the original task from where it left off, skipping already-completed work
```

The fresh session started from this prompt has no knowledge of:
- Being a sprint worker (vs. a general automation session)
- Which single issue ID it is responsible for
- That it must stop after completing exactly one issue
- That it must exit cleanly without waiting for further user input

**Observed in the field (2026-06-13, `cards` project):**
- FEAT-025 processing hit 4095% context → Option J fired
- Fresh session read the summary, implemented FEAT-025, FEAT-027, FEAT-030, FEAT-037 (all
  issues visible in the context summary), committed them all to branch `feat-037-...`
- Fresh session then asked "What would you like me to do next?" → blocked forever
- Sprint orchestrator waited indefinitely for `process_issue_inplace()` to return → manual kill required

**Two separate code paths share this bug:**

1. **Sprint sequential path** (`sprint/run.py` → `process_issue_inplace()` → `run_with_continuation()`): never
   passes `run_dir`, so the `guillotine-prompt.md` file-write branch in `run_with_continuation()` (gated on
   `run_dir is not None` at line 329) is never activated. Option J always falls through to
   `assemble_guillotine_prompt()` at line 359 in `issue_manager.py`, producing a prompt string passed directly as the next command.

2. **Parallel worktree path** (`worker_pool._run_with_continuation()` line 729): when `run_dir is not None` (line 823),
   it writes `guillotine-prompt.md` at lines 836–854 and uses `/ll:resume <path>` as the next command. This file also
   lacks sprint worker framing when called from parallel mode.

## Expected Behavior

When Option J fires inside a sprint worker, the continuation prompt must inject sprint
worker framing so the fresh session knows its constraints:
```
## Sprint Worker Context
You are processing exactly ONE sprint issue: FEAT-025
After completing this issue, exit immediately — do NOT process other issues.
Do NOT ask for further instructions. Exit with code 0.
Branch: main (or the worktree branch)
```

## Root Cause

**Sprint sequential path** (`issue_manager.py`):
- **File**: `scripts/little_loops/issue_manager.py`
- **Anchor**: module-level `run_with_continuation()` at line 194
- `process_issue_inplace()` (line 528) calls `run_with_continuation()` at lines 844–856 without passing `run_dir`,
  so Option J always invokes `assemble_guillotine_prompt()` (line 359 in `issue_manager.py`; implemented at
  `subprocess_utils.py:153`). No sprint context is threaded through this call chain.

**Parallel path** (`worker_pool.py`):
- **File**: `scripts/little_loops/parallel/worker_pool.py`
- **Anchor**: `WorkerPool._run_with_continuation()` at line 729
- Guillotine file write at lines 836–854; `assemble_guillotine_prompt()` call at line 865 (`else` branch when `run_dir is None`). Called from `_process_issue()` at line 396 without passing
  `run_dir`, so this path always falls through to `assemble_guillotine_prompt()` in normal parallel execution.

**Root miss**: neither `process_issue_inplace()` nor `_process_issue()` passes sprint-specific metadata
(`issue_id`, `branch`, stop-after-one constraint) into the continuation call chain.

**`SprintWorkerContext` does not exist anywhere in the codebase.** The closest model is `WorkerResult`
in `scripts/little_loops/parallel/types.py` (line 52), which carries `issue_id: str` and `branch_name: str`
and follows the `@dataclass` + `to_dict()` + `from_dict()` convention.

## Proposed Solution

**Minimal-surface approach** — inject through `assemble_guillotine_prompt()`:

1. Define `SprintWorkerContext` dataclass in `scripts/little_loops/parallel/types.py` (where `WorkerResult`
   and `QueuedIssue` live), following the `@dataclass` + `to_dict()` convention. Minimal fields:
   `issue_id: str`, `branch: str`.

2. Add an optional `sprint_context: SprintWorkerContext | None = None` parameter to
   `assemble_guillotine_prompt()` in `subprocess_utils.py` (line 153). When set, prepend a sprint framing
   block to the returned prompt string:
   ```python
   if sprint_context is not None:
       framing = (
           f"## Sprint Worker Context\n"
           f"You are a sprint worker. Process exactly ONE issue: {sprint_context.issue_id}\n"
           f"After completing this issue, exit immediately — do NOT process other issues.\n"
           f"Do NOT ask for further instructions. Exit with code 0.\n"
           f"Branch: {sprint_context.branch}\n\n"
       )
       return framing + body
   ```
   This avoids changing `run_dir` logic or the `process_issue_inplace()` return type.

3. Thread `sprint_context` through:
   - `issue_manager.run_with_continuation()` (line 194) → forward to `assemble_guillotine_prompt()` call at line 359
   - `issue_manager.process_issue_inplace()` (line 528) → forward to `run_with_continuation()` at lines 844–856
   - `worker_pool.WorkerPool._run_with_continuation()` (line 729) → forward to `assemble_guillotine_prompt()`
     and also inject into the guillotine file write at lines 836–854 for the parallel `run_dir` path

4. Pass sprint context from both call sites in `sprint/run.py`:
   - `_run_issue_with_wall_clock_timeout()` → `process_issue_inplace()` at line 63 (primary sequential wave path)
   - Sequential retry after parallel wave failure at line 541

## Implementation Steps

1. Define `SprintWorkerContext(issue_id: str, branch: str)` in `scripts/little_loops/parallel/types.py`,
   following the `@dataclass` + `to_dict()` pattern of `WorkerResult` (line 52) and `QueuedIssue` (line 20).
   Add `to_dict()` only (no `from_dict()` needed — not persisted to disk).

2. Add `sprint_context: SprintWorkerContext | None = None` to `assemble_guillotine_prompt()` in
   `subprocess_utils.py` (line 153). Prepend the framing block when set.

3. Add `sprint_context: SprintWorkerContext | None = None` to `issue_manager.run_with_continuation()` (line 194)
   and thread it into the `assemble_guillotine_prompt()` call at line 359.

4. Add `sprint_context: SprintWorkerContext | None = None` to `issue_manager.process_issue_inplace()` (line 528)
   and thread it into the `run_with_continuation()` call at lines 844–856.

5. Add `sprint_context: SprintWorkerContext | None = None` to `worker_pool.WorkerPool._run_with_continuation()`
   (line 729); inject into `assemble_guillotine_prompt()` at line 865 and into the guillotine file write at lines 836–854.

6. Pass `SprintWorkerContext(issue_id=issue.issue_id, branch=current_branch)` at **both** call sites in
   `scripts/little_loops/cli/sprint/run.py`:
   - Line 63 inside `_run_issue_with_wall_clock_timeout()` (primary sequential wave path)
   - Line 541: sequential retry after parallel wave failure

7. Write tests:
   - New test in `test_worker_pool.py` `TestRunWithContinuation` class (line 2260) mirroring
     `test_guillotine_with_run_dir_writes_resume_file` (line 2401) — assert sprint framing block present
     in guillotine file content when `sprint_context` is set
   - New test in `test_subprocess_utils.py` for `assemble_guillotine_prompt()` with `sprint_context` set —
     assert framing block is prepended and non-sprint calls are unaffected
   - New test in `test_cli_sprint.py` mirroring `_run_issue_with_wall_clock_timeout` pattern (lines 623–727) —
     assert `sprint_context` is forwarded to `process_issue_inplace()`
   - All 19 existing `process_issue_inplace` mocks in `test_sprint_integration.py` and all 10 in `test_sprint.py`
     use `**kwargs` — no mock cascade updates required

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Audit `scripts/tests/test_issue_manager.py` — `TestRunWithContinuation` (line 1131): add sprint-context guillotine variant (mirrors the new test in `test_worker_pool.py:TestRunWithContinuation`); confirm all 5 existing guillotine tests still pass with `sprint_context` defaulting to `None`
9. Audit `scripts/tests/test_issue_manager.py` — `TestProcessIssueInplace` direct call sites (lines 1676, 1702, 1734, 1762, 1804): verify each uses keyword args or `**kwargs` and absorbs `sprint_context=None` without breaking
10. Update `docs/reference/API.md` — add `SprintWorkerContext` dataclass entry in the parallel types section alongside `WorkerResult`
11. Add CHANGELOG entry for BUG-2141 fix under the next release section

## Files to Modify

- `scripts/little_loops/parallel/types.py` — add `SprintWorkerContext` dataclass
- `scripts/little_loops/subprocess_utils.py` — `assemble_guillotine_prompt()` (line 153): add `sprint_context` parameter
- `scripts/little_loops/issue_manager.py` — `run_with_continuation()` (line 194) and `process_issue_inplace()` (line 528)
- `scripts/little_loops/parallel/worker_pool.py` — `WorkerPool._run_with_continuation()` (line 729)
- `scripts/little_loops/cli/sprint/run.py` — both call sites (lines 63 and 541)

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/types.py` — add `SprintWorkerContext` dataclass (`issue_id: str`, `branch: str`); model after `WorkerResult` (line 52) and `QueuedIssue` (line 20)
- `scripts/little_loops/subprocess_utils.py` — `assemble_guillotine_prompt()` (line 153): add optional `sprint_context` parameter; prepend sprint framing block when set
- `scripts/little_loops/issue_manager.py` — module-level `run_with_continuation()` (line 194): add `sprint_context` parameter; thread into `assemble_guillotine_prompt()` call at line 357
- `scripts/little_loops/issue_manager.py` — `process_issue_inplace()` (line 528): add `sprint_context` parameter; thread into `run_with_continuation()` call at lines 844–856
- `scripts/little_loops/parallel/worker_pool.py` — `WorkerPool._run_with_continuation()` (line 729): add `sprint_context` parameter; inject framing into guillotine file write at lines 836–854 and into `assemble_guillotine_prompt()` call at line 865
- `scripts/little_loops/cli/sprint/run.py` — both call sites must pass `SprintWorkerContext(issue_id=info.issue_id, branch=current_branch)`
- `scripts/little_loops/parallel/__init__.py` — re-exports `WorkerPool`, `QueuedIssue`, `WorkerResult` via `__all__`; add `SprintWorkerContext` if public API exposure is desired (advisory; not required for core fix) [Wiring pass]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/sprint/run.py:63` — `_run_issue_with_wall_clock_timeout()` (lines 42–83) calls `process_issue_inplace()` without sprint context (primary sequential wave path)
- `scripts/little_loops/cli/sprint/run.py:541` — sequential retry after parallel wave failure; also calls `process_issue_inplace()` without sprint context

### Tests
- `scripts/tests/test_parallel_types.py` — existing tests for parallel types; add `SprintWorkerContext` dataclass tests here (model after `WorkerResult` assertions)
- `scripts/tests/test_worker_pool.py:2401` — `test_guillotine_with_run_dir_writes_resume_file` in `TestRunWithContinuation` (class at line 2260): model test to mirror for sprint-context variant
- `scripts/tests/test_worker_pool.py:2260` — `TestRunWithContinuation`: class for new `_run_with_continuation` sprint-context tests
- `scripts/tests/test_cli_sprint.py:623` — `_run_issue_with_wall_clock_timeout` tests (lines 623–727): pattern for new sprint-context forwarding tests
- `scripts/tests/test_subprocess_utils.py` — class `TestAssembleGuillatinePrompt` (line 1986, note: double-l typo in class name); 4 existing tests at lines 1989–2048 cover original_command, stdout tail, empty stdout, and token_stats; add sprint-context variant alongside
- `scripts/tests/test_sprint_integration.py` — 19 `process_issue_inplace` mock sites; all use `**kwargs` — no updates needed
- `scripts/tests/test_sprint.py` — 10 `process_issue_inplace` mock sites; all use `**kwargs` — no updates needed

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_manager.py` — `TestRunWithContinuation` (line 1131): directly tests `run_with_continuation` guillotine path (5 tests: `test_guillotine_path_on_context_overflow`, `test_guillotine_path_on_prompt_too_long`, `test_guillotine_with_run_dir_writes_resume_file`, `test_guillotine_without_run_dir_uses_summary_blob`, `test_option_j_fresh_session_skips_option_e`); add sprint-context variant alongside; assert non-sprint calls unaffected [Agent 1+2+3 finding]
- `scripts/tests/test_issue_manager.py` — `TestProcessIssueInplace` (direct call sites at lines 1676, 1702, 1734, 1762, 1804): audit each to confirm keyword args or `**kwargs` will absorb `sprint_context=None` without breaking [Agent 2+3 finding]

### J-Path Test Pattern (two-patch stack)

_Added by `/ll:refine-issue` — verified against `test_worker_pool.py:TestRunWithContinuation`:_

J-path tests in `TestRunWithContinuation` use a closure-based call counter (`call_count = [0]`, `commands_received: list[str] = []`) to track which invocation fires the usage callback. The standard two-patch stack:

```python
with patch.object(worker_pool, "_run_claude_command", side_effect=mock_run_claude):
    with patch("little_loops.parallel.worker_pool.detect_context_handoff", return_value=False):
        worker_pool._run_with_continuation("test", temp_repo_with_config, ...)
```

The `on_usage(185_000, 10_000)` call (195K > 90% of 200K = guillotine_threshold trigger) is injected inside `mock_run_claude` on the first invocation only. Assert `"Sprint Worker Context" in commands_received[1]` for the new sprint-context framing test.

`process_issue_inplace` is always mocked at module path `"little_loops.issue_manager.process_issue_inplace"`, never at the call site.

### Documentation
- `docs/guides/SPRINT_GUIDE.md` — may need note on Option J behavior in sprint context
- `hooks/prompts/continuation-prompt-template.md` — continuation prompt template used by guillotine

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `### WorkerPool` constructor signature and `### WorkerResult` fields documented; add `### SprintWorkerContext` dataclass entry alongside `WorkerResult` [Agent 2 finding]
- `CHANGELOG.md` — new entry for BUG-2141 fix; consistent with ENH-1996 and BUG-1386 entries that name `run_with_continuation` and `WorkerPool._run_with_continuation` [Agent 2 finding]

## Impact

- **Severity**: Critical — sprint deadlocks with no automatic recovery
- **Effort**: Medium — adding a parameter through 3 layers, writing framing block
- **Risk**: Low — additive change; non-sprint callers pass `None`, behavior unchanged
- **Breaking Change**: No

## Related Issues

- BUG-1386 (done): `run_with_continuation` false failure after Option J
- ENH-1996 (done): Option J should use `/ll:resume` instead of summary blob
- BUG-2144: Sprint orchestrator deadlock timeout gap (mitigation)
- ENH-2143: Sequential sprint worktree isolation (mitigation)

## Labels

`bug`, `sprint`, `option-j`, `worker-pool`, `deadlock`, `guillotine`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-14_

**Readiness Score**: 97/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors
- Test coverage gap (B: 15/25): the `sprint_context` parameter and sprint-framing code path in `_run_with_continuation()` have no test coverage until new tests are written — implement tests first so the fix is immediately verifiable (tests are co-deliverables of this issue per Implementation Steps item 7).
- Test mock cascade (D: 19/25): `process_issue_inplace()` is mocked in 19 tests in `test_sprint_integration.py` and 8 in `test_sprint.py`; adding `sprint_context: SprintWorkerContext | None = None` is backward-compatible and all mocks use `**kwargs` — no cascade updates actually required.

## Session Log
- `/ll:ready-issue` - 2026-06-14T15:20:23 - `1c47168d-1dcf-4e1d-8e44-83e96cbb7165.jsonl`
- `/ll:confidence-check` - 2026-06-14T16:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d1cee024-c4f6-4036-9950-3840a37ab101.jsonl`
- `/ll:wire-issue` - 2026-06-14T15:04:36 - `fa6737f4-ef9c-4c30-92bb-854a478da37c.jsonl`
- `/ll:refine-issue` - 2026-06-14T14:23:42 - `44b6af33-4270-4a3c-b93f-5ce3f689b2e8.jsonl`
- `/ll:confidence-check` - 2026-06-14T14:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/822c662f-28d6-4079-ad8d-82d73c4ff611.jsonl`
- `/ll:refine-issue` - 2026-06-14T14:13:50 - `5c2e9b75-5a1b-4b79-9b8f-961ba49fcbd8.jsonl`
- `/ll:refine-issue` - 2026-06-14T07:15:05 - `6f1984bf-3e4f-47b1-8f9b-80f0aecdbd84.jsonl`
- `/ll:refine-issue` - 2026-06-14T07:04:48 - `7ec55e37-83e6-4efd-a123-30c2a162e8a3.jsonl`
- `/ll:confidence-check` - 2026-06-14T06:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/78abf4ae-7fd0-424f-af64-8d1e965a6754.jsonl`
- `/ll:confidence-check` - 2026-06-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/47013740-85c7-4722-b055-695a04f000e8.jsonl`
- `/ll:format-issue` - 2026-06-14T05:17:38 - `cad4a66a-e81d-47ad-aff1-160b8d4f14d0.jsonl`
- `/ll:confidence-check` - 2026-06-14T08:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e3397313-7585-440e-bdb0-dd629e6d37b6.jsonl`
- `/ll:confidence-check` - 2026-06-14T09:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c098a5dc-9790-4295-bfe5-76b6a1197d7f.jsonl`
- `/ll:capture-issue` - 2026-06-14T03:50:03Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

## Status
**Open** | Priority: P1
