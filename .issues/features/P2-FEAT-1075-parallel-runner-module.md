---
discovered_date: "2026-04-12"
discovered_by: issue-size-review
parent_issue: FEAT-1072
confidence_score: 80
outcome_confidence: 78
---

# FEAT-1075: FSM ParallelRunner Module

## Blockers & Folded Criteria

**v1 contracts — must land in this PR:**

- **Structured error shape**: `ParallelItemResult.error` is a `ParallelItemError` dataclass, not a bare string. Enables retry-transient classification later without a schema break (see Proposed Solution below).
- **Thread-safety contract**: the runner MUST isolate per-worker access to known singletons (config, persistence checkpoint writer, session JSONL writer). See "Thread-safety contract" subsection below.

**v1 known limitations (documented, tracked elsewhere):**

- Worker tagging in the parent `event_callback` stream is **not added by this issue**, but IS shipped in v1 via **P2-ENH-1177** (promoted from P3, 2026-04-20). This module (FEAT-1075) propagates `self.event_callback` to child executors as-is with no wrapping; ENH-1177 adds the per-worker tagging wrapper around it. FEAT-1081 adds the minimum per-worker display label so log tails remain readable regardless of order of landing.
- `context_passthrough: bool` is binary-only in v1. Finer-grained filtering (include/exclude keys, mask secrets) is tracked under **ENH-1186** (v1 scope doc) as a post-v1 enhancement candidate.

**Signature coordination with FEAT-1174 (per-worker checkpointing):** the `ParallelRunner.run()` signature in this issue MUST include `on_worker_complete: Callable | None = None` and `starting_item_index: int = 0` parameters so FEAT-1174 can plug in the checkpoint callback and resume partial fan-outs without a signature break. See the Proposed Solution and API/Interface blocks below — both list the parameters. FEAT-1174 owns the behavior; this issue owns the signature surface.

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
class ParallelItemError:
    """Structured error for failed parallel workers.

    `kind` drives downstream retry/classification decisions without requiring
    string parsing. Keep the enum narrow; add new values only when a downstream
    state genuinely needs to distinguish.
    """
    kind: str                   # "timeout" | "exception" | "verdict_failure" | "cancelled"
    message: str                # short, single-line human-readable summary
    exc_type: str | None = None # qualified exception class name (e.g., "TimeoutError"); None for verdict_failure

@dataclass
class ParallelItemResult:
    item: str                   # original item string from items[item_index]
    item_index: int             # slot in original items list (stable; not completion order)
    verdict: str                # "yes" (reached terminal "done") | "no" (failed) | "partial" (reserved)
    terminated_by: str          # "terminal" | "error" | "timeout" | "signal" | "max_iterations" | "handoff"
    captures: dict              # child FSMExecutor.captured at exit (may be {} on early failure)
    error: ParallelItemError | None = None  # structured error when verdict != "yes"; None on success

@dataclass
class ParallelResult:
    all_results: list[ParallelItemResult]   # length == len(items); ordered by item_index (NOT completion order)
    verdict: str                            # "yes" | "partial" | "no"

    @property
    def succeeded(self) -> list[ParallelItemResult]:
        return [r for r in self.all_results if r.verdict == "yes"]

    @property
    def failed(self) -> list[ParallelItemResult]:
        return [r for r in self.all_results if r.verdict != "yes"]

class ParallelRunner:
    def run(
        self,
        items: list[str],
        loop_name: str,
        config: ParallelStateConfig,
        parent_context: dict | None = None,
        on_worker_complete: Callable[[ParallelItemResult], None] | None = None,
        starting_item_index: int = 0,
    ) -> ParallelResult:
        ...
