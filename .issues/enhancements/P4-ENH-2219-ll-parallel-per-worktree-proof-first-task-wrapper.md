---
id: ENH-2219
title: ll-parallel per-worktree proof-first-task wrapper for issues with learning_tests_required
type: enhancement
priority: P4
status: done
parent: EPIC-2207
blocked_by: ENH-2208
captured_at: '2026-06-18T15:38:06Z'
completed_at: '2026-06-19T02:34:57Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 82
score_complexity: 17
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 23
decision_needed: false
---

# ENH-2219: ll-parallel per-worktree proof-first-task wrapper for issues with learning_tests_required

## Summary

`ll-parallel` dispatches issues to isolated git worktrees for concurrent implementation but doesn't wrap those invocations with `proof-first-task`. For issues that declare `learning_tests_required`, inject a `proof-first-task` loop call as the first step in the worktree's claude invocation, so assumption-firewall runs per-worktree before implementation begins.

## Current Behavior

`ll-parallel` dispatches issues to isolated git worktrees via `WorkerPool._process_issue()` in `scripts/little_loops/parallel/worker_pool.py`. Each worker runs a fixed five-step sequence: worktree setup → `ready-issue` validation → optional `decide-issue` → `manage-issue` implementation → work verification. There is no step in this sequence that reads `issue.learning_tests_required` (the `IssueInfo` field populated at `issue_parser.py:271`) or invokes `proof-first-task` before implementation.

ENH-2210 gates the sprint-level pre-flight for `ll-sprint` via `_run_learning_gate_preflight()` in `cli/sprint/run.py:164`, but this runs once at orchestrator level before any worktree is created. `ll-parallel` is a separate code path that entirely bypasses learning test gating.

## Expected Behavior

When `WorkerPool._process_issue()` processes an issue, it should check whether `issue.learning_tests_required` is non-`None`. If so and `config.learning_tests.enabled` is `True`, it should run a per-worktree gate before the `IMPLEMENTING` stage:

```
ll-loop run proof-first-task --context issue_file=<issue.path>
```

If the gate result is `blocked`, the worktree should skip the manage-issue invocation and log the skip. If the result is `done`, implementation proceeds normally.

**Critical design point**: `ll-loop run proof-first-task` exits 0 for ALL terminal states (`done`, `blocked`, `impl_failed`) — `terminated_by="terminal"` maps to exit code 0 in `EXIT_CODES` in `fsm/_helpers.py`. The `blocked` vs `done` distinction is only accessible via `ExecutionResult.final_state` (Python API) or by parsing stdout. This drives the implementation decision below.

## Motivation

ENH-2210 gates the sprint-level pre-flight for `ll-sprint`. `ll-parallel` is a separate path that also bypasses learning test gating. The per-worktree wrapper is the right granularity: it's more precise than a batch pre-flight because it only invokes assumption-firewall for the specific issue being worked on in that worktree.

## Design Decision (Required Before Implementation)

Two viable approaches for detecting `blocked` vs `done`:

**Option A — Python API (recommended)**: Inside `WorkerPool._process_issue()`, call `run_foreground(loop_def, ctx)` from `scripts/little_loops/fsm/_helpers.py` directly and check `result.final_state == "blocked"`. Avoids subprocess, reliable, stays in-process. Requires loading the `proof-first-task.yaml` loop definition.

**Option B — Subprocess + stdout parse**: Call `subprocess.run(["ll-loop", "run", "proof-first-task", "--context", f"issue_file={issue.path}"], cwd=worktree_path)` and parse stdout for the final state name. Consistent with `_run_learning_gate_preflight()` in sprint (which uses `subprocess.run`), but requires a stable output format contract for `final_state`.

> **Selected:** Option B — Subprocess + stdout parse — consistent with the sprint reference implementation; thread-safe for worker threads; directly reusable test mock pattern; avoids unsafe in-process FSM execution from a ThreadPoolExecutor context.

