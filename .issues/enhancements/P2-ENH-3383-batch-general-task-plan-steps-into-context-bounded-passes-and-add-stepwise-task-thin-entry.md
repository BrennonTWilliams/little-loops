---
id: ENH-3383
type: ENH
title: Batch general-task plan steps into context-bounded passes and add stepwise-task
  thin entry
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-04'
captured_at: '2026-09-04T03:34:05Z'
completed_at: '2026-09-04T03:34:18Z'
---

# ENH-3383: Batch general-task plan steps into context-bounded passes and add stepwise-task thin entry

## Summary

`general-task.yaml` paid two to three LLM turns per plan step (`do_work`, `check_done`, and usually `continue_work`), and `check_done`'s `min(3, total_checked)` sample re-verification dominated wall-clock across several runs in multiple projects. Ordinary plans took multiple hours. This enhancement keeps the `general-task` name and its hardened contract (baseline test resolution, DoD-first with standing criteria, `final_verify` + `run_final_tests` + provisional-marker gate, `summary.json` verdict schema, `partial` terminal, and every BUG-3269 / BUG-3270 / ENH-2857 fix) and replaces only the execution middle: plan steps now run in **batched passes** (all remaining steps per pass by default), each pass is **context-bounded** via the `/ll:handoff` → `CONTEXT_HANDOFF` → `on_handoff: spawn` → `ll-loop resume` chain with a per-step progress ledger, the per-pass sample is capped to one criterion, an oversized pass is halved mechanically on timeout, and the old one-step-at-a-time behaviour is exposed as an opt-in thin entry, `stepwise-task`.

## Current Behavior

- `select_step` selected exactly one unchecked plan line; `do_work` implemented only that step (900s timeout, self-retry twice on exit 124); `check_done` ran after every step and independently re-verified up to three already-checked criteria; `continue_work` split any timed-out step.
- A plan of N steps cost roughly 2N–3N model turns before the final gate. `check_done` was the dominant cost.
- A `do_work` session that hit the context limit had no way to record partial progress: `ll-loop resume` re-enters the interrupted state from scratch and the continuation prompt is only displayed, never injected, so the re-entered session re-did work.
- The name `general-task` described a category, but the file implemented one specific strategy (stepwise).

## Expected Behavior

- `general-task` executes plan steps in passes sized by `context.steps_per_pass` (default `0` = all remaining). One `check_done` per pass, sampling exactly one already-checked criterion.
- A pass may span several host sessions. `do_work` appends each finished step's exact line to `${context.run_dir}/completed-steps.txt` and refreshes `last-files.txt` per step; on the context-monitor warning it runs `/ll:handoff` and ends its turn; the spawned continuation re-enters `do_work`, skips ledgered lines, and runs `/ll:resume` when `.ll/ll-continue-prompt.md` is newer than `pass-started.txt`.
- A timed-out multi-step pass has its uncompleted part halved mechanically (no LLM), with attempts refunded; a single-step timeout still splits the step. Finished steps in a pass that died are credited, never re-implemented.
- `stepwise-task` (new) binds `steps_per_pass: 1` and delegates to `general-task`, giving today's per-step verification under an honest name without forking the FSM.

## Motivation

`general-task` is the default `impl_loop` for `proof-first-task` and `spike-gate` and the recommended one-off task loop in `LOOPS_GUIDE.md`, so its per-step cost is paid by every consuming project. The user observed `check_done` dominating wall-clock across several runs in multiple projects, with ordinary plans taking several hours. The FSM's verification contract is sound and heavily hardened; only its granularity (one step per LLM verification pass) was wrong for the common case, and its name suggested a general strategy when it implemented a specific slow one.

## Proposed Solution