```

**Parameter contracts:**
- `on_worker_complete` — optional callback invoked from the runner's main thread (not worker threads) each time a worker's `ParallelItemResult` is materialized into the pre-allocated slot. This is the extension point FEAT-1174 uses to write per-worker checkpoints as fan-out progresses. Callback exceptions are logged and swallowed so a bad callback cannot corrupt fan-out.
- `starting_item_index` — resume offset. When FEAT-1174 reconstructs a partial fan-out from a checkpoint, it slices the remaining items and passes the original index of the first remaining item. The runner uses this to populate `ParallelItemResult.item_index` with the absolute (not relative) slot so downstream consumers see a contiguous `[0..N)` index space regardless of resume. Default `0` = fresh fan-out.

### Ordering guarantee

`ThreadPoolExecutor.as_completed()` yields futures in completion order, NOT submission order. The runner MUST preserve original item order in `all_results`:

- Pre-allocate `results: list[ParallelItemResult | None] = [None] * len(items)` before submission.
- Submit each item along with its `item_index` (e.g., `executor.submit(self._run_worker, item, idx, ...)`).
- As each future completes, write the result into `results[item_index]`, not append.
- After join, assert `all(r is not None for r in results)` (in `fail_mode="collect"`) or fill cancelled slots with a `ParallelItemResult(verdict="no", terminated_by="cancelled", ...)` sentinel (in `fail_mode="fail_fast"`).

This makes `all_results[i]` always refer to `items[i]` regardless of worker scheduling, so downstream routing logic and `${captured.<state_name>.results[*]}` interpolation are deterministic.

**Thread mode** (`isolation: "thread"`):
- Use `ThreadPoolExecutor(max_workers=N, thread_name_prefix="fsm-parallel")`
- Each thread constructs and runs an `FSMExecutor` for one item
- Drain results with `as_completed()` — canonical pattern at `link_checker.py:286–318`
- `fail_fast`: cancel remaining futures on first failure
- Per-worker timeout (`config.timeout_seconds`): enforced via `future.result(timeout=config.timeout_seconds)` when not `None`; a `TimeoutError` is caught and recorded as a timeout verdict, then aggregated under `fail_mode` like any other failure

**Worktree mode** (`isolation: "worktree"`):
- Per-item worktree via `worktree_utils.py` (setup/teardown)
- Git operations via `GitLock` directly from `parallel/git_lock.py`
- Merge-back via `MergeCoordinator` from `parallel/merge_coordinator.py`
- **Do NOT reuse `WorkerPool`** — it is tightly coupled to `IssueInfo` and the 9-step ll-parallel workflow; implement fan-out with `ThreadPoolExecutor` directly

**Verdict derivation**:
- All succeeded → `"yes"`
- All failed → `"no"`
- Mixed → `"partial"`

**`context_passthrough: true`**: pass a **deep copy** of the parent context (`parent_context = copy.deepcopy(self.captured)`) into each worker's sub-loop initial context, produced once by the runner and then given to each worker as its own independent copy. The runner MUST NOT pass `self.captured` by reference and MUST NOT use a shallow copy — see the Thread-Safety subsection below.

### Thread-Safety: `parent_context` is a per-worker deep copy

In thread mode, all workers run in the same Python process and share the caller's memory. A shallow copy (`dict(self.captured)`) is insufficient: top-level keys are isolated, but any value that is itself a mutable container (nested dict, list) is still shared by reference across workers and with the parent. A worker that mutates a nested structure would silently corrupt state visible to every other worker.

The contract is:
- The runner produces a **deep copy per worker** of the parent's captured context using `copy.deepcopy(self.captured)` when building each worker's initial context. One copy per worker, not one shared copy across workers.
- No locks, no freezing, no conventions about which keys are "safe" to mutate — each worker owns its copy outright and may read or mutate it freely without affecting siblings or the parent.
- Worker-private outputs (anything a worker wants to report back) live in that worker's own `FSMExecutor.captured` and surface via `ParallelResult.all_captures`, not in `parent_context`.
- The parent's `self.captured` dict is untouched by fan-out. After `runner.run()` returns, `FSMExecutor._execute_parallel_state()` writes a single aggregate entry (`self.captured[state_name] = {"results": [...]}`) — that is the only mutation of parent state from parallel execution.

**Cost rationale:** `copy.deepcopy` is O(total context size). In practice captures are small flat dicts (strings, ints, small lists of IDs) and the per-worker cost is microseconds. If profiling ever shows deepcopy as a real cost (e.g., orchestrator loops passing multi-megabyte contexts), revisit — but don't optimize speculatively. The mental-model win ("your snapshot is yours, do what you want with it") eliminates a whole class of silent-corruption bugs and is worth paying for.

### Thread-safety contract (singletons outside `parent_context`)

Per-worker context deepcopy covers `captured`, but the runner also MUST NOT corrupt module-level / process-global state shared by workers. Concrete contract:

- **Config loader** (`BRConfig` / `.ll/ll-config.json` / `ll-config.toml`): resolved once in the main thread BEFORE `runner.run()` is called; workers receive a frozen/read-only snapshot via their `FSMExecutor` construction. No worker invokes the config-loading path. If a worker needs config, it reads from its snapshot — never from the disk cache.
- **Checkpoint persistence** (`PersistentExecutor._save_state()`): each worker's `PersistentExecutor` (if used) writes to a **worker-scoped** checkpoint path — never the parent loop's checkpoint file. The parent's checkpoint is written only from the main thread, after `runner.run()` returns. The actual file-layout contract for per-worker checkpoint paths is specified in **FEAT-1174**. This issue just guarantees the parent file is untouched from worker threads.
- **Session JSONL logging** (`get_current_session_jsonl()`): writes are line-delimited JSONL and rely on OS-level atomic append-writes of single `\n`-terminated records up to PIPE_BUF. Workers MUST write one-line-per-event only and MUST NOT buffer multi-line records. No shared Python-level file handle is passed between threads; each worker opens its own handle in append mode.
- **Module-level caches** (e.g., loop-fragment caches, schema validator singletons): read-only post-init. The runner MUST verify during implementation that no cache performs lazy write-on-read; if one does, pre-warm it in the main thread before fan-out.

A dedicated test class `TestParallelRunnerSingletonSafety` in `test_parallel_runner.py` (added by FEAT-1077) exercises each of these. See FEAT-1077 Acceptance Criteria for the specific tests.

### Event callback worker-tagging (scope boundary with ENH-1177)

Workers' child `FSMExecutor` instances each emit their own event stream to the **same** `event_callback` the parent was constructed with. Without a tagging wrapper, these streams would merge with no per-worker attribution.

Scope split:
- **This issue (FEAT-1075)**: propagate `self.event_callback` to child executors as-is. No per-worker wrapping, no tagging. The runner simply hands the callback through. This keeps the runner module self-contained and easy to unit-test.
- **ENH-1177 (P2, ships v1)**: adds the per-worker tagging wrapper at the callsite (either in `_execute_parallel_state()` or as a thin adapter around `runner.run()`). Adds `worker_index`, `worker_label`, `parallel_state` fields to the `Event` dataclass. Since ENH-1177 is P2 and in the v1 ship, end users WILL see tagged events — this issue just doesn't do the tagging itself.
- **FEAT-1081**: adds the CLI display minimum (per-worker label in `ll-loop info --verbose` and live output) so log tails are debuggable independently of the structured event tagging.

Document the scope boundary in the module docstring so extension authors understand where tagging happens (ENH-1177's wrapper) vs. where the raw callback flows (this module).

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
        on_worker_complete: Callable[[ParallelItemResult], None] | None = None,
        starting_item_index: int = 0,
    ) -> ParallelResult: ...
```

