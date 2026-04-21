---
discovered_date: "2026-04-12"
discovered_by: issue-size-review
parent_issue: FEAT-1072
confidence_score: 80
outcome_confidence: 76
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 18
size: Very Large
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
- `scripts/little_loops/cli/loop/layout.py:119` — `_get_state_badge()` dispatches on state type; needs `state.parallel is not None` branch and `_PARALLEL_BADGE` constant (scope: FEAT-1078)
- `scripts/little_loops/cli/loop/info.py:548` — `_print_state_overview_table()` derives "Type" column; falls through to `"—"` for parallel states without an explicit branch (scope: FEAT-1078)
- `scripts/little_loops/fsm/persistence.py` — imports `FSMExecutor`/`ExecutionResult` from `executor.py`; not a direct consumer of `parallel_runner.py`, but sits in the same package and will exercise the module indirectly via `FSMExecutor` once FEAT-1076 is complete
- `scripts/little_loops/fsm/validation.py` — `_validate_state_action()` (line ~195) needs a `parallel`/`action`/`loop` mutual-exclusion check; `_validate_state_routing()` (line ~230) needs a `has_parallel = state.parallel is not None` guard alongside `has_loop` so a parallel state with no explicit `next`/routing table does not raise "State has no transition defined" error; both changes are FEAT-1074 scope but MUST land before any parallel loop YAML passes `validate_fsm()` [Wiring pass added by `/ll:wire-issue`]

### Similar Patterns
- `scripts/little_loops/link_checker.py` — canonical `ThreadPoolExecutor` + `as_completed` pattern (lines 284–318)
- `scripts/little_loops/parallel/worker_pool.py` — pattern reference only (not reusable directly)

