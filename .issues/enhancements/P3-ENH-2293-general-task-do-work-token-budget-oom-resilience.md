---
id: ENH-2293
title: "general-task do_work \u2014 token-budget / OOM resilience (pre-work context\
  \ guard)"
type: ENH
priority: P3
status: open
captured_at: '2026-06-25T15:24:25Z'
discovered_date: 2026-06-25
discovered_by: capture-issue
labels:
- loops
- general-task
- fsm
- resilience
relates_to:
- ENH-2246
- ENH-1732
decision_needed: false
confidence_score: 96
outcome_confidence: 91
score_complexity: 21
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 23
---

# ENH-2293: general-task do_work — token-budget / OOM resilience

## Summary

The `general-task` loop's `do_work` state (`scripts/little_loops/loops/general-task.yaml`)
runs an unbounded `prompt` action per step. When a step's prompt context balloons
(observed: ~46k input + ~138k cache-read tokens in a single `do_work` action), the
worker process can be **OOM/SIGKILL-killed mid-action (exit -9)**. A SIGKILL bypasses
the FSM's `on_error: do_work` retry and `on_retry_exhausted: capture_work_exit`
handlers entirely — the runner treats it as a hard termination, so the loop never
reaches a terminal state.

This is a **task-scoping / resource-resilience** concern, NOT an FSM routing defect.
The resume machinery (`resume_check`) already handles the post-kill state correctly:
on re-run it finds a checkpoint with no usable `last-files.txt`, falls through to
`RESUME_CLEAN`, and cleanly re-selects the interrupted step.

## Context

Source: `audit-general-task-whitepaper-2026-06-25.md` — run
`2026-06-25T150728-general-task` ("Implement the plan in
whitepaper-automation-sliding-window.md"). `do_work` for Step 1 was killed by
SIGKILL (exit -9) at ~190s, well within the 900s `timeout`, so timeout was not the
cause. The audit's other proposals (diagnose SIGKILL source, split the task into
sub-tasks, verify the urlencode change) are run-specific operational advice and were
deliberately NOT encoded into the FSM — only this resource-resilience item has
recurring signal.

## Current Behavior

`do_work` (general-task.yaml) uses `${context.input}` + the current step as a
`prompt` action with `timeout: 900`, `on_error: do_work`, `max_retries: 2`,
`on_retry_exhausted: capture_work_exit`. There is no guard on the *size* of the
context handed to the worker. An OOM kill (exit -9) is not catchable by any of these
handlers; the loop dies without summarize_partial or diagnose running.

This is distinct from ENH-2246 (which splits a step on wall-clock **timeout** exit
124) and ENH-1732 (which split `execute` into granular states to cap per-action
**duration**). Neither addresses memory/token-budget exhaustion (exit -9).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **CORRECTION — exit -9 is NOT fully bypassed by all handlers**: The negative-exit-code guard in `FSMExecutor._execute_state()` (`scripts/little_loops/fsm/executor.py:1018`) checks `result.exit_code < 0` and routes to `state.on_error`. For `do_work`, that means re-entering `do_work`. After `max_retries: 2` (3 total executions), it exhausts to `on_retry_exhausted: capture_work_exit` → `continue_work`. The runner process survives because `subprocess_utils.py:run_claude_command()` spawns the child with `start_new_session=True`, isolating the child's process session from the Python runner.
- **Actual gap — `continue_work` has no OOM branch**: `continue_work`'s prompt action explicitly branches on exit code 124 (step split) but has no branch for exit -9. An OOM-killed step falls through to the DoD-remediation path, which is incorrect behavior — it treats a resource kill like a verify failure rather than an OOM signal, producing a misleading remediation step.
- **Wasted retries**: 3 consecutive OOM attempts (same oversized context each time) burn ~570s (~190s × 3) before exhaustion — an argument for `retryable_exit_codes` filtering or a pre-work context guard to avoid burning all retries.
- **`summarize_partial` / `diagnose` are not bypassed**: after `capture_work_exit` → `continue_work` → exhaustion, `diagnose` is reachable via `continue_work.on_retry_exhausted: diagnose`. The silent-exit-with-no-artifact scenario only occurs if all three `do_work` retries and all three `continue_work` retries exhaust in sequence.