One FSM, one knob, two entry points (the `rn-stepwise` → `rn-refine` pattern), rather than a rename or a fork of ~1,150 lines of hardened shell. Renaming was rejected because `ll-history` / `audit-loop-run` key run series by loop name, `proof-first-task` and `spike-gate` default `impl_loop` to `general-task`, and archived runs under `.loops/.history/*-general-task/` would split.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — `context`, `select_step`, `do_work`, `capture_work_exit`, `mark_done`, `check_done`, `continue_work`, `resume_check` comment, `diagnose`, `description`
- `scripts/little_loops/loops/stepwise-task.yaml` — new thin entry

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/proof-first-task.yaml`, `spike-gate.yaml` — `impl_loop: "general-task"` default; unchanged because the name is kept
- `scripts/little_loops/fsm/executor.py` `_handle_handoff`, `fsm/handoff_handler.py`, `fsm/signal_detector.py` — the handoff chain `do_work` now relies on (no code change)
- `hooks/scripts/context-monitor.sh`, `commands/handoff.md`, `commands/resume.md` — emit the warning / marker / continuation the prompt references (no code change)

### Similar Patterns
- `scripts/little_loops/loops/rn-stepwise.yaml` → `rn-refine.yaml` — thin-entry delegation via `loop:` + `with:` (ENH-2862)
- `apply-research.yaml:40` — `${context.x:shell}` MR-11 remedy for a context value at a bash-token position

### Tests
- `scripts/tests/test_general_task_loop.py` — helper interpolation, updated pins, `TestBatchedPasses`
- `scripts/tests/test_builtin_loops.py` — expected loop-name set, `TestGeneralTaskLoop` routing pins; MR-11 allowlist and interpolation baseline unchanged by design
- `scripts/tests/test_wiring_guides_and_meta.py::test_doc_counts_all_match`, `test_wiring_skills_and_commands.py` mirror gates, `test_packaging_duplicate_files.py` README mirror — satisfied by the doc/mirror syncs

### Documentation
- `docs/guides/LOOPS_REFERENCE.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/reference/loops.md`, `scripts/little_loops/loops/README.md`, `skills/create-loop/loop-types.md` (+ `.gemini/.kimi-code/.qwen` mirrors), `README.md`, `scripts/README.md`

### Configuration
- `context_monitor.enabled` / `auto_handoff_threshold` in `.ll/ll-config.json` govern when the in-pass handoff fires; with the monitor disabled the exit-124 shrink path is the fallback

## Program Design

### Pass lifecycle (general-task.yaml)

`select_step` → `do_work` → (`verify_step` → `mark_done` → `check_done` → `count_done`) | (`capture_work_exit` → `continue_work` | `verify_step`)

- `select_step` (shell) — reads N from `steps-per-pass.txt` (seeded from `${context.steps_per_pass:shell}`), selects the first unchecked line via the unchanged cap/abandon/halt path, then up to N-1 more non-exhausted lines. Writes `current-step.txt` (multi-line), `checkpoint.json` (`in_flight_step`, `in_flight_count`), clears `completed-steps.txt`, touches `pass-started.txt`.
- `do_work` (prompt, 3600s) — implements the listed steps in order; per step appends the exact line to `completed-steps.txt` and rewrites `last-files.txt`; on the context-monitor warning runs `/ll:handoff`. `on_error: capture_work_exit`.
- `capture_work_exit` (shell, `evaluate: output_contains PARTIAL_CREDIT`) — writes `last-exit-code.txt`; on 124 with >1 uncompleted lines halves `steps-per-pass.txt` and refunds attempts (only when the ledger is empty); emits `PARTIAL_CREDIT` when the ledger is non-empty → `on_yes: verify_step`, else `on_no: continue_work`.
- `mark_done` (shell) — marks ledger lines (or all lines) `[x]`, refunds attempts for uncompleted lines, deletes the ledger and checkpoint.
- `check_done` (prompt) — delta verification over every `LAST_STEP` line; exactly one sampled criterion.
- `continue_work` (prompt) — 124: all-`[x]` or multi-line → `PASS_SHRUNK`; single line → split.

### Signatures

- `_load_state_script(state_name: str, context_overrides: dict | None = None) -> str` — test helper in `scripts/tests/test_general_task_loop.py`; extracts a state's shell action and interpolates every `context:` key in both `${context.k}` and `${context.k:shell}` forms (YAML defaults overridden by `context_overrides`), leaving runner-injected `run_dir` / `input_hash` to the caller.
- `derive_input_hash(context: dict[str, Any]) -> None` — existing, `scripts/little_loops/fsm/context_seed.py`; unchanged, it is why `stepwise-task` only needs to pass `input` through `with:`.

### Call Path

`ll-loop run stepwise-task "<task>"` → `stepwise-task.yaml::run` (`loop: general-task`, `with: input, steps_per_pass=1`) → `FSMExecutor` sub-loop spawn (`fsm/executor.py`, `derive_input_hash` on the child context) → `general-task.yaml::check_baseline_tests` → … → `select_step` → `do_work` → [`/ll:handoff` → `HANDOFF_SIGNAL` (`fsm/signal_detector.py`) → `FSMExecutor._handle_handoff` → `HandoffHandler._spawn_continuation` (`fsm/handoff_handler.py`) → `ll-loop resume general-task` → `do_work` re-entry] → `verify_step` → `mark_done` → `check_done` → `count_done`.

### Run-dir artifacts added
`steps-per-pass.txt`, `completed-steps.txt`, `pass-started.txt`, `last-exit-code.txt` (existing), transient `pass-remaining.tmp` / `pass-undone.tmp`.

### Invariants
- Attempt refund happens in exactly one state per path (`capture_work_exit` when the ledger is empty, `mark_done` otherwise), so a step is never double-refunded.
- `current-step.txt` is never removed mid-loop (BUG-2538); `checkpoint.json` stays valid JSON (first line only).
- No `mr11-ok` markers added; all new context refs use the `:shell` suffix.

## Scope Boundaries

- No rename of `general-task`; no change to DoD authoring, `final_verify`, `run_final_tests`, spin gates, summaries, or verdict schema.
- No executor change: the handoff chain is the existing `CONTEXT_HANDOFF` → `on_handoff: spawn` → `ll-loop resume` path; the ledger lives in the loop, not the runtime.
- No per-step commit/revert ("atomic" steps). That belongs to `rn-refine`'s leaf chain and would be a separate enhancement layered on `stepwise-task`.
- No CHANGELOG entry (promoted at release prep).

## Implementation Steps

All in `scripts/little_loops/loops/general-task.yaml` unless noted.

- [x] `context.steps_per_pass: 0`; effective value persisted to `steps-per-pass.txt`. Shell references use the MR-11 `:shell` suffix (`${context.steps_per_pass:shell}`, `${context.max_step_attempts:shell}`), so no new `mr11-ok` residual markers.
- [x] `select_step`: first-line attempt-cap / `[!]` abandonment / ENH-2857 blocker-halt path unchanged; then extends the selection with non-exhausted unchecked lines up to N (all when 0). Writes multi-line `current-step.txt`, appends every line to `step-attempts.txt`, clears `completed-steps.txt`, touches `pass-started.txt`, writes `checkpoint.json` with `in_flight_step` (first line) + `in_flight_count`, emits `SELECTED_COUNT: n` and `SELECTED_STEP: <first>`.
- [x] `do_work`: batched prompt with the progress ledger, re-entry check, and handoff-chain instructions; `timeout: 3600`; `on_error: capture_work_exit` (self-retry, `max_retries`, `retryable_exit_codes: [124]`, `on_retry_exhausted` removed).
- [x] `capture_work_exit`: records exit code; on 124 with more than one uncompleted line halves `steps-per-pass.txt` (integer, min 1), refunds one attempt per uncompleted line, prints `PASS_SHRUNK: C -> N`; if the ledger is non-empty emits `PARTIAL_CREDIT` and routes `on_yes: verify_step` (else `on_no: continue_work`) so finished steps reach `mark_done`. Refund happens in exactly one place per path (here when the ledger is empty, `mark_done` otherwise). Uses `grep -c … || true` + `[ -z ] && =0` per BUG-2827.
- [x] `mark_done`: credits `completed-steps.txt` lines when non-empty, else every `current-step.txt` line; refunds attempts for uncompleted lines; clears the ledger; never removes `current-step.txt`.
- [x] `check_done`: marker text describes multi-line `LAST_STEP`; delta scope covers any step line; sample re-verification is exactly one criterion, rotating away from the previous sample.
- [x] `continue_work` exit-124 branch: all-lines-already-`[x]` → `PASS_SHRUNK`; multi-line → `PASS_SHRUNK` (no split, no remediation); single line → split as before. OOM text no longer claims "retry exhaustion".
- [x] `resume_check` comment, `diagnose` state list (`capture_work_exit` added), `description:` updated.
- [x] New `scripts/little_loops/loops/stepwise-task.yaml`: `loop: general-task`, `with: {input, steps_per_pass: 1}`, `required_inputs: ["input"]`, `scope`, `on_handoff: spawn`, plain `done`/`failed` terminals.
- [x] Tests — `scripts/tests/test_general_task_loop.py`: `_load_state_script` now interpolates every `context:` key (bare and `:shell` forms) with overrides; stale pins updated (`do_work` routing/timeout, `min(3` sample, `retryable_exit_codes`); new 18-test `TestBatchedPasses` covering select/mark/shrink/partial-credit paths and the `stepwise-task` `with:` keys. `scripts/tests/test_builtin_loops.py`: `stepwise-task` registered in the exact expected-name set; two stale `capture_work_exit`/`do_work` routing pins rewritten.
- [x] Docs — `docs/guides/LOOPS_REFERENCE.md` (table row, select/do_work/mark_done bullets, sample size, exit-124 bullet, step-cap arithmetic), `docs/guides/LOOPS_GUIDE.md` (decision tree, table), `docs/reference/loops.md` (new `stepwise-task` section), `scripts/little_loops/loops/README.md` (rows), `skills/create-loop/loop-types.md` (Batched Passes paragraph) + `.gemini/.kimi-code/.qwen` mirrors via `ll-adapt --apply`, `README.md` + `scripts/README.md` loop count 104 → 105.

## Impact

- **Priority**: P2 - Multi-hour runs on ordinary plans across every consuming project; `general-task` is the default `impl_loop` for `proof-first-task` and `spike-gate`.
- **Effort**: Medium - Shell edits to five states plus prompt rewrites, a thin new loop, ~320 test lines, and doc/mirror syncs.
- **Risk**: Medium - The pass ledger and partial-credit routing are new control flow; covered by shell-level tests but the handoff chain itself is only exercised in a real run.
- **Breaking Change**: No - Same loop name, same artifacts and verdict schema; `stepwise-task` (or `--context steps_per_pass=1`) restores the previous behaviour exactly.

## Verification

- `ll-loop validate general-task` and `ll-loop validate stepwise-task` pass with no warnings.
- Direct bash smoke of `select_step` / `capture_work_exit` / `mark_done` with rendered actions: N=0 selects all four lines; N=2 selects two; exhausted non-first lines skipped; 124 on four uncompleted lines → `PASS_SHRUNK: 4 -> 2` with attempts refunded; 124 with one ledgered step → `PASS_SHRUNK: 3 -> 1` + `PARTIAL_CREDIT`, refund deferred to `mark_done`; single-step 124 leaves pass size alone; `mark_done` with a partial ledger marks only ledgered lines and refunds the rest.
- `python -m pytest scripts/tests/ -m "not integration and not conformance"`: 21,915 passed, 12 skipped after syncing the skill mirrors and `scripts/README.md`.
- Not yet done: a real end-to-end `ll-loop run general-task` to confirm one `check_done` per pass and a mid-pass handoff resuming into the same pass with the ledger honoured.

## Related

- Builds on ENH-2225 (final-only whole-suite gate), ENH-2857 (`[!]` abandonment and blocker halt), BUG-3269 / BUG-3270 (test-cmd resolution, final-verify spin gate) — all preserved unchanged.
- Pattern: ENH-2862 (`rn-stepwise` thin entry over `rn-refine`).
- Handoff mechanics: `fsm/signal_detector.py` `HANDOFF_SIGNAL`, `fsm/executor.py` `_handle_handoff`, `fsm/handoff_handler.py` `_spawn_continuation`, `commands/handoff.md`.

## Related Key Documentation

- `docs/guides/LOOPS_REFERENCE.md` § general-task
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` § The Design Rules (MR-11 `:shell` remedy, MR-13 abandonment verdicts)
- `docs/reference/loops.md` § `stepwise-task`

## Status

**Done** | Created: 2026-09-04 | Completed: 2026-09-04 | Priority: P2

Implemented directly in an interactive session (plan-mode design → apply → full-suite gate). Working tree changes are uncommitted at the time of writing; the plan is at `~/.claude/plans/check-done-does-indeed-dominate-scalable-hamster.md`.

## Session Log
- Interactive session (Claude Code) - 2026-09-04T03:34:18Z - design, implementation, tests, docs; see Verification
