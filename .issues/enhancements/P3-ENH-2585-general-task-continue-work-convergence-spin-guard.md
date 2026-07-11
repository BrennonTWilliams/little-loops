---
id: ENH-2585
title: general-task — guard the continue_work convergence spin after abandoned steps
type: ENH
priority: P3
status: open
discovered_date: "2026-07-10"
discovered_by: audit-loop-run
labels: [loops, fsm, general-task, stall-detection, audit]
relates_to:
- FEAT-1637
- BUG-1674
- ENH-2583
decision_needed: false
---

# ENH-2585: general-task — guard the continue_work convergence spin after abandoned steps

## Summary

Audit `general-task-audit-2026-07-09T232714.md` (03:41–03:55 UTC window): the
loop cycled `continue_work → select_step → check_done → count_done(on_no) →
continue_work` ~6 consecutive times with **zero `do_work`** in between.
`select_step` returned `NO_UNCHECKED_STEPS` in ~20ms each pass (plan steps
19–23 had all hit `max_step_attempts: 3` and were abandoned), yet each
`continue_work` burned 50–210s of LLM time re-deliberating without producing a
new actionable `- [ ]` step, until it finally self-assessed `WORK_COMPLETE`
with 12 hard criteria still open and handed off to `final_verify`.

## Why the existing stall detector doesn't catch this

