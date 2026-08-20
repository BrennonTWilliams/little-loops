---
id: BUG-3270
type: BUG
title: 'general-task: no spin guard on the continue_work -> final_verify -> run_final_tests
  cycle (ENH-2585 coverage gap)'
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T22:49:08Z'
labels:
- bug
- loops
- general-task
- fsm
- spin-guard
- postmortem
relates_to:
- ENH-2585
- BUG-3269
- BUG-3271
- ENH-3272
---

# BUG-3270: general-task: no spin guard on the continue_work -> final_verify -> run_final_tests cycle (ENH-2585 coverage gap)

## Summary

`general-task.yaml` has a closed 3-state cycle — `continue_work → final_verify →
run_final_tests → continue_work` — with no spin guard on it. ENH-2585 shipped a guard
(`check_step_halt → spin_gate`) but it covers only the `select_step` path, and
`select_step` actively deletes the counter file that guard depends on, so the counter
cannot survive a `continue_work` lap.

In run `2026-08-20T121448` this cycle ran **45 times over 2h37m** — 53% of wall clock —
with zero file mutations, while the decisive "we are done" signals were present and
ignored on every lap. Postmortem:
`postmortems/general-task-final-verify-spin-2026-08-20.md` (§3).

## Current Behavior

State-entry tally from that run's `.events.jsonl`:

```
do_work 25   verify_step 50   mark_done 50   check_done 64   count_done 64
continue_work 152   final_verify 92   run_final_tests 90   spin_gate 14
```

Edge counts confirm the closed cycle: `continue_work→final_verify` **45**,
`final_verify→run_final_tests` **45**, `run_final_tests→continue_work` **45**.

**Why the existing guard does not apply.** `spin_gate` (`general-task.yaml:296`) is
reachable only via `select_step → check_step_halt → spin_gate`. It reads
`${context.run_dir}/continue-work-spin-counter.txt`, which is incremented at
`general-task.yaml:194` only on the `NO_UNCHECKED_STEPS` branch of `select_step`. The
counter is `rm -f`'d at `general-task.yaml:253` on every genuine `SELECTED_STEP:`.

The `final_verify` cycle never passes through `select_step` at all, so the counter is
neither incremented nor consulted. At kill time `continue-work-spin-counter.txt` read
**`1`** — every lap re-entered `continue_work` fresh. `spin_gate` did fire correctly 7
times in this run, on the path it actually covers.

**The signal was available and ignored on all 45 laps.** Captured variables, identical
every lap:

```json
"done_counts":     {"output": "{\"hard_unchecked_dod\": 0, \"soft_unchecked_dod\": 0,
                                \"unchecked_plan\": 0, \"failed_samples\": 0, \"total\": 0}"},
"continue_result": {"output": "WORK_COMPLETE"}
```

`done_counts.total == 0` means "nothing left to do". `continue_result == WORK_COMPLETE`
means the model agrees. The loop had both, 45 times, and had no edge that could act on
them.

## Steps to Reproduce

The guard gap is reachable by any defect that makes `run_final_tests` permanently
unsatisfiable. BUG-3269 is one such defect and the one actually observed:

1. Reproduce BUG-3269 (`.ll/ll-config.json` with `project.test_cmd: null`, bare `pytest`
   exits non-zero, run `general-task` on a task that completes).
2. Let the run reach `final_verify` for the first time.
3. Observe the cycle `continue_work → final_verify → run_final_tests → continue_work`
   repeating without bound. Confirm from `${run_dir}/.events.jsonl` that the three edge
   counts are equal and rising.
4. Confirm the guard is not engaging: `${run_dir}/continue-work-spin-counter.txt` stays at
   a low constant (it read `1` at kill time in the observed run) rather than climbing to
   `spin_gate`'s `target: 3`.
5. Confirm the signals are present and ignored: every lap's `done_counts` capture reads
   `"total": 0` and every lap's `continue_result` capture reads `WORK_COMPLETE`.

**Isolating this bug from BUG-3269**: after BUG-3269 is fixed, force the same shape by
setting `project.test_cmd` to a command that always exits non-zero (e.g.
`"sh -c 'exit 3'"`) while the baseline is `0`. The no-regression gate can then never pass,
and the same unguarded cycle appears — demonstrating that this issue is independent of its
trigger.

**Frequency**: deterministic once triggered. The cycle has no exit edge.

**Observed in**: `general-task` v1.156.0, run `2026-08-20T121448` — 45 laps, 2h37m, 0 file
mutations.

## Expected Behavior

A consecutive-no-progress counter on the edges that return to `continue_work` from the
verification tail — `run_final_tests → continue_work` and `count_final → continue_work`.
When N consecutive laps satisfy **all three** of:

1. `done_counts.total == 0`, and
2. `continue_result == WORK_COMPLETE`, and
3. no file under the baseline diff has changed since the previous lap,