Run `/ll:decide-issue ENH-2219` to select the approach before wiring.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-18.

**Selected**: Option B — Subprocess + stdout parse

**Reasoning**: `run_foreground()` (Option A) returns `int`, not `ExecutionResult`, making the described `result.final_state == "blocked"` check impossible without building a full `PersistentExecutor` pipeline (~120 lines of setup) plus unsafe global `sys.stdout` mutations from a `ThreadPoolExecutor` worker thread. The only existing cross-subsystem loop invocation in the codebase (`_run_learning_gate_preflight()` in `cli/sprint/run.py`) uses `subprocess.run(["ll-loop", "run", ...])` — Option B's exact shape. The `blocked` vs `done` exit-code disambiguation is solved by reading the persisted events JSONL from `run_dir` rather than stdout parsing.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Python API | 0/3 | 0/3 | 1/3 | 0/3 | 1/12 |
| Option B — Subprocess | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |

**Key evidence**:
- Option A: `run_foreground()` is in `cli/loop/_helpers.py` (not `fsm/_helpers.py` as described); returns `int` exit code, not `ExecutionResult`; installs SIGWINCH handlers and mutates `sys.stdout` globally — unsafe from a `ThreadPoolExecutor` worker thread; `parallel/` has zero FSM imports (reuse score 1/3).
- Option B: `_run_learning_gate_preflight()` in `cli/sprint/run.py:164` is the direct template; `TestRunLearningGatePreflight` in `test_sprint_integration.py:1938` provides a directly reusable test mock pattern; `cwd=worktree_path` provides proper isolation per worktree; exit-code disambiguation solved by reading `run_dir/*.events.jsonl` for `final_state` (reuse score 2/3).

## Implementation Steps

1. **Wire `--skip-learning-gate` into `cli/parallel.py`**: In `main_parallel()` (at line ~67 where args are registered), add:
   ```python
   from little_loops.cli_args import add_skip_learning_gate_arg
   add_skip_learning_gate_arg(parser)
   ```
   `add_skip_learning_gate_arg()` already exists at `cli_args.py:214` — identical to sprint's wiring in `cli/sprint/__init__.py:137`.

2. **Inject gate check in `worker_pool.py:_process_issue()`**: Between the VALIDATING stage (ready-issue, line ~385) and the IMPLEMENTING stage (manage-issue, line ~396), add:
   - Check `issue.learning_tests_required is not None` and `config.learning_tests.enabled`
   - Check `not getattr(args, "skip_learning_gate", False)`
   - If gating applies, invoke gate per chosen option (A or B above)
   - If result is `blocked`, log skip and return a failed `WorkerResult` before reaching manage-issue

3. **Optional `WorkerStage` addition**: Add `PROVING = "proving"` to `WorkerStage` enum in `types.py:170` for progress tracking. Fits between `VALIDATING` and `IMPLEMENTING`.

4. **Tests in `test_worker_pool.py`**: Following `TestSprintPreflightGate` in `test_sprint_integration.py:1932`, add:
   - `TestPerWorktreeProofFirstGate.test_gate_skipped_when_lt_disabled`
   - `TestPerWorktreeProofFirstGate.test_gate_skipped_when_no_learning_tests_required`
   - `TestPerWorktreeProofFirstGate.test_blocked_result_skips_manage_issue`
   - `TestPerWorktreeProofFirstGate.test_skip_learning_gate_flag_bypasses_gate`
   - Use `_make_issue_info()` helper pattern from `test_sprint_integration.py:1911`

5. **Update CLI docs**: Add `--skip-learning-gate` flag to `docs/reference/CLI.md` under `ll-parallel`.

## Acceptance Signals

- A worktree for an issue with `learning_tests_required: [httpx]` runs assumption-firewall before the implementation prompt
- If assumption-firewall blocks, the worktree exits cleanly without starting the implementation
- Parallel execution of multiple worktrees is unaffected: each worktree's gate is independent
- `--skip-learning-gate` bypasses all per-worktree gating