## Expected Behavior

`do_work` (or a pre-`do_work` state) surfaces or mitigates oversized step context
before the worker is launched, so an OOM kill is less likely — and if it still
occurs, the operator gets actionable diagnosis rather than a silent hard exit.

## Motivation

A single oversized step can kill an otherwise-healthy run with no recoverable signal
beyond a raw exit -9. Because SIGKILL skips every error handler, the loop produces no
`summary.md` / `diagnose` output, making the failure opaque to operators. Hardening
here protects every general-task run on large/context-heavy tasks.

## Cross-Loop Evidence (second data point — runner-killed case)

A second OOM-SIGKILL was observed in a *different* built-in loop, confirming this is
not general-task-specific. Run `2026-06-25T151309` of `openscad-model-generator`
(`audit-openscad-model-generator-2026-06-25T151309.md`): the `generate` prompt action
ran ~700s producing a 23.7 KB single-shot `model.scad` (with a mid-stream rewrite) and
was SIGKILL-killed (exit -9). The run ended with `terminated_by: signal` —
**the runner itself died**, not just the child.

This qualifies the "runner survives child SIGKILL" finding below. `start_new_session=True`
escapes *signal-group propagation* (Ctrl-C, `killpg`) but **not** a kernel OOM killer,
which selects victims by memory at the cgroup/system level and reaps the runner
alongside the child. So Option 3's caveat ("a true external SIGKILL may kill the runner
too; this only helps when the child is killed but the runner survives") is the operative
case here, not the optimistic one.

Two implications, both deliberately kept **out of scope** for this issue:
- The OpenSCAD `generate` state uses verdict routing (`on_yes`/`on_error`), so it never
  reaches the exit-<0 guard at `executor.py:1018` that Option 3 relies on — and it has no
  `continue_work`/checkpoint-resume equivalent. The chosen general-task fix does not
  transfer to it.
- When the runner is killed, **no in-FSM mechanism can recover** (nothing runs after the
  process dies). The only mitigations are infra-level (host memory headroom) or
  generation-level (bounding/chunking oversized single-shot prompt output) — a
  cross-cutting concern for `host_runner.py` / output-size limits, not an
  openscad-loop or general-task FSM change. Defer until the runner-killed case recurs
  with a concrete fix to attach to.

## Proposed Solution

Options to evaluate (pick the cheapest that materially reduces OOM risk; do not
over-engineer the FSM):