## Implementation Steps

1. Define `ParallelResult` dataclass with `succeeded`, `failed`, `all_captures`, `verdict` fields
2. Implement thread mode: `ThreadPoolExecutor(max_workers=N)` + `as_completed()` — follow `link_checker.py:286–318` pattern
3. Implement `fail_fast`: cancel remaining futures on first failure
4. Implement worktree mode: per-item worktree via `worktree_utils.py`, merge-back via `MergeCoordinator`
5. Implement `context_passthrough` to inject a **deep copy** of the parent context (`copy.deepcopy(parent_context)`) into each worker's initial sub-loop context; workers must never see the parent's live captured dict by reference, and a shallow copy is insufficient because nested containers (dicts, lists) would still be shared (see Thread-Safety subsection)
6. Derive verdict: all succeeded → `"yes"`, all failed → `"no"`, mixed → `"partial"`
7. Verify module is importable standalone (no circular executor dependency)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Export from `scripts/little_loops/fsm/__init__.py` — add `from little_loops.fsm.parallel_runner import (ParallelRunner, ParallelResult)` block; add both to `__all__`; add `# Parallel Execution` entry to module docstring (lines 1–68); verify `test_review_loop.py` still passes (imports from this init)
9. **Use correct test path** — `scripts/tests/test_parallel_runner.py` (not `scripts/tests/fsm/test_parallel_runner.py`; the `fsm/` subdirectory does not exist)