## Scope Boundaries

- **In scope**: Modifying `worker_pool.py:_process_issue()` to detect `learning_tests_required` and invoke `proof-first-task`; wiring `--skip-learning-gate` into `cli/parallel.py`; optional `WorkerStage.PROVING`; tests in `test_worker_pool.py`; docs update in `docs/reference/CLI.md`
- **Out of scope**: Changes to the `proof-first-task` loop itself (`loops/proof-first-task.yaml`); batch pre-flight for learning tests in `ll-sprint` (covered by ENH-2210); other types of per-worktree gating beyond learning tests

## API/Interface

`ll-parallel` CLI:

```
ll-parallel [--skip-learning-gate]
```

- `--skip-learning-gate` — Bypass per-worktree learning test gating for emergency runs (same flag name as `ll-sprint`)

## Consolidation Note

**Note** (added by EPIC-2207 scoping review): Per-worktree gating shares code with ENH-2210's sprint-level pre-flight. Both must call the shared utility at `scripts/little_loops/learning_tests/gate.py` (`is_record_stale()`) rather than implementing independent gating logic. `gate.py` exists and is the ENH-2208 deliverable.

When implementing this issue:
1. The shared utility (`gate.py`) is already built by ENH-2208 (the `blocked_by` dependency).
2. This issue calls the utility per-worktree rather than reimplementing the gate check.
3. The `--skip-learning-gate` flag at the `ll-parallel` CLI level bypasses the per-worktree call.

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/worker_pool.py` — `WorkerPool._process_issue()`: inject gate check between VALIDATING (line ~385) and IMPLEMENTING (line ~396) stages
- `scripts/little_loops/cli/parallel.py` — `main_parallel()`: wire `add_skip_learning_gate_arg(parser)` (~line 67)
- `scripts/little_loops/parallel/types.py` — optional: add `PROVING = "proving"` to `WorkerStage` enum (line 170) for stage tracking

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/orchestrator.py` — `ParallelOrchestrator.run()` dispatches to `WorkerPool.submit()`; no changes needed but must remain compatible
- `scripts/little_loops/cli_args.py:214` — `add_skip_learning_gate_arg()` already defined; no changes needed

### Similar Patterns (Reference Implementations)
- `scripts/little_loops/cli/sprint/run.py:164` — `_run_learning_gate_preflight()`: sprint-level pattern for subprocess invocation and `learning_tests.enabled` / `skip_learning_gate` guard
- `scripts/little_loops/parallel/worker_pool.py:385` — `decision_needed` gate: per-issue conditional wrapper pattern to model after
- `scripts/little_loops/cli/sprint/__init__.py:137` — `add_skip_learning_gate_arg(run_parser)` wiring pattern

### Loop Being Invoked
- `scripts/little_loops/loops/proof-first-task.yaml` — `check_issue_file → gate → run_impl` FSM; requires `issue_file` context parameter; all terminal states (`done`, `blocked`, `impl_failed`) exit 0

### Shared Utilities
- `scripts/little_loops/learning_tests/gate.py` — `is_record_stale()` (ENH-2208 deliverable; already exists)
- `scripts/little_loops/learning_tests/__init__.py` — `check_learning_test()`, `LearnTestRecord`
- `scripts/little_loops/issue_parser.py:271` — `IssueInfo.learning_tests_required: list[str] | None` field
- `scripts/little_loops/fsm/_helpers.py` — `run_foreground()`, `ExecutionResult.final_state` (Option A only)

### Tests
- `scripts/tests/test_worker_pool.py` — extend with `TestPerWorktreeProofFirstGate` class (NOT `test_parallel.py` — that file does not exist)
- `scripts/tests/test_sprint_integration.py:1911` — `_make_issue_info()` helper and `TestSprintPreflightGate` pattern to copy
- `scripts/tests/test_parallel_types.py` — existing types tests (no changes needed)