### Tests
- `scripts/tests/test_parallel_runner.py` — new test file (added in FEAT-1077); **NOTE**: path corrected by wiring pass — `scripts/tests/fsm/` subdirectory does NOT exist; all FSM tests live flat in `scripts/tests/`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py:3634+` (`TestSubLoopExecution`) — canonical sub-loop test pattern to follow: writes child YAML to `tmp_path / ".loops"`, passes `loops_dir=loops_dir` to `FSMExecutor`; however the issue's note says parallel runner tests **should mock `FSMExecutor.run()` directly** rather than using real execution. _Note: lines 3480-3492 (previously cited) are inside `TestPerStateRetryLimits._make_fsm` — not sub-loop tests; corrected by wiring pass_
- `scripts/tests/test_cli_loop_worktree.py` — worktree/GitLock mock pattern: `patch.object(git_lock, "run", side_effect=_mock_run)` to capture git calls without real git; use this pattern for worktree mode unit tests
- `scripts/tests/test_link_checker.py:301-353` — `ThreadPoolExecutor` + `as_completed` mock pattern; no `fail_fast` cancellation tests exist anywhere in the codebase — need to write those as new
- `scripts/tests/test_review_loop.py:19` — imports `from little_loops.fsm import validate_fsm`; a broken `fsm/__init__.py` import would fail this test — verify __init__.py update doesn't introduce circular imports
- `scripts/tests/test_fsm_executor.py:4661-4677` — export test pattern (inline `from little_loops.fsm import <name>` in test methods); follow this pattern in `test_parallel_runner.py` to add tests verifying `from little_loops.fsm import ParallelRunner` and `from little_loops.fsm import ParallelResult` are importable [Wiring pass added by `/ll:wire-issue`]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:3713-3724` — submodule table listing all fsm/ modules; add row for `little_loops.fsm.parallel_runner` (scope: FEAT-1078, but blocking doc accuracy). _Line range re-verified 2026-04-20; drifted from 3653-3665._
- `docs/reference/API.md:3726+` — Quick Import block grouped by category; add `ParallelRunner`/`ParallelResult` to the Execution category (scope: FEAT-1078)
- `docs/ARCHITECTURE.md:255-266` — fsm/ directory tree listing; add `parallel_runner.py` entry (scope: FEAT-1078)
- `CONTRIBUTING.md:231` — identical fsm/ directory tree; add `parallel_runner.py` entry (scope: FEAT-1078)
- `docs/reference/CONFIGURATION.md` — `loops.glyphs` table lists the 6 badge keys (`prompt`, `slash_command`, `shell`, `mcp_tool`, `sub_loop`, `route`); needs a `"parallel"` row when a parallel badge glyph is introduced (scope: FEAT-1078; different file from the already-noted `config-schema.json`) [Wiring pass added by `/ll:wire-issue`]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/fsm-loop-schema.json:175-321` — stateConfig definition has `additionalProperties: false`; adding `parallel:` field is FEAT-1074 scope but must land before this module is usable. _Line range re-verified 2026-04-20; drifted from 174-292._
- `config-schema.json:760-773` — `loops.glyphs` object (lines 760-773) has `additionalProperties: false`; a `"parallel"` glyph key must be added here (scope: FEAT-1078); this blocks user-configurable parallel state display colors. _Location re-verified 2026-04-20; drifted significantly from 658-669._
- `scripts/little_loops/config/features.py:257-288` — `LoopsGlyphsConfig` Python dataclass mirrors the `loops.glyphs` JSON schema object with 6 fields; must add `parallel: str` field alongside the JSON schema and CONFIGURATION.md changes (scope: FEAT-1078) [Wiring pass added by `/ll:wire-issue`]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`FSMExecutor` constructor** (`executor.py:120-142`) — all params except `fsm` are optional. _Signature re-verified 2026-04-20; new `circuit: RateLimitCircuit | None = None` parameter added since prior refinement — workers MUST propagate the parent's circuit so cross-worktree 429 coordination works under fan-out; child sub-loop construction at executor.py:402-408 already passes `circuit=self._circuit`._
```python
FSMExecutor(
    fsm: FSMLoop,
    event_callback: EventCallback | None = None,
    action_runner: ActionRunner | None = None,
    signal_detector: SignalDetector | None = None,
    handoff_handler: HandoffHandler | None = None,
    loops_dir: Path | None = None,
    circuit: RateLimitCircuit | None = None,
)
```

**Child executor construction pattern** (`executor.py:402-410`) — the exact pattern for spawning a sub-loop executor. _Line range re-verified 2026-04-20; drifted from 354-361._
```python
child_executor = FSMExecutor(
    child_fsm,
    action_runner=self.action_runner,   # share parent runner
    loops_dir=self.loops_dir,           # share loops base dir
    event_callback=_sub_event_callback, # depth-injecting wrapper
    circuit=self._circuit,              # share rate-limit circuit for 429 coordination
)
child_executor._depth = depth           # set post-construction
child_result = child_executor.run()     # returns ExecutionResult
```
`child_result.terminated_by` (`"terminal"`, `"error"`, `"max_iterations"`) and `child_result.final_state` (`"done"` or other terminal) drive succeeded/failed classification.

**Sub-loop loading** — `resolve_loop_path` and `load_and_validate` are lazy-imported inside `_execute_sub_loop` at `executor.py:376-377`. _Line re-verified 2026-04-20; drifted from 328-329._ **Correct imports** (both differ from what was originally noted):
```python
from little_loops.cli.loop._helpers import resolve_loop_path  # NOT from fsm.runners
from little_loops.fsm.validation import load_and_validate     # NOT from fsm.schema
```
`resolve_loop_path` (`_helpers.py:93-114`) resolution chain: raw path → `<loops_dir>/<name>.fsm.yaml` → `<loops_dir>/<name>.yaml` → bundled plugin loops dir → `FileNotFoundError`. Called as `resolve_loop_path(state.loop, self.loops_dir or Path(".loops"))` (`executor.py:380`).

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
10. **Verify FEAT-1074 covers `validation.py`** — before beginning implementation, confirm that FEAT-1074 added (a) a `parallel`/`action`/`loop` mutual-exclusion check to `_validate_state_action()` and (b) a `has_parallel` guard to `_validate_state_routing()`; if absent, any FSM loop YAML with a `parallel:` state will fail `validate_fsm()` regardless of whether `parallel_runner.py` itself is correct [Wiring pass added by `/ll:wire-issue`]

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
- `_execute_sub_loop()` at `executor.py:366-431` — analogue; `_execute_parallel_state()` fans out N instances. `self.captured[self.current_state] = child_executor.captured` (line 414) shows how single-child captures merge back; parallel stores `{"results": [...]}`. _Line ranges re-verified 2026-04-20; drifted from 318-381 / 364._

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Worker verdict logic**: `child_result.terminated_by == "terminal"` and `child_result.final_state == "done"` → succeeded; all other `terminated_by` values (`"error"`, `"max_iterations"`, `"timeout"`, `"signal"`, `"handoff"`) or non-`"done"` terminal states → failed. Note: `"handoff"` is a valid `terminated_by` value in `ExecutionResult` (`types.py:16-54`) — treat as failure since the sub-loop did not complete normally
- **Thread-name prefix convention**: `worker_pool.py` uses `"issue-worker"`; use `"fsm-parallel"` for this module (already in proposed solution)
- **Context passthrough**: `_execute_sub_loop` at `executor.py:383-391` merges context as `{**self.fsm.context, **captured_as_context, **child_fsm.context}` — implement parallel context injection following the same merge order. _Line range re-verified 2026-04-20; drifted from 336-343._ Note: sub-loop path also strips `.output` values from capture dicts before merging (`captured_as_context` comprehension at 387-390) so `${context.key}` resolves to the plain output string; parallel workers should preserve this behavior when building per-worker initial context
- **Depth tracking**: child executor `_depth` is set post-construction via `child_executor._depth = depth`; parallel workers should propagate depth+1
- **MergeCoordinator is NOT directly usable** for worktree mode: it expects `ParallelConfig` (ll-parallel) and `WorkerResult` (IssueInfo-coupled). Implement worktree merge directly using `git_lock.run(["merge", "--no-ff", branch_name], cwd=repo_path)` instead, or investigate if a thin bridge suffices
- **Dataclass conventions** (`fsm/types.py`, `parallel/types.py`): required fields first, optional fields with `None` default at end, mutable defaults use `field(default_factory=...)` — follow same pattern for `ParallelResult`
- **Test pattern** (`test_fsm_executor.py:3480-3492`): sub-loop tests write child YAML to `tmp_path / ".loops"` and pass `loops_dir=loops_dir` to `FSMExecutor`; parallel runner tests should mock `FSMExecutor.run()` directly to avoid full execution overhead
- **`worktree_utils.py` correct path**: the module lives at `scripts/little_loops/worktree_utils.py`, NOT `scripts/little_loops/parallel/worktree_utils.py`. Import as `from little_loops.worktree_utils import setup_worktree, cleanup_worktree`. The `parallel/` directory contains `git_lock.py`, `merge_coordinator.py`, `worker_pool.py` — but NOT `worktree_utils.py`
- **Standalone worktree pattern** (`cli/loop/run.py:201-240`): the simplest per-item worktree lifecycle in the codebase; uses `GitLock(logger)` directly, calls `setup_worktree(repo_path, worktree_path, branch_name, copy_files, logger, git_lock)`, registers cleanup via `atexit.register` (cleanup closure at `run.py:231-240`). Branch name pattern at `run.py:211-213`: `_safe_name = re.sub(r"[^a-zA-Z0-9-]", "-", loop_name); _branch_name = f"{_timestamp}-{_safe_name}"`. _Line range corrected 2026-04-20 (drifted from 171-215; lines 171-198 are scope-lock / queue-wait logic, not worktree setup)._ For `ParallelRunner` worktree mode, adapt this pattern per-item with `try/finally` (not `atexit`) for proper cleanup under concurrent execution

### Additional Findings (2026-04-20 refine pass)

_Added by `/ll:refine-issue` — new findings beyond prior refinement:_

- **`_sub_event_callback` wrapper — actual code** (`executor.py:393-409`): the depth-injecting wrapper referenced earlier is a closure that preserves deeper-nested depth when already set:
  ```python
  depth = self._depth + 1

  def _sub_event_callback(event: dict) -> None:
      if "depth" not in event:
          self.event_callback({**event, "depth": depth})
      else:
          self.event_callback(event)
  ```
  The scope boundary for FEAT-1075 is literal: `child_executor = FSMExecutor(..., event_callback=self.event_callback, ...)` — no wrapper, no depth injection. ENH-1177 adds the tagging wrapper around `self.event_callback` at the callsite. If `_execute_parallel_state()` (FEAT-1076) needs depth propagation it can add a `_sub_event_callback`-style wrapper following this pattern — but FEAT-1075 itself does NOT wrap.
- **No production `Future.cancel()` precedent exists in the codebase** — grep confirms only one occurrence, in `test_worker_pool.py:537-546`, where `Future.cancel()` + manual `_state = "CANCELLED"` force-populates a test fixture. `fail_fast` cancellation in this module is net-new code with no prior pattern to mirror. Implement using the documented Python API: collect submitted futures in a list, call `future.cancel()` on the unstarted ones after first failure observed in `as_completed()`. Note that `as_completed()` will still yield already-running futures; handle both cases.
- **Per-worker timeout precedent** (`parallel/orchestrator.py:796`): `result = future.result(timeout=self.parallel_config.timeout_per_issue)` — exactly the pattern to reuse for `ParallelStateConfig.timeout_seconds`. Wrap the call to catch `concurrent.futures.TimeoutError` (NOT the built-in `TimeoutError`; they are distinct classes pre-3.11) and classify as `ParallelItemError(kind="timeout", exc_type="TimeoutError", ...)`.
- **No existing `copy.deepcopy` usage anywhere in `scripts/`** — grep confirms this module introduces the first deep-copy-for-isolation pattern to the codebase. There is no existing utility to extend. Use `import copy; copy.deepcopy(parent_context)` directly. The standard library is sufficient; no custom pickling needed because captured values are primitives and small containers (the context model is strict about what can be stored).
- **Branch-name sanitization choice for worktree mode** — two precedents exist, pick `run.py`'s pattern:
  - `cli/loop/run.py:211` uses inline `re.sub(r"[^a-zA-Z0-9-]", "-", loop_name)` (no lowercasing, no shared utility)
  - `parallel/worker_pool.py:240-245` uses `slugify()` from `issue_parser.py:99-110` (lowercases, collapses runs). This is ll-parallel-specific and loops should not take an `issue_parser` dependency.
  - **Use the `run.py` pattern** since `ParallelRunner` is a loop feature; per-worker branch naming: `f"{timestamp}-{safe_loop_name}-{item_index}"` keeps the worktree lifecycle consistent with existing loop worktrees.
- **Worktree cleanup pattern departure from codebase precedent** — every worktree cleanup in the codebase today uses `atexit.register` (`cli/loop/run.py:231-240`, `lifecycle.py:209`). `try/finally` per worker is intentional departure (rationale: `atexit` fires at process end; under concurrent fan-out, workers must release their worktree the moment they complete or worktrees leak if fan-out is long-running). Flag in the module docstring so future readers understand the rationale.

## Impact

- **Priority**: P2 — Required dependency for FEAT-1076 (executor dispatch); blocks parallel FSM end-to-end delivery
- **Effort**: Medium — New module ~150 lines; follows existing `ThreadPoolExecutor` + `as_completed` pattern
- **Risk**: Low — Self-contained new module; no changes to existing code paths
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `executor`

---

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-04-20_ (original: 2026-04-12)

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 76/100 → MODERATE (was 72 on 2026-04-20)

### Concerns
- **FEAT-1074 still open** (re-verified 2026-04-20): `ParallelStateConfig` is absent from `schema.py`. Hard blocker — the runner cannot compile without it. FEAT-1074 has confidence_score 90 and is the logical next implementation target. Do not begin FEAT-1075 until FEAT-1074 is merged.

_Resolved since 2026-04-20: Worktree merge approach decided (direct `git_lock.run(["merge", "--no-ff", branch_name], cwd=repo_path)` — MergeCoordinator incompatible and not bridgeable without IssueInfo coupling). All other design decisions finalized by 2026-04-21 refine pass: deepcopy per worker (no shared utility needed), `concurrent.futures.TimeoutError` (not built-in TimeoutError), Future.cancel() approach, try/finally cleanup (not atexit), branch naming follows run.py pattern._

_Resolved since 2026-04-12: Test gap (tests moved into this issue from FEAT-1077). Import paths verified (`resolve_loop_path` from `little_loops.cli.loop._helpers`; `load_and_validate` from `little_loops.fsm.validation`)._

## Session Log
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5bfc13ef-4b6a-4f7b-b596-5015f6c01579.jsonl`
- `/ll:refine-issue` - 2026-04-21T01:37:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/168a576e-aa89-4e22-8dcf-751545bca22f.jsonl`
- `/ll:confidence-check` - 2026-04-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27bf787d-bd3b-4f68-b9eb-6aa8cbacf2cc.jsonl`
- `/ll:wire-issue` - 2026-04-21T01:31:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/50c8a9ee-e61b-4ea8-bc4a-5270b48faf0b.jsonl`
- `/ll:refine-issue` - 2026-04-21T01:21:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1ccb99a2-08c0-45c2-9034-21590b69788e.jsonl`
- `/ll:refine-issue` - 2026-04-12T21:44:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ba00a202-7579-41c1-8d16-ccc842c9ed69.jsonl`
- `/ll:confidence-check` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/76789ff6-088d-4a98-b81f-58898ce4522f.jsonl`
- `/ll:wire-issue` - 2026-04-12T21:38:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a7762782-0f79-4152-a3a2-b2f202799611.jsonl`
- `/ll:refine-issue` - 2026-04-12T21:32:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/34932e3c-e378-4fd7-9886-68460b918395.jsonl`
- `/ll:format-issue` - 2026-04-12T21:28:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/80e2b48b-2183-43e6-9b2d-906181c202b3.jsonl`
- `/ll:issue-size-review` - 2026-04-12T21:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8e4e49c-4e79-4270-9839-915fa38b03f2.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P2
