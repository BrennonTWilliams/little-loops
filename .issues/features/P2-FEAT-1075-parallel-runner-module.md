---
discovered_date: "2026-04-12"
discovered_by: issue-size-review
parent_issue: FEAT-1072
confidence_score: 80
outcome_confidence: 78
---

# FEAT-1075: FSM ParallelRunner Module

## Summary

Create `scripts/little_loops/fsm/parallel_runner.py` — the `ParallelRunner` class that fans out N sub-loop executions in either thread or worktree isolation mode and returns a `ParallelResult`.

## Current Behavior

The `parallel:` FSM state type has no execution engine. There is no `ParallelRunner` class or `ParallelResult` dataclass in `scripts/little_loops/fsm/`; attempting to use a parallel state in a loop YAML would fail at dispatch time.

## Expected Behavior

`scripts/little_loops/fsm/parallel_runner.py` exists and exports `ParallelRunner` and `ParallelResult`. Calling `ParallelRunner.run(items, loop_name, config)` fans out one sub-loop execution per item (thread or worktree mode), collects captures from all workers, and returns a `ParallelResult` with `succeeded`, `failed`, `all_captures`, and `verdict` fields.

## Motivation

This module is the core execution engine for the `parallel:` FSM state type:
- Enables concurrent sub-loop fan-out, reducing total loop runtime for multi-item workloads
- Unblocks FEAT-1076 (executor dispatch) and ultimately FEAT-1072 (full parallel state feature end-to-end)
- Designed to reuse existing patterns (`ThreadPoolExecutor` from `link_checker.py`, `worktree_utils.py`) rather than introducing new dependencies

## Parent Issue

Decomposed from FEAT-1072: Add `parallel:` State Type to FSM for Concurrent Sub-Loop Fan-Out

## Proposed Solution

### fsm/parallel_runner.py (new, ~150 lines)

```python
@dataclass
class ParallelResult:
    succeeded: list[str]        # item values that reached terminal "done"
    failed: list[str]           # items that did not
    all_captures: list[dict]    # per-worker captured dicts (indexed by item order)
    verdict: str                # "yes" | "partial" | "no"

class ParallelRunner:
    def run(
        self,
        items: list[str],
        loop_name: str,
        config: ParallelStateConfig,
        parent_context: dict | None = None,
    ) -> ParallelResult:
        ...
```

**Thread mode** (`isolation: "thread"`):
- Use `ThreadPoolExecutor(max_workers=N, thread_name_prefix="fsm-parallel")` 
- Each thread constructs and runs an `FSMExecutor` for one item
- Drain results with `as_completed()` — canonical pattern at `link_checker.py:286–318`
- `fail_fast`: cancel remaining futures on first failure

**Worktree mode** (`isolation: "worktree"`):
- Per-item worktree via `worktree_utils.py` (setup/teardown)
- Git operations via `GitLock` directly from `parallel/git_lock.py`
- Merge-back via `MergeCoordinator` from `parallel/merge_coordinator.py`
- **Do NOT reuse `WorkerPool`** — it is tightly coupled to `IssueInfo` and the 9-step ll-parallel workflow; implement fan-out with `ThreadPoolExecutor` directly

**Verdict derivation**:
- All succeeded → `"yes"`
- All failed → `"no"`
- Mixed → `"partial"`

**`context_passthrough: true`**: pass parent context dict into each worker's sub-loop initial context.

## Files to Create/Modify

- `scripts/little_loops/fsm/parallel_runner.py` — new module (~150 lines)

## Dependencies