## Acceptance Criteria

- `ParallelItemResult` dataclass exists with `item`, `item_index`, `verdict`, `terminated_by`, `captures`, `error` fields (see Proposed Solution for types)
- `ParallelResult` dataclass exists with `all_results: list[ParallelItemResult]` and `verdict: str`; exposes `succeeded`/`failed` as derived `@property` filters over `all_results`
- Ordering guarantee: `all_results[i]` always corresponds to `items[i]` regardless of completion order; results are written into the pre-allocated slot by `item_index`, never appended from `as_completed()` order
- Thread mode: 4 items with `max_workers: 2` run 2 at a time; all captures collected
- Thread mode `fail_fast`: remaining futures cancelled on first failure; cancelled slots populated with `ParallelItemResult(verdict="no", terminated_by="cancelled", ...)` so `all_results` length still equals `len(items)`
- Worktree mode: each item gets its own worktree; changes merged back
- `context_passthrough: true` passes a **deep copy** (`copy.deepcopy(parent_captured)`) of parent context to each worker — one independent copy per worker, never the live dict and never a shallow copy (nested containers would still be shared)
- Concurrent workers may read or mutate their per-worker `parent_context` copy without affecting siblings or the parent: a test spawns N workers that each mutate nested structures in their copy and asserts no cross-worker divergence and no mutation of the parent's captured dict (belongs in FEAT-1077 as `test_parallel_runner_context_passthrough_is_deep_copy_per_worker`)
- Per-worker timeout: when `timeout_seconds` is set, a worker exceeding it records `ParallelItemResult(verdict="no", terminated_by="timeout", error="worker exceeded timeout_seconds=N")` and is aggregated under `fail_mode`; `timeout_seconds=None` disables the timeout
- Verdict derivation: all `verdict=="yes"` → aggregate `"yes"`; all non-`"yes"` → aggregate `"no"`; mixed → `"partial"`
- Each failed `ParallelItemResult` carries a `ParallelItemError` with `kind` ∈ `{"timeout", "exception", "verdict_failure", "cancelled"}`, a short single-line `message`, and `exc_type` (qualified exception class name when applicable, else `None`). Classification rules: child `ExecutionResult.terminated_by == "timeout"` → `kind="timeout"`; a worker-level Python exception → `kind="exception"` with `exc_type` set; child terminated normally but not at `done` → `kind="verdict_failure"`; cancelled in `fail_fast` → `kind="cancelled"`
- `ParallelItemError` is serialized as a plain dict (`{"kind": ..., "message": ..., "exc_type": ...}`) when stored into `self.captured[state_name].results[i].error` by FEAT-1076 — downstream states read `${captured.<state>.results[i].error.kind}` without any string parsing
- Thread-safety contract honored: a `TestParallelRunnerSingletonSafety` test (scaffolding owned by FEAT-1077; audit-driven test methods contributed by ENH-1185) asserts the parent's config snapshot, checkpoint file, and session JSONL file are not written from worker threads
- `on_worker_complete` callback is invoked from the runner's main thread exactly once per completed worker with that worker's fully-populated `ParallelItemResult`; callback exceptions are caught, logged, and do not abort fan-out (FEAT-1174 is the primary consumer; contract surfaced here so the signature is stable at v1)
- `starting_item_index` offsets the `item_index` assignment: when called with `starting_item_index=3` and `items=["c", "d"]`, the returned `all_results[0].item_index == 3` and `all_results[1].item_index == 4` (resume-aware indexing for FEAT-1174)
- Module importable standalone without executor dependency