### Documentation
- `docs/reference/CLI.md` — add `--skip-learning-gate` to `ll-parallel` reference (NOT `scripts/little_loops/cli/parallel.md` — that file does not exist)

### Configuration
- `config-schema.json` — `learning_tests.enabled` (boolean, default false); drives the master gate guard

## Impact

- **Priority**: P4 — Low priority; enhancement to existing parallel execution, not a correctness fix
- **Effort**: Medium — touches `WorkerPool._process_issue()`, adds conditional logic and a new CLI flag
- **Risk**: Low — wraps existing behavior conditionally; `--skip-learning-gate` provides emergency bypass
- **Breaking Change**: No — new optional behavior behind `learning_tests_required` frontmatter check

## Success Metrics

- Issues with `learning_tests_required` in frontmatter get assumption-firewall before per-worktree implementation
- Worktrees blocked by `proof-first-task` exit cleanly without starting implementation
- `--skip-learning-gate` flag correctly bypasses all per-worktree gating
- Parallel execution throughput is unaffected when no issues have `learning_tests_required`

## Labels

`enhancement`, `learning-tests`, `ll-parallel`, `captured`

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): ENH-2219 invokes `ll-loop run proof-first-task` which routes through `fsm/executor.py`'s `_execute_learning_state`. That function calls `check_learning_test()` directly; ENH-2208 (`blocked_by` dependency, now done) adds `is_record_stale()` to this path so date-stale proven records don't silently pass. ENH-2219 must not ship without ENH-2208's fix in place — which is satisfied by the `blocked_by: ENH-2208` declaration.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-18_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 77/100 → MODERATE

### Concerns (corrected by `/ll:refine-issue`)
- **Exit code semantics incorrect**: Original issue claimed `proof-first-task` exits 1 for `blocked`. All terminal states exit 0. Blocking detection requires Python API (`ExecutionResult.final_state`) or stdout parsing — see Design Decision section.
- **Wrong injection site named**: `cli/parallel.py` is only for arg wiring; actual gate injection is `worker_pool.py:_process_issue()`.
- **`parallel.md` does not exist**: Removed from integration map; replaced with `docs/reference/CLI.md`.
- **No `test_parallel.py` exists**: Replaced with `test_worker_pool.py` in integration map.
- **`fsm/executor.py` staleness**: Satisfied by `blocked_by: ENH-2208` (done); no separate action needed.

## Session Log
- `/ll:manage-issue` - 2026-06-19T02:34:57Z - `<current-session>`
- `/ll:ready-issue` - 2026-06-19T02:03:59 - `60457264-5ec2-4230-b561-cf8c29df6a10.jsonl`
- `/ll:confidence-check` - 2026-06-18T00:00:00Z - `165628c5-4270-4773-8690-7baa05dcfb1d.jsonl`
- `/ll:decide-issue` - 2026-06-19T01:56:26 - `dfa69e88-722f-4858-acae-90ce2a2e6658.jsonl`
- `/ll:refine-issue` - 2026-06-19T01:48:25 - `1b0c2555-dfdc-41d4-b85d-426505c29406.jsonl`
- `/ll:refine-issue` - 2026-06-18T00:00:00 - `<current-session>`
- `/ll:audit-issue-conflicts` - 2026-06-18T21:17:06 - `23eb26e5-163c-41e9-bc83-173b75524706.jsonl`
- `/ll:format-issue` - 2026-06-18T19:33:16 - `4072b9ee-5401-460f-9774-32c1e434c36f.jsonl`
- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`
- `/ll:confidence-check` - 2026-06-18T00:00:00Z - `047f7fe1-cbcf-417c-a6be-6362c9a7900e.jsonl`

## Status

**Open** | Created: 2026-06-18 | Priority: P4