- FEAT-1074 must be complete (needs `ParallelStateConfig` from schema.py)
- Reuses: `worktree_utils.py`, `parallel/git_lock.py`, `parallel/merge_coordinator.py`
- **Does not reuse** `parallel/worker_pool.py` (coupling to `IssueInfo`)

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/parallel_runner.py` — new module (create)
- `scripts/little_loops/fsm/__init__.py` — add `from little_loops.fsm.parallel_runner import (ParallelRunner, ParallelResult)` block, add both to `__all__`, add `# Parallel Execution` entry to module docstring [Wiring pass added by `/ll:wire-issue`]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — will import `ParallelRunner` (wired in FEAT-1076)
- `scripts/little_loops/fsm/schema.py` — provides `ParallelStateConfig` (from FEAT-1074)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/layout.py:118` — `_get_state_badge()` dispatches on state type; needs `state.parallel is not None` branch and `_PARALLEL_BADGE` constant (scope: FEAT-1078)
- `scripts/little_loops/cli/loop/info.py:548` — `_print_state_overview_table()` derives "Type" column; falls through to `"—"` for parallel states without an explicit branch (scope: FEAT-1078)
- `scripts/little_loops/fsm/persistence.py` — imports `FSMExecutor`/`ExecutionResult` from `executor.py`; not a direct consumer of `parallel_runner.py`, but sits in the same package and will exercise the module indirectly via `FSMExecutor` once FEAT-1076 is complete

### Similar Patterns
- `scripts/little_loops/link_checker.py` — canonical `ThreadPoolExecutor` + `as_completed` pattern (lines 284–318)
- `scripts/little_loops/parallel/worker_pool.py` — pattern reference only (not reusable directly)

### Tests
- `scripts/tests/test_parallel_runner.py` — new test file (added in FEAT-1077); **NOTE**: path corrected by wiring pass — `scripts/tests/fsm/` subdirectory does NOT exist; all FSM tests live flat in `scripts/tests/`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py:3480-3492` — canonical sub-loop test pattern to follow: writes child YAML to `tmp_path / ".loops"`, passes `loops_dir=loops_dir` to `FSMExecutor`; however the issue's note (line ~236) says parallel runner tests **should mock `FSMExecutor.run()` directly** rather than using real execution
- `scripts/tests/test_cli_loop_worktree.py` — worktree/GitLock mock pattern: `patch.object(git_lock, "run", side_effect=_mock_run)` to capture git calls without real git; use this pattern for worktree mode unit tests
- `scripts/tests/test_link_checker.py:301-353` — `ThreadPoolExecutor` + `as_completed` mock pattern; no `fail_fast` cancellation tests exist anywhere in the codebase — need to write those as new
- `scripts/tests/test_review_loop.py:19` — imports `from little_loops.fsm import validate_fsm`; a broken `fsm/__init__.py` import would fail this test — verify __init__.py update doesn't introduce circular imports

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:3653-3665` — submodule table listing all fsm/ modules; add row for `little_loops.fsm.parallel_runner` (scope: FEAT-1078, but blocking doc accuracy)
- `docs/reference/API.md:3669-3686` — Quick Import block grouped by category; add `ParallelRunner`/`ParallelResult` to the Execution category (scope: FEAT-1078)
- `docs/ARCHITECTURE.md:254-266` — fsm/ directory tree listing; add `parallel_runner.py` entry (scope: FEAT-1078)
- `CONTRIBUTING.md:231` — identical fsm/ directory tree; add `parallel_runner.py` entry (scope: FEAT-1078)

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/fsm-loop-schema.json:174-292` — stateConfig definition has `additionalProperties: false`; adding `parallel:` field is FEAT-1074 scope but must land before this module is usable
- `config-schema.json:658-669` — `loops.glyphs` object has `additionalProperties: false`; a `"parallel"` glyph key must be added here (scope: FEAT-1078); this blocks user-configurable parallel state display colors

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`FSMExecutor` constructor** (`executor.py:92-116`) — all params except `fsm` are optional:
```python
FSMExecutor(
    fsm: FSMLoop,
    event_callback: EventCallback | None = None,
    action_runner: ActionRunner | None = None,
    signal_detector: SignalDetector | None = None,
    handoff_handler: HandoffHandler | None = None,
    loops_dir: Path | None = None,
)
```

**Child executor construction pattern** (`executor.py:354-361`) — the exact pattern for spawning a sub-loop executor:
```python
child_executor = FSMExecutor(
    child_fsm,
    action_runner=self.action_runner,   # share parent runner
    loops_dir=self.loops_dir,           # share loops base dir
    event_callback=_sub_event_callback, # depth-injecting wrapper
)
child_executor._depth = depth           # set post-construction
child_result = child_executor.run()     # returns ExecutionResult
```
`child_result.terminated_by` (`"terminal"`, `"error"`, `"max_iterations"`) and `child_result.final_state` (`"done"` or other terminal) drive succeeded/failed classification.

**Sub-loop loading** — `resolve_loop_path` and `load_and_validate` are lazy-imported inside `_execute_sub_loop` at `executor.py:328-329`. **Correct imports** (both differ from what was originally noted):
```python
from little_loops.cli.loop._helpers import resolve_loop_path  # NOT from fsm.runners
from little_loops.fsm.validation import load_and_validate     # NOT from fsm.schema
```
`resolve_loop_path` (`_helpers.py:93-114`) resolution chain: raw path → `<loops_dir>/<name>.fsm.yaml` → `<loops_dir>/<name>.yaml` → bundled plugin loops dir → `FileNotFoundError`. Called as `resolve_loop_path(state.loop, self.loops_dir or Path(".loops"))` (`executor.py:332`).

**`worktree_utils.setup_worktree`** (`worktree_utils.py:20-99`):
```python
def setup_worktree(
    repo_path: Path, worktree_path: Path, branch_name: str,
    copy_files: list[str], logger: Logger, git_lock: GitLock,
) -> None
```