## Tests (owned by this issue)

Moved from FEAT-1077 (2026-04-20) to break the circular dependency where FEAT-1077 gated on FEAT-1075 but FEAT-1076 needed runner tests passing before it could merge. Unit tests for the runner now land with this issue:

- **`scripts/tests/test_parallel_runner.py` — mocked-executor unit suite:**
  - Thread mode: captures collected, verdict derived correctly
  - Thread mode `fail_fast`: remaining futures cancelled on first failure
  - Worktree mode: mock worktree setup/teardown, merge-back called
  - `context_passthrough: true` passes parent context to each worker
  - `test_parallel_runner_context_passthrough_is_deep_copy_per_worker` — deep-copy contract (thread-safety invariant): N≥4 workers mutate nested structures; assert no sibling bleed and parent captured dict is byte-for-byte unchanged (identity check on nested containers)
  - `test_parallel_runner_preserves_item_order_under_async_completion` — ordering guarantee: 4 items with durations `[3.0, 1.0, 2.0, 0.5]`s, assert `result.all_results[i].item == items[i]` regardless of completion order
  - `timeout_seconds`: worker exceeding timeout records `ParallelItemResult(verdict="no", terminated_by="timeout", …)`; `timeout_seconds=None` means no timeout
  - Edge: 0 items → `ParallelResult(all_results=[], verdict="yes")` with empty `.succeeded`/`.failed`
  - Edge: 1 item fails of 1 → `result.verdict == "no"`, `result.failed[0].error` non-empty
- **`ParallelItemError` classification tests** — one test per `kind` value (`timeout`, `exception`, `verdict_failure`, `cancelled`) asserting both `kind` and `exc_type` are set correctly
- **`test_parallel_runner_invokes_on_worker_complete_per_worker`** — 4 items, passing `on_worker_complete` callback; assert callback is invoked 4 times, once per worker, each with a fully-populated `ParallelItemResult`; assert invocation happens from the runner's main thread (not worker threads) by capturing `threading.current_thread().name` in the callback
- **`test_parallel_runner_on_worker_complete_exception_is_swallowed`** — callback raises; fan-out still completes; assert a WARN-level log entry is produced and `ParallelResult` is fully populated
- **`test_parallel_runner_starting_item_index_offsets_absolute_index`** — call with `items=["c", "d"]`, `starting_item_index=3`; assert `all_results[0].item_index == 3`, `all_results[1].item_index == 4`

Integration-level real-threading tests (`TestParallelRunnerRealThreading`), singleton-safety scaffolding (`TestParallelRunnerSingletonSafety`), and the end-to-end loop tests remain with FEAT-1077.

## Related / See Also

- **ENH-1173** (`.issues/enhancements/P3-ENH-1173-extend-unresolved-context-variable-pre-scan-to-cover-parallel-items.md`) — extends the `cli/loop/run.py` unresolved-context-variable pre-scan to cover `state.parallel.items`. Runner code doesn't change, but the author-experience gap around unresolved `{{ }}` in `items:` closes there rather than here.

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
