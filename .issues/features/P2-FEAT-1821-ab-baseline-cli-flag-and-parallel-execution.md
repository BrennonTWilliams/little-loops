---
id: FEAT-1821
title: A/B Baseline CLI Flag Wiring and Parallel Execution
type: FEAT
priority: P2
status: done
parent: FEAT-1790
labels:
- feature
- loops
- harness
- ab-testing
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# FEAT-1821: A/B Baseline CLI Flag Wiring and Parallel Execution

## Summary

Add `--baseline`, `--baseline-skill`, and `--items` flags to `ll-loop run`, and implement the parallel execution infrastructure that spawns both the gated harness arm and the ungated baseline arm concurrently. Capture per-arm timing and token counts.

## Parent Issue

Decomposed from FEAT-1790: A/B Baseline Mode for `ll-loop run`

## Motivation

FEAT-1790 adds an A/B baseline-comparison mode to `ll-loop run`. This child establishes the CLI surface and the parallel execution infrastructure — the foundation that the blind evaluation and reporting child (FEAT-1822) builds on.

## Current Behavior

`ll-loop run` has no A/B baseline comparison capability. The CLI does not accept `--baseline`, `--baseline-skill`, or `--items` flags. Execution is single-arm: the FSM executor runs the gated harness path (action → eval chain → retries) with no parallel baseline arm for comparison. Per-arm timing and token counts are not tracked because there is only one execution path.

## Expected Behavior

`ll-loop run <loop> --baseline` spawns two parallel execution arms:

- **Harness arm**: Normal gated execution with eval-chain routing and retries
- **Baseline arm**: Single-shot skill invocation with no eval gates or retries

Both arms execute concurrently via `ThreadPoolExecutor`. The harness arm drives FSM routing (determines the next state); the baseline arm runs for data collection only. Per-arm `duration_ms` and `total_tokens` are captured and emitted via `baseline_complete` events. `--baseline-skill` overrides the auto-extracted baseline skill, and `--items N` limits the sample size. Flags are forwarded through `run_background()` to child processes. `PersistentExecutor` and `StateFeedRenderer` handle `baseline_complete` events for persistence and live progress display.

## Use Case

A developer modifies a loop's evaluate prompt or adjusts eval thresholds and wants to measure whether the gating logic meaningfully changes output quality compared to a bare skill invocation. They run `ll-loop run optimize-loop --baseline` and the system executes both arms in parallel — the gated harness arm (with eval checks and retries) alongside an ungated baseline arm (raw skill, no eval). Per-arm timing and token data lets the developer quantify the overhead of the eval chain versus the raw skill cost. This data feeds into FEAT-1822 for blind evaluation and reporting.

## Implementation Steps

### Phase 1: Wire `--baseline` flag

Add `--baseline`, `--baseline-skill`, and `--items` to the `run` subparser in `main_loop()` at `cli/loop/__init__.py:111-231`. Follow the existing boolean-flag pattern used for `--dry-run` / `--no-llm` / `--background` (lines 131-201). Consume the flags in `cmd_run()` at `cli/loop/run.py:88` — same pattern as `--max-iterations` (line 117) and `--context` (lines 147-151). Forward flags to background-spawned children following `run_background()` in `cli/loop/_helpers.py:1010-1055`.

### Phase 2: Parallel execute (harness arm + baseline arm)

When `--baseline` is active, modify `FSMExecutor._execute_state()` at `fsm/executor.py:772` to spawn two subprocess invocations in parallel after the action execution resolves:

- **Harness arm**: Normal gated execution — `_run_action()` (line 970) → `DefaultActionRunner.run()` (`fsm/runners.py:62`) → `run_claude_command()` (`subprocess_utils.py:221`) with streaming output and eval-chain retries.
- **Baseline arm**: Single-shot skill invocation — call `resolve_host().build_streaming()` (`host_runner.py:233`) with the bare slash command (extracted from `execute.action`), no eval gates, no retries. Run via `subprocess.Popen` with selector-based streaming (pattern at `subprocess_utils.py:277-386`).