route to `diagnose` or a `partial` terminal — never back to `continue_work`.

**Suggested N = 2.** There is no scenario where a third byte-identical lap produces a
different answer.

The counter must be reset only by genuine forward progress (a file mutation or a change in
`done_counts`), on the same principle as the `select_step` reset at `:253` — but it must
not share the `select_step` counter file, or the two guards will clobber each other.

## Motivation

This is the mechanism that made BUG-3269 unbounded rather than merely wrong. BUG-3269 poisoned
the gate input; the missing guard is why the loop could not notice and had to be killed by
hand.

Landing this independently of BUG-3269 is worthwhile precisely because it is
failure-mode-agnostic: any future defect that makes `run_final_tests` un-satisfiable
produces the same infinite cycle, and this guard bounds all of them. It is the second line
of defense, not a substitute for BUG-3269.

## Proposed Solution

Add a `final_verify_spin_gate` state modeled on the existing `spin_gate`
(`general-task.yaml:296`), with its own counter file (e.g.
`${context.run_dir}/final-verify-spin-counter.txt`) to avoid interference with
`continue-work-spin-counter.txt`.

Redirect `run_final_tests.on_no` and `count_final.on_no` through it rather than straight to
`continue_work`. The gate increments, compares against N, and either falls through to
`continue_work` (under the cap) or diverts to `summarize_partial` / `diagnose` (at the cap).

Fingerprinting for condition 3 can reuse the `baseline-ref.txt` machinery that
`check_provisional_markers` (`general-task.yaml:657`) already uses for its
`git diff --name-only "$BASELINE_REF"` check.

### Explicitly out of scope

The postmortem's §3 also floats a generalized version: "any edge that returns to a state
already visited with an identical captured-variable fingerprint should be counted, not just
the two hand-picked ones."

**Do not implement that here.** It is an FSM-executor change with blast radius across every
loop in the repo, proposed on the evidence of a single run. The two named edges are the
evidence-backed part. If the generalized guard is wanted, it needs its own issue and its
own evidence base.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — one new state, two edge redirects:
  - new `final_verify_spin_gate` state
  - `run_final_tests.on_no` (`:653`) — currently `continue_work`
  - `count_final.on_no` (`:648`) — currently `continue_work`

### Dependent Files (Callers/Importers)
- None. The change is internal to one loop's state graph; no Python or CLI surface moves.

### Similar Patterns
- `general-task.yaml:296` `spin_gate` — the existing guard to model on (shell counter +
  `output_numeric` / `lt` evaluate)
- `general-task.yaml:194` — counter increment on the `NO_UNCHECKED_STEPS` branch
- `general-task.yaml:253` — `rm -f "$SPIN_COUNTER"` reset on genuine progress; the reason
  the existing counter cannot serve this cycle
- `general-task.yaml:657` `check_provisional_markers` — the `baseline-ref.txt` +
  `git diff --name-only` machinery to reuse for the "no file changed" condition

### Tests
- `scripts/tests/test_builtin_loops.py` — reachability/graph assertions for built-in loops
- New: assert a run whose `run_final_tests` can never pass reaches a `partial` terminal
  within a bounded iteration count rather than running to `max_iterations`

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the spin-guard rule; note that a guard must
  cover every cycle back to a re-deliberation state, not just one path

### Configuration
- Consider exposing the cap as a `context` value (alongside `max_step_attempts`) rather than
  hard-coding N, so a run can raise it without editing the loop.

## Program Design

### Signatures

- `final_verify_spin_gate(done_counts: json, continue_result: str, baseline_ref: str) -> bool`
  — new shell state; true means "under the cap, allow another lap".
- `final_verify_spin_gate.evaluate -> output_numeric(operator=lt, target=2)` — the cap
  comparison, matching `spin_gate`'s shape.
- `run_final_tests.on_no -> final_verify_spin_gate` — redirected edge, was `continue_work`.
- `count_final.on_no -> final_verify_spin_gate` — redirected edge, was `continue_work`.

### Call Path

- `continue_work` → `final_verify` → `run_final_tests` → `continue_work` — the unguarded
  cycle this issue closes; traversed 45 times in the observed run.
- `run_final_tests` → `final_verify_spin_gate` → `continue_work` — the new under-cap path.
- `run_final_tests` → `final_verify_spin_gate` → `summarize_partial` — the new at-cap path.
- `count_final` → `final_verify_spin_gate` — the second redirected edge.
- `select_step` → `check_step_halt` → `spin_gate` — the **existing** ENH-2585 guard, shown
  for contrast: it is unreachable from `run_final_tests`, which is the whole defect.
- `select_step` → `rm -f continue-work-spin-counter.txt` — the reset at
  `general-task.yaml:253` that makes a shared counter file unusable for this guard.