**`worktree_utils.cleanup_worktree`** (`worktree_utils.py:102-142`):
```python
def cleanup_worktree(
    worktree_path: Path, repo_path: Path, logger: Logger,
    git_lock: GitLock, delete_branch: bool = True,
) -> None
```

**`GitLock` constructor** (`git_lock.py:44-65`) and key method:
```python
GitLock(logger=None, max_retries=3, initial_backoff=0.5, max_backoff=8.0)
git_lock.run(args: list[str], cwd: Path, timeout: int = 30) -> CompletedProcess
```

**`MergeCoordinator` compatibility concern** (`merge_coordinator.py:44-79`): constructor takes `config: ParallelConfig` (from `parallel/types.py`) and `queue_merge(worker_result: WorkerResult)` takes `WorkerResult` (ll-parallel's IssueInfo-coupled type). The ParallelRunner will need to either (a) implement worktree merge directly without `MergeCoordinator`, or (b) bridge `ParallelStateConfig` → `ParallelConfig`. Investigate at implementation time.

**`ExecutionResult` fields** (`fsm/types.py`): `final_state: str`, `terminated_by: str`, `captured: dict[str, dict[str, Any]]` — terminated_by values: `"terminal"`, `"error"`, `"max_iterations"`, `"timeout"`, `"signal"`.

**`ParallelStateConfig` status**: Confirmed absent from `schema.py` — FEAT-1074 is a hard blocker. Do not begin implementation until FEAT-1074 is merged.

## Use Case

**Who**: Developer configuring an FSM loop that processes a list of items concurrently

**Context**: A loop YAML defines a `parallel:` state with `items: ["file-a.py", "file-b.py"]` and `loop: lint-check`. The loop should run `lint-check` against each item concurrently rather than sequentially.

**Goal**: Fan out N sub-loop instances (one per item) with configurable isolation (thread or worktree) and optional fail-fast behavior.

**Outcome**: A `ParallelResult` is returned with per-item outcomes, collected captures, and an overall verdict (`"yes"` / `"partial"` / `"no"`) that the FSM executor uses to route to the next state.

## API/Interface

```python
@dataclass
class ParallelResult:
    succeeded: list[str]        # item values that reached terminal "done"
    failed: list[str]           # items that did not
    all_captures: list[dict]    # per-worker captured dicts (indexed by item order)
    verdict: str                # "yes" | "partial" | "no"

class ParallelRunner:
    def run(
        self,
        items: list[str],
        loop_name: str,
        config: ParallelStateConfig,
        parent_context: dict | None = None,
    ) -> ParallelResult: ...
```

## Implementation Steps

1. Define `ParallelResult` dataclass with `succeeded`, `failed`, `all_captures`, `verdict` fields
2. Implement thread mode: `ThreadPoolExecutor(max_workers=N)` + `as_completed()` — follow `link_checker.py:286–318` pattern
3. Implement `fail_fast`: cancel remaining futures on first failure
4. Implement worktree mode: per-item worktree via `worktree_utils.py`, merge-back via `MergeCoordinator`
5. Implement `context_passthrough` to inject parent context dict into each worker's initial sub-loop context
6. Derive verdict: all succeeded → `"yes"`, all failed → `"no"`, mixed → `"partial"`
7. Verify module is importable standalone (no circular executor dependency)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Export from `scripts/little_loops/fsm/__init__.py` — add `from little_loops.fsm.parallel_runner import (ParallelRunner, ParallelResult)` block; add both to `__all__`; add `# Parallel Execution` entry to module docstring (lines 1–68); verify `test_review_loop.py` still passes (imports from this init)
9. **Use correct test path** — `scripts/tests/test_parallel_runner.py` (not `scripts/tests/fsm/test_parallel_runner.py`; the `fsm/` subdirectory does not exist)

## Acceptance Criteria

- `ParallelResult` dataclass exists with `succeeded`, `failed`, `all_captures`, `verdict`
- Thread mode: 4 items with `max_workers: 2` run 2 at a time; all captures collected
- Thread mode `fail_fast`: remaining futures cancelled on first failure
- Worktree mode: each item gets its own worktree; changes merged back
- `context_passthrough: true` passes parent context dict to each worker
- Verdict: all succeed → `"yes"`, all fail → `"no"`, mixed → `"partial"`
- Module importable standalone without executor dependency

## Implementation Notes

- `link_checker.py:284–318` is the canonical `ThreadPoolExecutor` + `as_completed` pattern in this codebase (`scripts/little_loops/link_checker.py`, not `parallel/`)
- `WorkerPool` in `parallel/worker_pool.py` — pattern reference only (NOT reusable directly); shows `ThreadPoolExecutor(max_workers=N, thread_name_prefix=...)` constructor and `Future`-based result tracking
- `_execute_sub_loop()` at `executor.py:318–381` — analogue; `_execute_parallel_state()` fans out N instances. `self.captured[self.current_state] = child_executor.captured` (line 364) shows how single-child captures merge back; parallel stores `{"results": [...]}`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Worker verdict logic**: `child_result.terminated_by == "terminal"` and `child_result.final_state == "done"` → succeeded; all other `terminated_by` values (`"error"`, `"max_iterations"`, `"timeout"`, `"signal"`, `"handoff"`) or non-`"done"` terminal states → failed. Note: `"handoff"` is a valid `terminated_by` value in `ExecutionResult` (`types.py:16-54`) — treat as failure since the sub-loop did not complete normally
- **Thread-name prefix convention**: `worker_pool.py` uses `"issue-worker"`; use `"fsm-parallel"` for this module (already in proposed solution)
- **Context passthrough**: `_execute_sub_loop` at `executor.py:336-343` merges context as `{**self.fsm.context, **captured_as_context, **child_fsm.context}` — implement parallel context injection following the same merge order
- **Depth tracking**: child executor `_depth` is set post-construction via `child_executor._depth = depth`; parallel workers should propagate depth+1
- **MergeCoordinator is NOT directly usable** for worktree mode: it expects `ParallelConfig` (ll-parallel) and `WorkerResult` (IssueInfo-coupled). Implement worktree merge directly using `git_lock.run(["merge", "--no-ff", branch_name], cwd=repo_path)` instead, or investigate if a thin bridge suffices
- **Dataclass conventions** (`fsm/types.py`, `parallel/types.py`): required fields first, optional fields with `None` default at end, mutable defaults use `field(default_factory=...)` — follow same pattern for `ParallelResult`
- **Test pattern** (`test_fsm_executor.py:3480-3492`): sub-loop tests write child YAML to `tmp_path / ".loops"` and pass `loops_dir=loops_dir` to `FSMExecutor`; parallel runner tests should mock `FSMExecutor.run()` directly to avoid full execution overhead
- **`worktree_utils.py` correct path**: the module lives at `scripts/little_loops/worktree_utils.py`, NOT `scripts/little_loops/parallel/worktree_utils.py`. Import as `from little_loops.worktree_utils import setup_worktree, cleanup_worktree`. The `parallel/` directory contains `git_lock.py`, `merge_coordinator.py`, `worker_pool.py` — but NOT `worktree_utils.py`
- **Standalone worktree pattern** (`cli/loop/run.py:171-215`): the simplest per-item worktree lifecycle in the codebase; uses `GitLock(logger)` directly, calls `setup_worktree(repo_path, worktree_path, branch_name, copy_files, logger, git_lock)`, registers cleanup via `atexit.register`. Branch name pattern: `f"{timestamp}-{safe_loop_name}"` where `safe_loop_name = re.sub(r"[^a-zA-Z0-9-]", "-", loop_name)`. For `ParallelRunner` worktree mode, adapt this pattern per-item with `try/finally` (not `atexit`) for proper cleanup under concurrent execution

## Impact

- **Priority**: P2 — Required dependency for FEAT-1076 (executor dispatch); blocks parallel FSM end-to-end delivery
- **Effort**: Medium — New module ~150 lines; follows existing `ThreadPoolExecutor` + `as_completed` pattern
- **Risk**: Low — Self-contained new module; no changes to existing code paths
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `executor`

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-12_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 78/100 → MODERATE

### Concerns
- **FEAT-1074 not complete**: `ParallelStateConfig` does not exist in `schema.py`. The `ParallelRunner.run()` signature requires it. Do not begin implementation until FEAT-1074 is merged.
- **Test gap**: Tests are deferred to FEAT-1077. This module will be untested until that issue ships — plan to implement FEAT-1077 immediately after.
- **`resolve_loop_path` import**: ~~verify exact import~~ RESOLVED — `from little_loops.cli.loop._helpers import resolve_loop_path` (`_helpers.py:93`); `load_and_validate` is at `from little_loops.fsm.validation import load_and_validate` (`validation.py:451`). Neither is in `fsm.runners` or `fsm.schema`.

## Session Log
- `/ll:refine-issue` - 2026-04-12T21:44:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ba00a202-7579-41c1-8d16-ccc842c9ed69.jsonl`
- `/ll:confidence-check` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/76789ff6-088d-4a98-b81f-58898ce4522f.jsonl`
- `/ll:wire-issue` - 2026-04-12T21:38:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a7762782-0f79-4152-a3a2-b2f202799611.jsonl`
- `/ll:refine-issue` - 2026-04-12T21:32:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/34932e3c-e378-4fd7-9886-68460b918395.jsonl`
- `/ll:format-issue` - 2026-04-12T21:28:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/80e2b48b-2183-43e6-9b2d-906181c202b3.jsonl`
- `/ll:issue-size-review` - 2026-04-12T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8e4e49c-4e79-4270-9839-915fa38b03f2.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P2