Use the simple two-thread `concurrent.futures` pattern (not `WorkerPool` — that adds worktree isolation and process tracking that aren't needed for in-process arm spawning):

```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=2) as pool:
    harness_future = pool.submit(_run_harness_arm, action, state, ctx)
    baseline_future = pool.submit(_run_baseline_arm, action, state, ctx)
    harness_result: ActionResult = harness_future.result()
    baseline_result: ActionResult = baseline_future.result()
```

Same pattern as `test_file_utils.py:95`. The harness arm drives routing (returns `str | None` for next state); baseline result is collected for reporting only.

### Phase 4 (partial): Capture timing and tokens

- **duration_ms**: Already available via `ActionResult.duration_ms` (`fsm/types.py:71`) and `run_claude_command()` timing (`subprocess_utils.py:122`). Each arm records its own `_now_ms()` independently.
- **total_tokens**: Wire the `on_usage` callback (currently unused by `DefaultActionRunner`) from `run_claude_command()` at `subprocess_utils.py:365`. The `result` stream-json event includes `usage.input_tokens` and `usage.output_tokens` (lines 362-369). Store immediately on receipt per the completion-notification constraint.

  **Wiring path**: Add `on_usage: UsageCallback | None = None` parameter to `DefaultActionRunner.run()` at `fsm/runners.py:62`, forward it to `run_claude_command()` at line 102. Then update `FSMExecutor._run_action()` at `executor.py:1014-1022` to pass `on_usage` through to `self.action_runner.run()`. `UsageCallback = Callable[[int, int], None]` — receives `(input_tokens, output_tokens)`, where `input_tokens` already includes `cache_read_input_tokens`. Compute `total_tokens = input_tokens + output_tokens`.

### Wiring Step 8: Flag forwarding in `run_background()`

Forward `--baseline`/`--baseline-skill`/`--items` to child process args at `scripts/little_loops/cli/loop/_helpers.py:941-1074` following existing flag-forwarding pattern (lines 1010-1055); without this, background mode silently drops baseline flags.

### Wiring Step 10: `PersistentExecutor` event handling

`_handle_event()` and `_save_state()` at `scripts/little_loops/fsm/persistence.py:606-641` must handle new parallel-arm event types (`baseline_complete`) to avoid state-save failures during baseline runs.

Note: Unknown event types in `_handle_event()` are still logged to JSONL and forwarded to `EventBus` — they don't cause failures. Only `state_enter` and `loop_complete` trigger `_save_state()`. Add `baseline_complete` to the save-trigger list at line 616 if baseline results need to survive across `ll-loop resume`.

### Wiring Step 11: `StateFeedRenderer` progress display

`StateFeedRenderer.handle_event()` at `scripts/little_loops/cli/loop/_helpers.py:529` needs a `baseline_complete` branch to display per-arm timing and token counts in the live progress feed during execution.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Update `ActionRunner` Protocol at `fsm/runners.py:28-53` — add `on_usage: UsageCallback | None = None` keyword parameter to the `.run()` signature (follows `agent` and `tools` precedent at lines 37-38)
2. Update `SimulationActionRunner.run()` at `fsm/runners.py:191` — add `on_usage` parameter (may be ignored like `agent`/`tools` at line 213 with `del`); required for Protocol conformance
3. Forward `on_usage` through contributed action dispatch at `executor.py:1007-1013` — extension-contributed runners stored in `_contributed_actions` must also receive `on_usage`
4. Gate `--baseline` incompatibility with resume — `cmd_resume()` at `lifecycle.py:443` should block or warn if `--baseline` is active (similar to `cmd_run()` blocking `--worktree + --background` at `run.py:236-237`)
5. Update `MockActionRunner.run()` in `test_fsm_executor.py:43` — add `on_usage=None` parameter (231 instantiation sites)
6. Update `MockActionRunner.run()` in `test_fsm_persistence.py:610` — add `on_usage=None` parameter (38 instantiation sites)
7. Update ~18 inline mock runner classes across `test_fsm_executor.py`, `test_fsm_persistence.py`, and `test_learning_state.py` — each must accept `on_usage` keyword argument in their `.run()` signatures
8. Add `on_usage` forwarding test in `test_fsm_executor.py` `TestAgentToolsPassThrough` — extend existing `agent`/`tools` pass-through pattern
9. Add `baseline_complete` save-trigger test in `test_fsm_persistence.py` `TestPersistentExecutor` — verify `_save_state()` called
10. Add `baseline_complete` display test in `test_state_feed_renderer.py` `TestStateFeedRendererHandleEvent` — verify per-arm timing/tokens printed

### Documentation Touchpoints (tracked for FEAT-1822)

_Wiring pass noted these doc files need updating — they are in FEAT-1822 scope but listed here for cross-issue traceability:_

- `docs/reference/CLI.md:381-444` — add `--baseline`/`--baseline-skill`/`--items` to `ll-loop run` flag table
- `docs/reference/EVENT-SCHEMA.md:166-224` — add `baseline_complete` event to FSM Executor event catalog
- `docs/guides/LOOPS_GUIDE.md` — add `--baseline` usage section
- `skills/create-loop/loop-types.md:1219-1300` — disambiguation note for meta-optimize `baseline` state vs `--baseline` CLI flag
- `skills/create-loop/templates.md:124-177` — same disambiguation note

## Acceptance Criteria

- [ ] `ll-loop run <loop> --baseline` parses without error and both arms execute in parallel
- [ ] `--baseline-skill` overrides the default baseline skill extraction
- [ ] `--items N` limits sample size
- [ ] Both harness arm and baseline arm produce output streams
- [ ] Per-arm `duration_ms` captured
- [ ] Per-arm `total_tokens` captured via `on_usage` callback
- [ ] `--baseline`/`--baseline-skill`/`--items` forwarded through `run_background()` to child process
- [ ] `PersistentExecutor` handles `baseline_complete` events without state-save failures
- [ ] `StateFeedRenderer` displays baseline arm timing and token counts in live progress feed

## Impact

- **Priority**: P2
- **Effort**: Medium — CLI flag wiring, parallel subprocess execution with threading, token capture callback wiring
- **Risk**: Low — Additive feature behind opt-in `--baseline` flag; no changes to existing `ll-loop run` behavior when flag is omitted
- **Breaking Change**: No

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — argparse wiring for `--baseline` / `--baseline-skill` / `--items` flags
- `scripts/little_loops/cli/loop/run.py` — consume flags in `cmd_run()`
- `scripts/little_loops/cli/loop/_helpers.py` — flag forwarding in `run_background()` and `StateFeedRenderer.handle_event()` for baseline progress display
- `scripts/little_loops/fsm/executor.py` — parallel arm spawning in `_execute_state()`
- `scripts/little_loops/fsm/runners.py` — wire `on_usage` callback in `DefaultActionRunner.run()`; add `on_usage` to `ActionRunner` Protocol (line 28-53); add `on_usage` parameter to `SimulationActionRunner.run()` (line 191) for Protocol conformance
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor` event handling for parallel-arm event types

### Dependent Files (Callers/Importers)
- `scripts/little_loops/host_runner.py` — baseline arm uses `HostInvocation` / `build_streaming()` (line 233)
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()` token capture via `on_usage`; selector-based streaming pattern for baseline arm
- `scripts/little_loops/parallel/orchestrator.py` — `ThreadPoolExecutor` concurrency pattern to follow
- `scripts/little_loops/parallel/worker_pool.py` — `WorkerPool` uses `ThreadPoolExecutor` (line 108); already wires `on_usage` for worker path
- `scripts/little_loops/fsm/types.py` — `ActionResult.duration_ms` already available; `EventCallback` type for emitting baseline events
- `scripts/little_loops/cli/loop/_helpers.py` — `StateFeedRenderer.handle_event()` (line 529) must handle `baseline_complete` event for live progress display

### Similar Patterns
- `scripts/little_loops/cli/loop/__init__.py:131-201` — existing boolean flag wiring (`--dry-run`, `--no-llm`, `--background`)
- `scripts/little_loops/cli/parallel.py:41-152` — `ParallelOrchestrator` with `ThreadPoolExecutor`
- `scripts/little_loops/subprocess_utils.py:277-386` — selector-based streaming for baseline arm subprocess

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Token capture gap**: `run_claude_command()` in `subprocess_utils.py:365` exposes `on_usage` and `on_model_detected` callbacks that parse token counts from stream-json `result` events, but `DefaultActionRunner.run()` in `fsm/runners.py:62` does NOT wire them — it only passes `stream_callback`, `on_process_start`, and `on_process_end`. Both arms must wire `on_usage` to capture per-arm token counts.
- **`UsageCallback` signature**: `Callable[[int, int], None]` — receives `(input_tokens, output_tokens)`. `input_tokens` already includes `cache_read_input_tokens` (summed at `subprocess_utils.py:367-368`). `total_tokens` = `input_tokens + output_tokens`.
- **`DefaultActionRunner.run()` signature** (`fsm/runners.py:62`): `def run(self, action: str, timeout: int, is_slash_command: bool, on_output_line: Callable[[str], None] | None = None, agent: str | None = None, tools: list[str] | None = None) -> ActionResult`. Needs a new `on_usage: UsageCallback | None = None` parameter forwarded to `run_claude_command()`. `FSMExecutor._run_action()` (`executor.py:1014-1022`) must also pass it through.
- **`duration_ms` already available**: `ActionResult.duration_ms` (from `fsm/types.py:58`) and `ExecutionResult.duration_ms` (from `fsm/runners.py:122`) already track timing via `_now_ms()`. Each arm independently records its own `start`/`duration_ms`.
- **`cmd_run()` flag consumption pattern** (`cli/loop/run.py:88-409`): Uses `getattr(args, "flag_name", default)` throughout — no destructuring. Flags mutate `fsm` object in place (e.g., `fsm.max_iterations = args.max_iterations` at line 117). New flags follow same pattern with `getattr(args, "baseline", False)`.
- **Flag forwarding in `run_background()`** (`cli/loop/_helpers.py:997-1065`): Base command is `[sys.executable, "-m", "little_loops.cli.loop", subcommand, loop_name]`. Boolean flags: `cmd.append("--flag-name")` when truthy. Value flags: `cmd.extend(["--name", str(value)])` when non-None. All use `getattr(args, "flag_name", default)` for safe access.
- **Two-thread `ThreadPoolExecutor` pattern**: Simpler than `WorkerPool` for in-process arm spawning. Use `with ThreadPoolExecutor(max_workers=2) as pool: futures = [pool.submit(fn, arg) for arg in args]; results = [f.result() for f in futures]` — pattern used in `test_file_utils.py:95-97`. No worktree isolation, lock management, or process tracking needed.
- **`PersistentExecutor._handle_event()`** (`fsm/persistence.py:606-647`): Unknown event types are still logged to JSONL and forwarded to `EventBus` — they do NOT cause state-save failures. Only `state_enter` and `loop_complete` trigger `_save_state()`. A `baseline_complete` event would be logged but not persisted unless explicitly added to the save-trigger list at line 616.
- **`StateFeedRenderer.handle_event()`** (`cli/loop/_helpers.py:529`): The live progress display needs a `baseline_complete` branch to show per-arm results during execution — this is NOT covered by `PersistentExecutor` event handling alone.
- **`_execute_state()` return type** (`fsm/executor.py:772`): Returns `str | None` (the next state name). When spawning two arms in parallel, the harness arm's result drives routing; the baseline arm runs concurrently for data collection only.
- **Stream-json `result` event shape**: `{"type": "result", "usage": {"input_tokens": N, "output_tokens": N, "cache_read_input_tokens": N}}`. The `result` event fires exactly once per Claude invocation — token capture is a one-shot callback, not cumulative.

### Tests

#### New Tests to Write
- `scripts/tests/test_ll_loop_parsing.py` — `TestLoopArgumentParsing`: add `test_baseline_flag_parsed`, `test_baseline_default_false`, `test_baseline_skill_flag`, `test_items_flag` (note: actual file is `test_ll_loop_parsing.py`, not `test_ll_loop.py`)
- `scripts/tests/test_cli_loop_background.py` — `TestRunBackground`: add `test_forwards_baseline`, `test_forwards_baseline_skill`, `test_forwards_items`, `test_baseline_not_forwarded_when_false`
- `scripts/tests/test_ll_loop_execution.py` — parallel execution tests: mock host runner to verify both arms spawn, per-arm duration and tokens captured
- `scripts/tests/test_fsm_executor.py` — extend `TestAgentToolsPassThrough` (line 4703) with `on_usage` forwarding test (same pattern as existing `agent`/`tools` pass-through tests)
- `scripts/tests/test_state_feed_renderer.py` — `TestStateFeedRendererHandleEvent`: add `baseline_complete` event test (follow `test_action_complete_shows_duration` pattern at line 125)
- `scripts/tests/test_fsm_persistence.py` — `TestPersistentExecutor`: verify `_save_state()` triggered for `baseline_complete` events

#### Existing Tests That Will Break (Signature Change)

_Wiring pass added by `/ll:wire-issue`: adding `on_usage` to `ActionRunner.run()` signature breaks mock runner `.run()` calls in tests — every mock must accept the new parameter:_

- `scripts/tests/test_fsm_executor.py` — `MockActionRunner.run()` (line 43, 231 uses): add `on_usage=None`; 12 inline runner classes (`RaisingRunner` line 2691, `FailingRunner` line 1924, `ShutdownAfterFirstActionRunner` line 2431, `CaptureAndShutdownRunner` line 2514, `TimeoutCapturingRunner` line 3951, `ProgressRunner` line 6630, `CapturingRunner` lines 4710/4748, etc.)
- `scripts/tests/test_fsm_persistence.py` — `MockActionRunner.run()` (line 610, 38 uses): add `on_usage=None`; 5 inline runners (`CaptureAndShutdownRunner` line 1914, `ShutdownAfterFirstRunner` line 1973, `ProgressTrackingRunner` line 2057, `_AlwaysOkRunner` line 2230, `_OkRunner` line 2289)
- `scripts/tests/test_learning_state.py` — `_MockRunner.run()` (line 31): add `on_usage=None`

#### Test Patterns to Follow
- Mock host runner pattern at `test_subprocess_mocks.py:28`
- CLI entry test pattern at `test_ll_loop_errors.py:98`
- Bool flag forwarding test pattern at `test_cli_loop_background.py` (`test_forwards_no_llm`)
- Value flag forwarding test pattern at `test_cli_loop_background.py` (`test_forwards_handoff_threshold`, line 404)

## Out of Scope

- Blind evaluation of arm outputs (FEAT-1822)
- A/B aggregation, ab.json writing, terminal summary (FEAT-1822)
- Documentation updates (FEAT-1822)

## Session Log
- `/ll:ready-issue` - 2026-05-31T04:04:43 - `a2c0b1b1-7043-4750-bbb0-196b75de50e7.jsonl`
- `/ll:wire-issue` - 2026-05-31T03:59:16 - `f0a36fc6-c399-49cb-b38e-dd741555ad08.jsonl`
- `/ll:refine-issue` - 2026-05-31T03:52:08 - `fde387ed-4d7c-4ef0-8836-2a5a3430dc78.jsonl`
- `/ll:issue-size-review` - 2026-05-30T23:00:00Z - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:confidence-check` - 2026-05-31T04:00:00Z - `56585d9e-8e09-4953-a428-4cf755864d91.jsonl`