- `check_provisional_markers` → `git diff --name-only $BASELINE_REF` — the existing
  `baseline-ref.txt` machinery the new gate reuses for its no-file-changed condition.
- `load_and_validate` (`scripts/little_loops/fsm/validation/structural_rules.py:1659`) —
  the validator every built-in loop, including `general-task.yaml`, is run through;
  it is what the `TestValidatorWarningBudget` reachability ratchet
  (`scripts/tests/test_builtin_loops.py:14475-14603`) calls, and it is what will flag
  `final_verify_spin_gate` as unreachable if the two `on_no` redirects are not wired.

### State contract

**New state `final_verify_spin_gate`** (shell, modeled on `spin_gate` at
`general-task.yaml:296`):

- Counter file: `${context.run_dir}/final-verify-spin-counter.txt`. **Must be distinct from**
  `continue-work-spin-counter.txt` — sharing it makes the two guards clobber each other,
  since `select_step:253` unconditionally deletes that file on every genuine selection.
- Increment-and-compare, `evaluate: output_numeric` / `operator: lt` / `target: 2`.
- `on_yes` → `continue_work` (under the cap, allow another lap).
- `on_no` → `summarize_partial` (at the cap, divert to the ENH-2583 partial-credit chain).
- `on_error` → `continue_work`, matching `spin_gate`'s fail-open posture: a broken guard
  must not itself terminate a healthy run.

**Reset condition — the part that makes N=2 safe.** The counter increments only when the
lap made no progress; any progress resets it to zero. "Progress" is the conjunction from
Expected Behavior, evaluated inside the gate's shell body:

1. `done_counts.total == 0` — read from the `${captured.done_counts.output}` JSON.
2. `continue_result == WORK_COMPLETE` — read from `${captured.continue_result.output}`.
3. No file changed since the previous lap — `git diff --name-only "$BASELINE_REF"` against
   `baseline-ref.txt`, hashed and compared to the previous lap's stored hash.

All three true → increment. Any false → `rm -f` the counter and fall through to
`continue_work`. A lap that legitimately fixed a failing final test therefore never counts
toward the cap.

**Dominance check**: both captured variables must be set on every path reaching the gate.
`done_counts` is captured by `count_done`, `continue_result` by `continue_work` — both
precede `final_verify` on the cycle. Verify this holds on the *first* entry to
`run_final_tests` too (the path that arrives without having cycled), and default defensively
if not.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-20 — based on codebase analysis:_