1. **Pre-do_work step-size advisory** — a lightweight state before `do_work` that
   warns (or splits, reusing ENH-2246's split machinery) when the selected step is
   plausibly too large for one focused session, nudging the planner toward smaller
   steps up front rather than reacting after a kill.
2. **Context-size guard** — estimate the assembled prompt/context size and, above a
   threshold, route to the existing step-split path instead of launching `do_work`.
3. **OOM-aware post-mortem** — detect exit -9 distinctly from timeout (124) and route
   to `diagnose`/`summarize_partial` with an OOM-specific message so the operator
   gets a recoverable artifact instead of a bare hard exit. (Note: a true external
   SIGKILL may kill the runner too; this only helps when the child is killed but the
   runner survives.)

> **Selected:** Option 3: OOM-aware post-mortem — minimal-invasive ~5-line prompt extension + one-line `retryable_exit_codes: [124]` filter; all patterns exist verbatim in the codebase.

Whichever path is chosen, respect the meta-loop authoring rules in `.claude/CLAUDE.md`
(general-task is `category: harness`) and validate with `ll-loop validate general-task`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Runner survives child SIGKILL (confirmed)**: `subprocess_utils.py:run_claude_command()` uses `start_new_session=True` — the child is isolated in its own process session, so a SIGKILL to the child does NOT kill the runner. The "Note: a true external SIGKILL may kill the runner too" caveat in Option 3 does **not** apply to this scenario. Option 3 is fully viable.
- **Minimum-invasive fix for Option 3**: The `continue_work` prompt already branches on exit code 124. Adding an exit -9 branch requires only a ~5-line addition to the existing prompt action text — no new FSM state, no schema change. The exit code is already available via `${captured.work_result.exit_code:default=0}`. Minimum viable: print a diagnostic message and route to `diagnose` or `summarize_partial` instead of treating exit -9 as a DoD failure.
- **`retryable_exit_codes` for retry filtering**: The FSM schema supports `retryable_exit_codes: [124]` (used in `scripts/little_loops/loops/rlhf-svg-generate.yaml:plan_animation`). This field limits which exit codes re-enter via `on_error` vs. falling through to the negative-exit-code guard immediately. Adding `retryable_exit_codes: [124]` to `do_work` would mean exit -9 skips retries and goes directly to `capture_work_exit` on the first OOM kill, saving ~380s of wasted retries.
- **Cheapest option is likely Option 3 + `retryable_exit_codes` filter**: Extend `continue_work` prompt with an exit -9 branch (OOM-specific message + route to `diagnose`) and add `retryable_exit_codes: [124]` to `do_work` to avoid 3× OOM retry waste. A pre-work context-size guard (Options 1/2) requires a new shell state and context estimation logic — more invasive for marginal additional gain.
- **Guard state pattern (if implementing Option 1/2)**: Follow `scripts/little_loops/loops/oracles/plan-research-iteration.yaml:check_research` — a pre-work shell guard using `output_contains` evaluator that routes populated-context → proceed, empty/missing → skip. Tests in `test_builtin_loops.py:TestPlanResearchIterationOracle` (~line 6450) show the canonical test shape for guard states.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-25.

**Selected**: Option 3: OOM-aware post-mortem

**Reasoning**: Option 3 requires only a ~5-line addition to the `continue_work` prompt (mirroring the existing exit-124 branch) and a one-line `retryable_exit_codes: [124]` addition to `do_work` — both patterns exist verbatim in this codebase (`rlhf-svg-generate.yaml:195,323` and `test_builtin_loops.py:7640–7667`). Options 1 and 2 require a new shell guard state with step-size estimation logic, but the actual OOM-causing context (138k cache-read tokens from conversation history) is assembled inside the host CLI process and is not measurable by any pre-flight shell state, making them heuristic-only with marginal protective gain over Option 3.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option 1: Pre-do_work step-size advisory | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |
| Option 2: Context-size guard | 1/3 | 0/3 | 1/3 | 2/3 | 4/12 |
| Option 3: OOM-aware post-mortem | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |

**Key evidence**:
- **Option 1**: Guard pattern shape exists (4 precedents: `check_research`, `check_research_written`, `check_baseline_tests`, `validate_input`) but step-size estimation utility is absent from shell-callable YAML context; the 138k cache tokens are invisible to any pre-flight measurement. Reuse score: 2/3.
- **Option 2**: Context-size guard infrastructure does not exist — assembled prompt size is built inside the host CLI process, inaccessible to a shell state; `continue_work` step-split path is exit-code-driven and would misroute a pre-work arrival. Reuse score: 1/3.
- **Option 3**: `continue_work` exit-124 branch is the direct template (same `${captured.work_result.exit_code:default=0}` variable, same paragraph structure); `retryable_exit_codes: [124]` confirmed in `rlhf-svg-generate.yaml:195,323`; test scaffolding maps 1:1 to `test_continue_work_prompt_detects_timeout_exit_code` (line 7640). Reuse score: 3/3.

## Implementation Steps

1. Reproduce / characterize the OOM: confirm whether exit -9 reaches the runner at
   all, or whether the runner is also killed (determines which option is viable).
2. Decide between pre-work guard (options 1/2) vs. post-mortem routing (option 3).
3. Implement in `scripts/little_loops/loops/general-task.yaml`; reuse the
   ENH-2246 step-split path where applicable rather than adding a parallel mechanism.
4. Add/extend a test in `scripts/tests/test_builtin_loops.py`.
5. `ll-loop validate general-task` + `python -m pytest scripts/tests/test_builtin_loops.py`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 finding**: Runner survives child SIGKILL (confirmed — `start_new_session=True` in `subprocess_utils.py`). The exit -9 reaches the FSM's negative-exit-code guard at `executor.py:FSMExecutor._execute_state():1018` and routes to `on_error: do_work`. Step 1 can be considered resolved; proceed to Step 2.
- **Step 3 precision (Option 3 path)**: Change is to `continue_work`'s prompt action text in `scripts/little_loops/loops/general-task.yaml`. Add an `if exit code is -9 (OOM/SIGKILL)` branch alongside the existing `if exit code is 124 (timeout)` branch. Optionally add `retryable_exit_codes: [124]` to `do_work` to skip 3× OOM retries.
- **Step 3 precision (Option 1/2 path)**: Add a new shell guard state before `do_work`. Follow the `check_research` pattern in `scripts/little_loops/loops/oracles/plan-research-iteration.yaml` for the guard state shape and `output_contains` evaluator wiring.
- **Step 4 — two test files**: Add tests to **both** `scripts/tests/test_builtin_loops.py:TestGeneralTaskLoop` (line 7536) for routing assertions AND `scripts/tests/test_general_task_loop.py` (dedicated general-task test file from ENH-1644) for prompt-content assertions. Model the new tests after `test_continue_work_prompt_detects_timeout_exit_code` (line 7640) and `test_continue_work_prompt_instructs_step_split_on_timeout` (line 7648) in `test_builtin_loops.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Add 3 new tests to `scripts/tests/test_builtin_loops.py:TestGeneralTaskLoop` (after line 7667):
   - `test_do_work_retryable_exit_codes_is_124_only` — assert `data["states"]["do_work"].get("retryable_exit_codes") == [124]`
   - `test_continue_work_prompt_detects_oom_exit_code` — assert `"-9"` or `"OOM"` or `"SIGKILL"` in `continue_work.action`
   - `test_continue_work_prompt_routes_to_diagnose_on_oom` — assert `"diagnose"` appears in the OOM branch of `continue_work.action`
7. Add 2 new tests to `scripts/tests/test_general_task_loop.py` (new class `TestENH2293OOMResilience`):
   - `test_do_work_retryable_exit_codes` — assert `raw_data["states"]["do_work"]["retryable_exit_codes"] == [124]`
   - `test_continue_work_handles_oom_exit_code` — assert OOM/SIGKILL signal text in `continue_work.action`
8. Update `docs/guides/LOOPS_REFERENCE.md` — Section "5. Continue": add exit -9 (OOM/SIGKILL) as a third case alongside exit-124 and DoD-remediation

## Scope Boundaries

- **In scope**: `general-task.yaml` FSM only — adding a pre-`do_work` guard state or OOM-aware post-mortem routing.
- **Out of scope**: Changes to the loop runner or harness infrastructure; diagnosing the root cause of the SIGKILL source (run-specific operational advice captured in the audit whitepaper, not recurring signal).
- **Out of scope**: Duplicating the ENH-2246 step-split mechanism — reuse it where applicable rather than building a parallel path.
- **Out of scope**: ENH-2246 (timeout exit 124 handling) and ENH-1732 (execute granularity) — those address different resource failure modes.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — add pre-`do_work` guard state or OOM-aware routing

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loop_runner.py` — executes general-task; source of exit -9 signal if runner survives the kill
- `scripts/little_loops/cli/loop.py` — `ll-loop run` CLI entrypoint

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/proof-first-task.yaml` — references `impl_loop: "general-task"` (line 14); no change needed but general-task's loop interface must remain stable after this fix [Agent 1 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Corrected/Additional Dependent Files:**
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._execute_state()`: the negative-exit-code guard at line 1018 is what processes exit -9 and routes it to `on_error`. More directly relevant than `loop_runner.py`.
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()`: launches child with `start_new_session=True`; runner survives child SIGKILL; returns `returncode=-9` directly via `process.returncode`.
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run()`: wraps `run_claude_command()` result into `ActionResult(exit_code=-9, ...)`; maps `subprocess.TimeoutExpired` → exit 124 (distinct path from SIGKILL).
- Note: `scripts/little_loops/cli/loop.py` does not exist as a single file — the CLI is `scripts/little_loops/cli/loop/run.py` and `scripts/little_loops/cli/loop/_helpers.py`.

**Additional Test File:**
- `scripts/tests/test_general_task_loop.py` — dedicated test file for `general-task.yaml` (Change 1–4 tests from ENH-1644); add prompt-content assertions here.

### Similar Patterns
- ENH-2246 step-split path in `general-task.yaml` — reuse `step_split` routing logic; check `scripts/little_loops/loops/general-task.yaml` for the existing split state
- `scripts/little_loops/loops/oracles/plan-research-iteration.yaml:check_research` — canonical pre-work shell guard pattern (output_contains evaluator, routes proceed vs. skip); see `TestPlanResearchIterationOracle` in `test_builtin_loops.py` (~line 6450) for guard test shape
- `scripts/little_loops/loops/rlhf-svg-generate.yaml:plan_animation` — `retryable_exit_codes: [124]` pattern for limiting which exit codes consume the retry budget

### Tests
- `scripts/tests/test_builtin_loops.py` — add/extend test for the new guard state or OOM-aware routing

_Wiring pass added by `/ll:wire-issue`:_

New tests to add in `test_builtin_loops.py:TestGeneralTaskLoop` (after line 7667, mirroring the exit-124 test shape):
- `test_do_work_retryable_exit_codes_is_124_only` — assert `data["states"]["do_work"].get("retryable_exit_codes") == [124]`
- `test_continue_work_prompt_detects_oom_exit_code` — assert `"-9"` or `"OOM"` or `"SIGKILL"` appears in `continue_work.action`
- `test_continue_work_prompt_routes_to_diagnose_on_oom` — assert `"diagnose"` appears in the OOM branch of `continue_work.action`

New tests to add in `scripts/tests/test_general_task_loop.py` (new class `TestENH2293OOMResilience`, mirroring `TestENH1732StateSplit` shape):
- `test_do_work_retryable_exit_codes` — assert `raw_data["states"]["do_work"]["retryable_exit_codes"] == [124]`
- `test_continue_work_handles_oom_exit_code` — assert OOM/SIGKILL signal text in `continue_work.action` [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — Section "5. Continue" documents exactly two exit-code cases ("exit 124" and "Other exit codes / DoD remediation"); adding an exit -9 OOM branch to `continue_work` makes this section incomplete and requires a third case [Agent 2 finding]

### Configuration
- N/A

## Impact

- **Priority**: P3 — recurring failure mode but workaround exists (manual re-run after OOM kill).
- **Effort**: Small–Medium — FSM-only change; may reuse ENH-2246 step-split path.
- **Risk**: Low–Medium — adding a state/guard to a built-in loop; covered by builtin-loops tests.
- **Breaking Change**: No
- **Scope**: `scripts/little_loops/loops/general-task.yaml` (FSM only; no runner change expected).

## Session Log
- `/ll:confidence-check` - 2026-06-25T16:30:00Z - `48eb6c56-fe87-4a7b-abd5-a2992ed6f148.jsonl`
- `/ll:wire-issue` - 2026-06-25T15:59:22 - `36c21096-cd85-469c-bcaf-ae76d9650ce1.jsonl`
- `/ll:decide-issue` - 2026-06-25T15:48:33 - `58d60d2e-2091-4283-b975-b472ea8c30c0.jsonl`
- `/ll:refine-issue` - 2026-06-25T15:38:39 - `bf3647f2-ce33-4c92-93fb-c97defad2e8b.jsonl`
- `/ll:format-issue` - 2026-06-25T15:28:02 - `1c91181a-126c-4f87-8a8f-91683ce4f565.jsonl`
- `/ll:capture-issue` - 2026-06-25T15:24:25Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5b20befe-e492-4ae3-953f-22c6539100e8.jsonl`

---

## Status

**Open** | Created: 2026-06-25 | Priority: P3