FEAT-1637's `StallDetector` (and the BUG-1674 fix) treat auxiliary file
mutations between visits as progress. In this spin, `check_done` rewrites the
`## Sample Verification` section of `dod.md` every cycle, so each pass mutates
a file and the detector sees "slow but real progress." The spin is invisible
at the executor layer; the guard has to be loop-local (or the detector must
learn to exclude the loop's own bookkeeping artifacts, mirroring the
`repeated_failure.exclude_paths` mechanism this loop already configures for
`plan.md`/`dod.md`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **StallDetector class** lives at `scripts/little_loops/fsm/stall_detector.py:27-77`. Tracks consecutive `(state, exit_code, verdict)` triples in a `deque(maxlen=window)`; `check()` returns `Stall(triple, count)` when the deque is full and every entry identical. Fingerprint-driven reset was added by BUG-1674 at lines 42-61.
- **The exact gap that lets this spin pass** is in `scripts/little_loops/fsm/executor.py:996-1035` (`_compute_progress_fingerprint`). When `circuit.repeated_failure.progress_paths` is empty, the function returns `None` early at line 1011 — before `exclude_paths` is consulted at lines 1014-1019. Net: `exclude_paths` alone is inert. This loop declares only `exclude_paths` (`scripts/little_loops/loops/general-task.yaml:24-30`: `window: 7`, `on_repeated_failure: diagnose`, `exclude_paths: [plan.md, dod.md]`), so the fingerprint is always `None` and the deque never resets.
- **Why `count_done` is the eval-bearing state** here, not `continue_work`: `count_done` (`general-task.yaml:344-425`) is the state whose verdict (`output_json` on `.total`) repeats as `no` across the spin. The detector deque would fill at `window: 7` per `general-task.yaml:26`, but with `None` fingerprint, `StallDetector.record` (`stall_detector.py:56-60`) takes the no-op path.
- **`check_done`'s bookkeeping write** that defeats the detector: `general-task.yaml:287-342`, Step 3 ("Sample re-verification", lines 323-337) rewrites the `## Sample Verification` section of `dod.md` every cycle (`general-task.yaml:326-328`).
- **Earlier precedent** — BUG-1767 (`scripts/little_loops/fsm/validation.py:2370-2400`) introduced `_validate_progress_paths_isolation`, which already warns when a state action writes to a file in `progress_paths` but not `exclude_paths`. The validation rule is a strong signal that the schema authors considered "exclude-only" ambiguous; Option 2 below should resolve that ambiguity explicitly.
- **`diagnose` is currently the stall target** (`general-task.yaml:692-703`, terminal: `failed`). For this spin, the right target is **not** `diagnose` (which discards verified progress); it is the **ENH-2583 partial-credit chain** — see "Proposed Solution" below.

## Expected Behavior (design open — two candidate shapes)

1. **Loop-local stall counter**: `select_step` already emits
   `NO_UNCHECKED_STEPS`; persist a consecutive-occurrence counter in the run
   dir (cleared whenever a step is selected or continue_work appends a new
   step). When the counter reaches N (e.g. 3) with unchecked hard criteria
   remaining, route to the ENH-2583 partial-credit chain instead of another
   `continue_work` deliberation.
2. **Detector enhancement**: extend `StallDetector` progress accounting to
   honor the loop's `circuit.repeated_failure.exclude_paths` (mutations to
   excluded bookkeeping files don't count as progress), letting the generic
   window fire on this cycle.

Either way, N no-progress cycles must cost N × ~20ms shell + at most one
`continue_work` deliberation — not ~15 minutes of repeated LLM re-planning.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**For Option 1 (loop-local counter) — in-tree precedent:**

- `scripts/little_loops/loops/general-task.yaml:163-180` already uses a per-run-dir counter pattern in `select_step` (the `step-attempts.txt` file). The exact shell shape: `ATTEMPTS="${context.run_dir}/step-attempts.txt"; PRIOR=$(grep -Fx -- "$STEP" "$ATTEMPTS" ...); ... echo "$STEP" >> "$ATTEMPTS"`. A new sibling file like `${context.run_dir}/continue-work-spin-counter.txt` fits cleanly and reuses `${context.run_dir}` exposure that every state already has.
- `scripts/little_loops/loops/lib/common.yaml:23-45` exposes `retry_counter` — a parameterized counter fragment with `parameters.counter_key` + `parameters.max_retries` and an `output_numeric lt ${param.max_retries}` evaluator. Could be reused as the gate state, but Option 1 doesn't need it: a single `select_step` shell extension (read, increment, branch on threshold) plus a routing change in `continue_work.on_no` is sufficient.
- **Reset semantics** — clear the counter when (a) `select_step` returns a fresh step (the existing branch at `general-task.yaml:171-180` already conditionally skips the echo step on abandonment — the same path can `rm -f` the spin counter on a real selection), or (b) `continue_work` appends a new actionable step (infer from `current-step.txt` presence after the prompt — see `general-task.yaml:269-285`).
- **Threshold gate location** — best at `select_step`'s `on_no` (where `NO_UNCHECKED_STEPS` is emitted). Adding a new state between `select_step.on_no` and `check_done` is unnecessary; the increment happens inside `select_step`'s shell action and the gate is `select_step.on_no` → either `check_done` (counter < N) or `summarize_partial` (counter >= N).

**For Option 2 (detector enhancement) — in-tree precedent:**

- The single mechanical change point is `scripts/little_loops/fsm/executor.py:1010-1011`: replace `if not paths: return None` with a fallback that watches all `run_dir` files minus `excluded`. Specifically, when `progress_paths` is empty but `exclude_paths` is non-empty, watch `(mtime, size)` for every regular file under `run_dir` not in `excluded`.
- **Schema change** — likely a new opt-in flag on `RepeatedFailureConfig` (`scripts/little_loops/fsm/schema.py:991-1022`) such as `watch_all_when_empty: bool = False`, mirroring the skip-if-default `to_dict`/`from_dict` pattern at lines 998-1022. JSON schema counterpart at `scripts/little_loops/fsm/fsm-loop-schema.json:237-270` must be updated in lockstep (`additionalProperties: false` is in effect).
- **Trade-off** — Option 2 silently changes semantics for ALL loops using `exclude_paths`-alone, which is desirable here but needs the opt-in flag to avoid regressing loops that deliberately rely on the inert behavior. Validation should flag `exclude_paths` without `progress_paths` AND without `watch_all_when_empty` (extending `_validate_progress_paths_isolation` at `scripts/little_loops/fsm/validation.py:2370-2400`).
- BUG-1767 / ENH-2245 are the historical precedent for additive config fields: each was a new optional field with skip-if-default serialization, never a breaking change.

**Common to both options:**

- The partial-credit chain at `scripts/little_loops/loops/general-task.yaml:616-687` (`summarize_partial` → `write_partial_summary` → `partial`) is reachable from `final_verify.on_error` (`general-task.yaml:458`) and the loop-level `on_max_steps` (`general-task.yaml:9`). The spin-guard route target is the same `summarize_partial` — it takes a `dod.md` with a `## Verification Criteria` section and writes `summary.json` unconditionally. **No additional prompt plumbing required.**
- A diagnostic event (`STALL_DETECTED_EVENT`) is already emitted at `scripts/little_loops/fsm/executor.py:1235` when the generic detector trips — Option 2's path emits one for free; Option 1 should emit an analogous event before routing to `summarize_partial` so audit reports (`general-task-audit-2026-07-09T232714.md`) capture the spin guard firing.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — add spin-counter logic to `select_step` (Option 1) and/or update `circuit.repeated_failure` config (Option 2). New routing target is `summarize_partial` (already implemented via ENH-2583 at lines 616-687).
- `scripts/little_loops/fsm/executor.py` (Option 2 only) — extend `_compute_progress_fingerprint` (lines 996-1035) to honor `exclude_paths` when `progress_paths` is empty. Single edit point: lines 1010-1011 (`if not paths: return None`).
- `scripts/little_loops/fsm/schema.py` (Option 2 only) — extend `RepeatedFailureConfig` (lines 991-1022) with a new opt-in field (e.g. `watch_all_when_empty: bool = False`) using the skip-if-default `to_dict`/`from_dict` pattern at lines 998-1022.
- `scripts/little_loops/fsm/fsm-loop-schema.json` (Option 2 only) — add the new property under `circuit.repeated_failure.properties` at lines 237-270.
- `scripts/little_loops/fsm/validation.py` (Option 2 only) — extend `_validate_progress_paths_isolation` (lines 2370-2400) to require the opt-in flag when only `exclude_paths` is set.
- `scripts/tests/test_general_task_loop.py` — add tests for the new counter logic / new routing (Option 1) or the new detector semantics (Option 2). Existing scaffolding at lines 415-465 (`_setup_run_dir`, `_load_state_script`, `_bash`) and structural assertions at lines 34-75 (`TestGeneralTaskLoopFile`) are reusable.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/stall_detector.py` — Option 2 changes the semantics of the `record()` call at lines 42-61 (currently no-ops on `None` fingerprint).
- `scripts/little_loops/fsm/__init__.py` — re-exports `StallDetector`, `RepeatedFailureConfig`; verify no surface change needed.
- `scripts/tests/test_fsm_executor.py` — existing `TestStallDetector` at lines 7547-7918 and `TestRecurrentWindowDetector` at lines 7921+ must continue passing; the `test_exclude_paths_allows_stall_despite_self_writes` regression test at lines 7831-7918 (BUG-1767) is the model for the new test.
- `scripts/tests/test_stall_detector.py` — unit-level coverage for the detector; Option 2 changes may need new cases here.

_Wiring pass added by `/ll:wire-issue` (Option 1 — selected):_
- `scripts/little_loops/loops/proof-first-task.yaml:14` — sets `context.impl_loop: "general-task"` as its default delegation target; when the spin guard routes to `summarize_partial` the loop terminates at `partial` (deliberately NOT `done`), which propagates to the parent as a non-success verdict. Verify the parent already treats `partial` as handled (ENH-2575 / audit-loop-run recognize `partial`) — no code change expected, but the behavioral coupling must be confirmed. [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/loops/general-task.yaml:163-180` (`select_step` abandoned-step cap) — exact in-loop precedent for Option 1's per-run-dir counter pattern.
- `scripts/little_loops/loops/lib/common.yaml:23-45` (`retry_counter` fragment) — generic parameterized counter with numeric gate; reusable if Option 1 prefers a fragment call over an inline shell extension.
- `scripts/little_loops/loops/general-task.yaml:616-687` — partial-credit chain (`summarize_partial` → `write_partial_summary` → `partial`) is the destination terminal in both options.
- `scripts/little_loops/loops/general-task.yaml:9` (`on_max_steps: summarize_partial`) and `:458` (`final_verify.on_error: summarize_partial`) — existing routes into the partial-credit chain.

_Wiring pass added by `/ll:wire-issue` (Option 1 — selected):_
- `scripts/little_loops/loops/loop-composer-adaptive.yaml:432-456` (`check_replan_budget` + `increment_replan_count`) — two-state counter-budget precedent with an `output_numeric operator: lt, target: ${context.max_replans}` gate; direct model for the spin-gate numeric evaluator if a dedicated gate state is used. Its structural test class `TestReplanBudget` (`scripts/tests/test_loop_composer_adaptive.py:167-206`) is the model for the new spin-gate routing assertions. [Agent 3 finding]

### Tests
- `scripts/tests/test_general_task_loop.py:444-449` (`test_empty_plan_emits_no_unchecked_steps`) — model for the new Option 1 shell-action test.
- `scripts/tests/test_general_task_loop.py:34-75` (`TestGeneralTaskLoopFile`) — model for structural assertions on the new routing.
- `scripts/tests/test_fsm_executor.py:7831-7918` (`test_exclude_paths_allows_stall_despite_self_writes`) — BUG-1767 regression test; Option 2 needs the inverse assertion (stall fires because the self-write is excluded from progress).

_Wiring pass added by `/ll:wire-issue` (Option 1 — selected):_
- `scripts/tests/test_general_task_loop.py:350-351` (`TestENH1732StateSplit.test_select_step_routes_no_to_check_done`) — asserts `select_step.on_no == "check_done"`; **WILL BREAK** if the spin-gate re-routes `select_step.on_no` to a new `spin_gate` state. Update this assertion to match the chosen routing shape. [Agent 2 + Agent 3 finding]
- `scripts/tests/test_general_task_loop.py:209-217` (`TestBUG1687ContinueWorkCapture.test_continue_work_routes_to_select_step`) — asserts `continue_work.on_no == "select_step"`; only needs updating if the gate is placed on `continue_work.on_no` instead of `select_step.on_no` (the selected Option 1 puts it on `select_step`, so this likely stays green — but confirm). [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — **not previously in this Integration Map.** `TestBuiltinLoopFiles.test_all_validate_as_valid_fsm` (`:46-54`) re-validates every builtin loop, so the new `spin_gate` state must pass FSM schema validation (declare `on_yes`/`on_no` or `next:`, `action_type: shell`, no `model`/`params`/`loop`/`with`). The bare-`PASS` sweep (`:170-188`) and unescaped-`${...}` sweep (`:190+`) also run against the new shell action. `TestGeneralTaskLoop` (`:8911-9067`) carries per-state structural assertions for general-task — add spin-gate coverage here or in `test_general_task_loop.py`. `test_expected_loops_exist` (`:76-168`) is a subset/name check — adding a state is non-breaking. [Agent 1 + Agent 3 finding]
- `scripts/tests/test_fsm_interpolation.py:773-795` (`test_general_task_check_done_safe_with_empty_captured`, `test_general_task_run_final_tests_safe_with_empty_context`) — load `general-task.yaml` and assert interpolation safety; only relevant if the `spin_gate` action introduces a `${captured.*}` reference. Advisory. [Agent 1 finding]
- New shell-action tests (counter increment/reset) model: `TestSelectStepShellAction` (`test_general_task_loop.py:434-465`), using `_setup_run_dir`/`_load_state_script`/`_bash` (`:415-426`). Verify: counter file increments on the `NO_UNCHECKED_STEPS` branch, resets (`rm -f`) only on a real `SELECTED_STEP:` selection, and is NOT reset on the `STEP_ABANDONED:` branch. [Agent 3 finding]

### Documentation
- `docs/guides/LOOPS_GUIDE.md` (line 1135+ covers `progress_paths` from BUG-1674) — Option 2 should add a section on `watch_all_when_empty` / exclude-only semantics.
- `docs/reference/loops.md` (lines 859+ for `circuit.repeated_failure`, line 869 for `exclude_paths`) — Option 2 needs updated documentation.
- `docs/reference/API.md` (line 4646+ `RepeatedFailureConfig`) — Option 2 needs the new field documented.

_Wiring pass added by `/ll:wire-issue` (Option 1 — selected):_
- `docs/guides/LOOPS_REFERENCE.md:105-129` — documents the `general-task` state machine sequence, including the exact `continue_work → select_step → check_done → count_done → continue_work` convergence spin this issue guards (and the per-step iteration-cost formula at line 129). Add a note describing the new spin-gate → `summarize_partial` route after N no-progress cycles. This is the Option-1-relevant doc (the three docs above are Option-2 only). [Agent 1 finding]
- `docs/reference/EVENT-SCHEMA.md:650` (fyi) — example payload uses `"summary_state": "summarize_partial"` for `max_steps_summary`; if the spin guard emits a diagnostic event or a distinct `summary_state`, keep the example consistent. Report-only. [Agent 1 finding]

### Configuration
- No new config in `.ll/ll-config.json` is needed. Loop-local counter lives entirely inside `${context.run_dir}` (per-run filesystem state).

## Proposed Solution

**Option 1 (preferred for loop-locality):** Extend `select_step` in `general-task.yaml:155-195` with a spin-counter file at `${context.run_dir}/continue-work-spin-counter.txt`:

> **Selected:** Option 1 (loop-local stall counter) — surgical, verbatim in-tree precedent, no FSM-internal changes; the convergence spin is unique to general-task so a generic detector fix (Option 2) isn't warranted.

1. After the existing `NO_UNCHECKED_STEPS` branch (line 160) emits, increment the counter instead of bare `echo "NO_UNCHECKED_STEPS"`. Reset (`rm -f`) the counter when a real step is selected (the abandoned-step branch at line 171-180 is conditional — the echo-on-success path is where to add the reset).
2. Add a new `spin_gate` shell state (or extend `select_step.on_no` with a numeric evaluator) that reads the counter and routes:
   - counter < N (e.g. 3): route to `check_done` (current behavior).
   - counter >= N: route to `summarize_partial` (partial-credit chain, ENH-2583).
3. Emit a `spin_guard_triggered` event before routing to `summarize_partial`, mirroring `STALL_DETECTED_EVENT` at `executor.py:1235`.

**Option 2 (preferred for cross-loop reusability):** Make `exclude_paths` actually work standalone:

1. Add `watch_all_when_empty: bool = False` to `RepeatedFailureConfig` (`scripts/little_loops/fsm/schema.py:991-1022`) with skip-if-default `to_dict`/`from_dict` (`schema.py:998-1022`).
2. In `_compute_progress_fingerprint` (`executor.py:996-1035`): when `progress_paths` is empty AND `watch_all_when_empty` is True AND `exclude_paths` is non-empty, enumerate regular files under `context.run_dir`, exclude any in the resolved `excluded` set, and compute the `(mtime, size)` fingerprint across the remainder. Return `None` otherwise.
3. Update `fsm-loop-schema.json:237-270` (`repeated_failure.properties`) with the new property block.
4. Extend `_validate_progress_paths_isolation` (`scripts/little_loops/fsm/validation.py:2370-2400`) to require the opt-in flag when only `exclude_paths` is set (warning, not error — backward-compatible).
5. In `general-task.yaml:24-30`, set `watch_all_when_empty: true` and route `on_repeated_failure: summarize_partial` (instead of `diagnose`).

**Decision guidance:**
- Pick Option 1 if the spin pattern is unique to general-task (likely true — the convergence spin is a property of LLM-driven convergence detection, not a general FSM hazard), and you want a small, surgical change that does not touch FSM internals.
- Pick Option 2 if the same `exclude_paths`-alone trap is expected to affect other loops as they grow (`recursive-refine`, `rn-implement`, and the 100+ loop YAMLs in `scripts/little_loops/loops/`). Option 2 fixes the generic detector and benefits every future loop.
- Either way, the **route target** is the ENH-2583 partial-credit chain — `summarize_partial` (`general-task.yaml:616-637`).

**Estimated cost (Option 1):** ~30 lines of shell + ~10 lines of YAML routing in `general-task.yaml`; one new shell-action test class.
**Estimated cost (Option 2):** ~5 lines of Python in `executor.py`, ~3 lines in `schema.py`, ~15 lines in `fsm-loop-schema.json`, ~10 lines in `validation.py`, ~3 lines in `general-task.yaml`; one new unit test for the detector + one integration test.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be folded into the Option 1 implementation (in addition to the numbered steps above):_

1. Update `scripts/tests/test_general_task_loop.py:350-351` (`test_select_step_routes_no_to_check_done`) to assert the new `select_step.on_no` routing through the spin gate.
2. Add spin-gate shell-action tests (counter increment on `NO_UNCHECKED_STEPS`, reset only on real `SELECTED_STEP:`, no reset on `STEP_ABANDONED:`) — model on `TestSelectStepShellAction` (`test_general_task_loop.py:434-465`); model the structural/routing assertions on `TestReplanBudget` (`test_loop_composer_adaptive.py:167-206`).
3. Confirm the `test_builtin_loops.py` FSM-validation sweep (`:46-54`) passes with the new `spin_gate` state, and add per-state coverage to `TestGeneralTaskLoop` (`:8911-9067`) if desired.
4. Update `docs/guides/LOOPS_REFERENCE.md:105-129` to document the spin-guard route (spin counter → `summarize_partial` after N no-progress cycles).
5. Confirm `proof-first-task.yaml` (parent delegating to general-task) treats a spin-fired `partial` verdict correctly — no change expected, verification only.

**Placement constraints (from wiring analysis):**
- Increment the counter **only** in the empty-plan branch (`general-task.yaml:158-162`, where `NO_UNCHECKED_STEPS` is emitted), before the `echo`.
- Reset (`rm -f`) **only** in the real-step-selected branch (`:181-186`, after `echo "$STEP" >> "$ATTEMPTS"`). The abandoned-step branch (`:171-180`) must **NOT** reset — a `max_step_attempts` abandonment is exactly the no-progress signal the guard detects.
- A new `spin_gate` shell state must declare `on_yes`/`on_no` (or `next:`); `action_type: shell`; no `model`/`params`/`loop`/`with`. `${context.run_dir}/continue-work-spin-counter.txt` already satisfies MR-3 isolation, and the loop's `artifact_versioning_ok: true` (`:8`) silences MR-5. If an `output_numeric` gate is used, mind `_validate_zero_retry_counter` (choose `target: 3` for a 2-cycle allowance to avoid the WARNING).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-10.

**Selected**: Option 1 (loop-local stall counter)

**Reasoning**: Both options route to the same ENH-2583 `summarize_partial` partial-credit chain; the choice is one of scope. Option 1's increment-and-numeric-gate shape is verbatim in-tree precedent (`goal-cluster.yaml:515-528` `check_cluster_replan_budget`; `general-task.yaml:171-181` `step-attempts.txt`), the `${context.run_dir}` per-run counter idiom appears at 30+ call sites, and the shell-action test scaffolding at `test_general_task_loop.py:415-465` is a drop-in — all contained to the one loop file with zero FSM-internal changes. Option 2 shifts `exclude_paths` semantics for every loop and touches five files plus schema-JSON lockstep for value this issue doesn't need, since the convergence spin is a property of LLM-driven convergence detection specific to general-task, not a generic FSM hazard.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option 1 (loop-local counter) | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |
| Option 2 (detector enhancement) | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |

**Key evidence**:
- Option 1: Verbatim counter precedent (`goal-cluster.yaml:515-528`, `general-task.yaml:171-181`), 30+ `${context.run_dir}` counter call sites, `summarize_partial` terminal already wired from two routes, matching shell-action test scaffolding (`test_general_task_loop.py:415-465`). Reuse score 3. Only novel piece is cross-state counter reset; the optional `spin_guard_triggered` event has no shell-state channel and can be dropped.
- Option 2: Fits the BUG-1767/ENH-2245 additive opt-in `RepeatedFailureConfig` precedent (`schema.py:991-1022`), but requires a net-new directory-walk in `_compute_progress_fingerprint` and shifts detector semantics for all `exclude_paths` loops behind an opt-in flag. Reuse score 2; higher blast radius (5 files + JSON-schema lockstep) than this issue's scope justifies.

## Acceptance Criteria

- [ ] A `continue_work → select_step(NO_UNCHECKED_STEPS) → … → continue_work`
      cycle that appends no new plan step terminates in ≤N cycles by routing
      to the partial-credit chain (ENH-2583), not by continue_work
      self-assessing WORK_COMPLETE.
- [ ] Counter/detector resets on genuine progress (a step selected, a new
      remediation step appended, or a criterion flipped).
- [ ] Abandoned-step interaction covered: steps at `max_step_attempts` do not
      re-arm the spin.
- [ ] Shell-execution tests for the counter logic in
      `scripts/tests/test_general_task_loop.py`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Shell-action test scaffolding at `scripts/tests/test_general_task_loop.py:415-465` (`_setup_run_dir`, `_load_state_script`, `_bash`) is reused across `TestSelectStepShellAction`, `TestVerifyStepShellAction`, `TestMarkDoneShellAction`, etc. Follow `TestSelectStepShellAction.test_empty_plan_emits_no_unchecked_steps` at lines 444-449 as the test model for the new counter increment/reset logic.
- Structural assertion tests in `TestGeneralTaskLoopFile` (`test_general_task_loop.py:34-75`) verify `state.next` / `on_yes` / `on_no` / `on_error` / `evaluate.pattern` directly against the loaded YAML. Use these to assert the new routing (e.g. `select_step.on_no == "spin_gate"` or `continue_work.on_no == "summarize_partial"` depending on Option chosen).
- For Option 2, the regression test pattern at `scripts/tests/test_fsm_executor.py:7831-7918` (`test_exclude_paths_allows_stall_despite_self_writes`) uses a `SelfWriteRunner` that writes to `plan.md` every cycle. Emulate this shape but flip the assertion: with `watch_all_when_empty: true` and the self-write excluded, the detector SHOULD now trip on the consecutive `(state, exit_code, verdict)` triple because the self-write no longer resets the deque.
- Recurrent-window tests at `scripts/tests/test_fsm_executor.py:7921+` (`TestRecurrentWindowDetector`) demonstrate the non-consecutive counting pattern added by ENH-2245; Option 2's `watch_all_when_empty` may combine with `recurrent_window` for an even more aggressive guard.
- Audit evidence model: `general-task-audit-2026-07-09T232714.md` (the source of this issue) and `.loops/diagnostics/general-task-20260707T152654Z.md` (BUG-1960 era) — new audit artifacts should follow the same `.loops/diagnostics/general-task-<timestamp>Z.md` convention.

## Notes

From audit recommendation 3 (`general-task-audit-2026-07-09T232714.md`).
Distinct from the abandoned-step cap itself (already implemented in
`select_step`) — this guards what happens *after* every remaining step has
been abandoned.


## Session Log
- `/ll:wire-issue` - 2026-07-11T00:07:06 - `9c5cc73a-20e5-4fa5-8515-01177f26a4d8.jsonl`
- `/ll:decide-issue` - 2026-07-10T23:41:26 - `3e5921d8-498f-4333-bab4-0762112d1daf.jsonl`
- `/ll:refine-issue` - 2026-07-10T23:37:01 - `c1630b0e-e5ca-4441-abf2-969719ea948d.jsonl`