- **Confirmed current anchors** (`scripts/little_loops/loops/general-task.yaml`, line numbers as of this pass — the issue's original citations have drifted):
  - `spin_gate` state: `:296-307`. Action reads `${context.run_dir}/continue-work-spin-counter.txt` via `cat ... 2>/dev/null || echo 0`; `evaluate: {type: output_numeric, operator: lt, target: 3}`; `on_yes: check_done`, `on_no: summarize_partial`, `on_error: check_done` (fail-open).
  - Counter increment: `select_step:192-198`, only on the `NO_UNCHECKED_STEPS` branch. Counter reset: `select_step:253-254`, `rm -f "$SPIN_COUNTER"` on every genuine `SELECTED_STEP:` — unconditional, confirming the issue's claim that a shared counter file would be clobbered by unrelated progress in the `select_step`/`continue_work` inner loop.
  - `run_final_tests`: `:596-627`, `fragment: shell_exit`, `timeout: 1800`. `on_yes: count_final` (`:625`), **`on_no: continue_work` (`:626`)** — the first edge to redirect.
  - `count_final`: `:629-651`. **`on_no: continue_work` (`:650`)** — the second edge to redirect.
  - `final_verify`: `:553-594`. Prompt-type state, no `capture:` and no `evaluate:` block on the state itself — it does not capture a named variable consumed by a gate.
  - `continue_work`: `:776-846`. `capture: continue_result` (`:837`); `evaluate: {type: output_contains, pattern: "WORK_COMPLETE"}` (`:838-841`); `on_yes: final_verify`, `on_no: select_step`; `max_retries: 3`, `on_retry_exhausted: diagnose` (`:845-846`) — an existing but orthogonal bound that does not detect the unsatisfiable-criterion/no-progress condition this issue targets.
  - `done_counts` is captured once by `count_done` (`capture: done_counts`, gate `evaluate` around `:543-548` on `.total == 0`, `on_yes: final_verify`) and is **not** re-captured by any state on the `final_verify`/`run_final_tests`/`count_final`/`continue_work` cycle — its value is stale from the original `count_done` entry across every subsequent lap.
  - `check_provisional_markers`: `:653-676`. Reads `${context.run_dir}/baseline-ref.txt` and runs `git diff --name-only "$BASELINE_REF" -- .` against it.
- **Design implication for the "no file changed since last lap" condition**: `baseline-ref.txt` is written **once**, at run start, by `check_baseline_tests` (`git rev-parse HEAD > baseline-ref.txt`) — it is a fixed run-start ref, not updated per lap. The proposed `final_verify_spin_gate` cannot reuse `baseline-ref.txt` directly to detect "no file changed *since the previous lap*"; it needs its own per-lap-updated ref (e.g., write the current `git rev-parse HEAD` or a content hash to a separate file each time the gate runs, and diff against the *previous* stored value on the next entry) rather than diffing against the fixed run-start baseline.
- **Test coverage to extend**: `scripts/tests/test_builtin_loops.py` `TestValidatorWarningBudget` (`:14475-14603`, using the `builtin_loops` fixture `:34-40`) ratchets warning categories including `"unreachable"` — a new `final_verify_spin_gate` state must be actually wired into the edge graph (target of `run_final_tests.on_no`/`count_final.on_no`) or it trips this gate. `TestGeneralTaskLoop` already has static dict-shape routing assertions in this exact style for the ENH-2585/ENH-2857 guard (e.g. `check_step_halt.on_no == "spin_gate"` around `:14874-14881`) — the natural model for new `run_final_tests.on_no == "final_verify_spin_gate"` / `count_final.on_no == "final_verify_spin_gate"` assertions.
- **Spin-guard shape precedent (codebase-wide, not just `spin_gate`)**: the same read-increment-write-echo + `output_numeric`/`lt` shape recurs at `refine-to-ready-issue.yaml:670-689` (`check_refine_limit`), `:453-474` (`check_reconcile_limit`), `:390-396` (`check_hedge_attempts`), `loop-composer.yaml:159-166`, `brainstorm.yaml:222-228`, `oracles/plan-node-refine.yaml:215-221`. A documented "Decision Rules › Counter shape" convention (referenced from `refine-to-ready-issue.yaml:454-458,682`) distinguishes this **independent, scoped counter** pattern (own file, own gate state) from `autodev.yaml`'s shared-counter-plus-consume-once-marker layering used for a different, multi-repair-class scenario — `final_verify_spin_gate` should follow the independent-counter convention, consistent with what the issue already proposes.
- **Test-execution pattern for the new gate**: `test_builtin_loops.py:1592-1618` (`_run_check_hedge_attempts` helper + `test_check_hedge_attempts_counts_up_and_gates_at_two`) extracts a counter state's `action`, substitutes `${context.run_dir}`, and runs it via `subprocess.run(["bash", "-c", ...])` twice against the same `run_dir`, asserting the counter progresses `"1"` then `"2"` and gates correctly at the cap — the direct model for testing `final_verify_spin_gate`'s counter progression and cap behavior.

## Implementation Steps

1. **Confirm the diagnosis in the graph.** Re-derive that `spin_gate` is unreachable from
   `run_final_tests`/`count_final`, and that `select_step:253` deletes the counter. Both are
   asserted in Current Behavior; make them a test before changing anything.
2. **Add the state.** Write `final_verify_spin_gate` with its own counter file, cap N=2, and
   the three-condition reset.
3. **Redirect the two edges.** `run_final_tests.on_no` and `count_final.on_no` →
   `final_verify_spin_gate`.
4. **Validate.** `ll-loop validate general-task` — confirm no MR-rule regressions and that
   the new state is reachable and has a terminating path.
5. **Test the bound.** Assert a permanently-failing `run_final_tests` terminates at
   `partial` within a bounded iteration count. Assert the complementary case: a lap that
   changes files resets the counter and is *not* cut off.
6. **Verify.** `python -m pytest scripts/tests/` exits 0.

## Impact

- **Severity**: P1. Not a root cause, but it converts a bounded bug into an unbounded one.
- **Scope**: one new state plus two edge redirects in `general-task.yaml`. Contained.
- **Risk**: a too-aggressive N would cut off legitimate late-stage recovery — cases where
  `continue_work` genuinely does fix a failing final test. Condition 3 (no file changed) is
  what makes N=2 safe: a lap that changed files does not count toward the cap.
- **Test**: assert that a run whose `run_final_tests` can never pass terminates at
  `partial` within a bounded number of iterations rather than running to `max_iterations`.

## Related Key Documentation

- `postmortems/general-task-final-verify-spin-2026-08-20.md` §3
- ENH-2585 — shipped the `select_step`-path spin guard; this is its coverage gap
- ENH-2857 — `check_step_halt` blocker-detection, adjacent to the existing guard
- ENH-2583 — the partial-credit chain this should divert into

## Status

**Open** | Created: 2026-08-20 | Priority: P1


## Session Log
- `/ll:refine-issue` - 2026-08-20T23:06:40 - `eecdcf60-17f0-43fe-a3bb-f00297aad10d.jsonl`
