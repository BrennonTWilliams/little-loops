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
confidence_score: 100
outcome_confidence: 81
score_complexity: 16
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 23
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

**These are evidence of the spin, not usable gate inputs.** Both values were *identical on
every lap* precisely because neither is re-captured anywhere on this cycle — `done_counts`
comes from `count_done`, `continue_result` from `continue_work`'s entry evaluation. That
constancy is what makes them a legible symptom here and a useless (indeed dangerous) signal
for the guard itself; see Expected Behavior for why the fix does not read them.

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
When N consecutive laps leave the working tree **byte-identical** — no change to the
tracked-file diff content and no change to the untracked-file set since the previous lap —
route to a `partial` terminal, never back to `continue_work`.

**Suggested N = 2.** There is no scenario where a third byte-identical lap produces a
different answer.

The counter must be reset only by genuine forward progress (a working-tree mutation), on the
same principle as the `select_step` reset at `:253` — but it must not share the `select_step`
counter file, or the two guards will clobber each other.

### Why the working-tree fingerprint is the *only* condition

An earlier draft of this issue proposed a three-condition conjunction, adding
`done_counts.total == 0` and `continue_result == WORK_COMPLETE`. Both were dropped after
verification against the loop graph; keeping them would have ranged from useless to
actively defeating the guard.

**`done_counts.total == 0` is a frozen value that can permanently disable the gate.**
`done_counts` is captured *only* by `count_done` (`general-task.yaml:470-551`) and is never
re-captured by any state on the `continue_work → final_verify → run_final_tests →
count_final` cycle. Its value is therefore constant across every lap — zero per-lap
information. Worse, as an AND-term it is a live failure mode: `final_verify` has two
entries, `count_done.on_yes` (where `total == 0` holds) and `continue_work.on_yes`
(`WORK_COMPLETE`). On the second path `done_counts` is stale from a `count_done` that may
have had `total > 0`, making the condition **permanently false**. The counter would then
never increment and the new gate would fail open forever — reproducing the exact defect it
exists to fix.

**`continue_result == WORK_COMPLETE` is a tautology on the guarded cycle.** The only edge
from `continue_work` to `final_verify` is `on_yes`, whose evaluate is
`output_contains: WORK_COMPLETE` (`:838-841`). Every lap arriving by that path satisfies it
by construction. On the other entry — `count_done.on_yes → final_verify → run_final_tests`
on a first pass that never entered `continue_work` — `continue_result` is unset entirely,
which is a dominance problem rather than a signal (see State contract).

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
`continue_work` (under the cap) or diverts to `summarize_partial` (at the cap).

**Fingerprinting must hash diff *content*, not file names.** The obvious move —
reusing the `git diff --name-only "$BASELINE_REF"` machinery from
`check_provisional_markers` (`general-task.yaml:653-676`) — is wrong twice over:

1. `baseline-ref.txt` is written **once**, at run start, by `check_baseline_tests`. It is a
   fixed run-start ref, not a per-lap one, so diffing against it says nothing about what
   *this* lap did.
2. Even compared per-lap, `--name-only` is the wrong fingerprint: a lap that re-edits a
   file already present in the changed-name set produces an **identical name list**, which
   the gate would read as "no progress" and count toward the cap.

Use content instead, stored per-lap in its own file (e.g.
`${context.run_dir}/final-verify-fingerprint.txt`) and compared against the previous lap's
value:

```sh
FP=$( { git diff "$BASELINE_REF" -- . ; git ls-files -o --exclude-standard ; } \
      | git hash-object --stdin )
```

The untracked-file listing matters: newly created files are the common shape of forward
progress in this loop and never appear in a tracked-file diff.

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
- `scripts/little_loops/loops/general-task.yaml` — one new state, two edge redirects, one
  context value, one prompt-text update:
  - new `final_verify_spin_gate` state
  - `run_final_tests.on_no` (`:626`) — currently `continue_work`
  - `count_final.on_no` (`:650`) — currently `continue_work`
  - `context:` block (`:24`) — add `max_final_verify_spins: 2` alongside `max_step_attempts`
  - `summarize_partial` prompt body (`:848-862`) — currently tells the model the run stopped
    "either the step budget was exhausted, or final verification failed or timed out". The
    gate adds a **third** stop reason (repeated no-progress final-verify laps); without this
    edit every spin-cutoff run writes an operator-facing `summary.md` that mis-describes why
    it stopped.

### Dependent Files (Callers/Importers)
- None. The change is internal to one loop's state graph; no Python or CLI surface moves.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/validation/reachability.py` — `capture-reachability` rule enforces
  that `${captured.*}` references are dominated by their capturing state. **No longer a
  concern under the revised design**: `final_verify_spin_gate` reads no captured variables,
  so this rule has nothing to check. Retained here as a tripwire — if implementation
  reintroduces a `${captured.*}` reference in the gate, this validator is what will fail, and
  the ref needs `:default=`. [Agent 1 finding, superseded by design revision]
- `scripts/little_loops/fsm/validation/__init__.py` — exports/registers `capture_reachability`
  alongside the other structural rules `load_and_validate` runs. No change needed.
  [Agent 1 finding]

### Similar Patterns
- `general-task.yaml:296` `spin_gate` — the existing guard to model on (shell counter +
  `output_numeric` / `lt` evaluate)
- `general-task.yaml:194` — counter increment on the `NO_UNCHECKED_STEPS` branch
- `general-task.yaml:253` — `rm -f "$SPIN_COUNTER"` reset on genuine progress; the reason
  the existing counter cannot serve this cycle
- `general-task.yaml:653-676` `check_provisional_markers` — reads `baseline-ref.txt` and runs
  `git diff --name-only "$BASELINE_REF" -- .`. Read it for the `BASELINE_REF` resolution +
  not-a-git-repo guard, but **do not copy the `--name-only` form** as the progress
  fingerprint (see Proposed Solution).

### Tests
- `scripts/tests/test_builtin_loops.py` — reachability/graph assertions for built-in loops
- New: assert a run whose `run_final_tests` can never pass reaches a `partial` terminal
  within a bounded iteration count rather than running to `max_iterations`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_general_task_loop.py::test_run_final_tests_routing` (`:1437-1441`) —
  **will break**: hard-asserts `state["on_no"] == "continue_work"` for `run_final_tests`;
  update to `"final_verify_spin_gate"`. [Agent 2/3 finding]
- `scripts/tests/test_general_task_loop.py::test_count_final_routes_no_to_continue_work`
  (`:1309-1310`, duplicated at `~:1660-1663`) — **will break**: hard-asserts
  `raw_data["states"]["count_final"]["on_no"] == "continue_work"`; update both occurrences to
  `"final_verify_spin_gate"`. [Agent 2/3 finding]
- `scripts/tests/test_general_task_loop.py::test_spin_gate_routes_yes_to_check_done_no_to_summarize_partial`
  (`:366-375`) and `test_check_step_halt_routes_yes_to_summarize_partial_no_to_spin_gate`
  (`:356-362`) — existing spin-gate-shape precedent; clone as the model for new
  `TestFinalVerifySpinGate*` routing/shape assertions (`on_yes`/`on_no`/`on_error`/
  `evaluate.type`/`operator`/`target`). [Agent 2/3 finding]
- `scripts/tests/test_builtin_loops.py` `_run_check_hedge_attempts` helper +
  `test_check_hedge_attempts_counts_up_and_gates_at_two` (`:1592-1618`) — subprocess-execution
  model for the new gate's counter shell action: interpolate `${context.run_dir}`, run via
  `subprocess.run(["bash", "-c", ...])` twice against the same `run_dir`, assert progression
  `"1"` then `"2"` and the cap-at-N gate. Extend the pattern with a real temp git repo so the
  fingerprint branch is exercised: same tree twice → `"1"` then `"2"`; tracked-file edit
  between laps → reset to `"0"`; **new untracked file** between laps → reset to `"0"`; no git
  repo at all → fail open at `"0"`. [Agent 3 finding, revised]
- `scripts/tests/test_general_task_loop.py::test_validates_as_fsm` (`:43-47`) — runs
  `load_and_validate` + `validate_fsm` against the real YAML and fails on any ERROR-severity
  finding; safety net for a mis-wired `final_verify_spin_gate` (unreachable, missing
  `on_yes`/`on_no`). No change needed, but will fail loudly on a mis-wire. [Agent 2/3 finding]

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the spin-guard rule; note that a guard must
  cover every cycle back to a re-deliberation state, not just one path

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` (`:122`) — prose narrates the exact edges being redirected
  ("On a passing exit it routes to `count_final`; on failure it routes to `continue_work`" /
  "`count_final` ... any failures → `continue_work`"); goes stale once both `on_no` edges
  point through `final_verify_spin_gate` instead. [Agent 2 finding]
- `docs/reference/loops.md` (`:1066-1085`) — the `recurrent_window` circuit-breaker doc uses
  this exact unguarded cycle (`run_final_tests(fail) → continue_work → select_step → do_work →
  verify_step → run_final_tests(fail) → ...`) as its worked example; note or replace the
  example since `general-task.yaml` now has a dedicated guard for this specific cycle
  (`recurrent_window` itself remains valid as a generic mechanism). [Agent 2 finding]

### Configuration
- Expose the cap as `max_final_verify_spins: 2` in the loop's `context:` block, alongside
  `max_step_attempts` (`general-task.yaml:24`), rather than hard-coding N. This is not
  optional: it matches the existing convention, costs nothing, and lets the
  bounded-termination test set the cap to `1` instead of burning two full laps per test run.

_Wiring pass added by `/ll:wire-issue`:_
- Confirmed no `config-schema.json` change is needed for this: `max_step_attempts`-style caps
  are FSM-loop `context:` block values, not project-config schema fields (zero matches for
  such keys in `config-schema.json`). Exposing N as a context value, if done, is scoped
  entirely to `general-task.yaml`. [Agent 2 finding]

## Program Design

### Signatures

- `final_verify_spin_gate(baseline_ref: str, prev_fingerprint: str) -> int` — new shell
  state; echoes the current consecutive-no-progress count. Takes no captured variables.
- `final_verify_spin_gate.evaluate -> output_numeric(operator=lt, target=${context.max_final_verify_spins})`
  — the cap comparison, matching `spin_gate`'s shape; true means "under the cap, allow
  another lap".
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
  `baseline-ref.txt` resolution the new gate borrows; the gate substitutes a content hash
  for the `--name-only` listing.
- `final_verify_spin_gate` → `summarize_partial` → `write_partial_summary` → `partial` —
  the ENH-2583/ENH-2575 partial-credit chain the at-cap path lands in. `summarize_partial`
  is a `prompt` state whose body enumerates the stop reasons and must be amended.
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
- Fingerprint file: `${context.run_dir}/final-verify-fingerprint.txt`, holding the previous
  lap's working-tree content hash.
- Increment-and-compare, `evaluate: output_numeric` / `operator: lt` /
  `target: ${context.max_final_verify_spins}`.
- `on_yes` → `continue_work` (under the cap, allow another lap).
- `on_no` → `summarize_partial` (at the cap, divert to the ENH-2583 partial-credit chain).
- `on_error` → `continue_work`, matching `spin_gate`'s fail-open posture: a broken guard
  must not itself terminate a healthy run.

**Reset condition — the part that makes N=2 safe.** A single condition, evaluated entirely
inside the gate's shell body from the working tree — no captured variables:

- Compute the current fingerprint (`git diff "$BASELINE_REF" -- .` content plus
  `git ls-files -o --exclude-standard`, piped through `git hash-object --stdin`).
- If it **differs** from the value stored in `final-verify-fingerprint.txt`, the lap made a
  real change: `rm -f` the counter, store the new fingerprint, echo `0`.
- If it **matches**, the lap was byte-identical: increment the counter, echo the new value.
- On first entry the fingerprint file is absent — treat that as "changed", store, echo `0`.
  The gate therefore never fires on the first pass through `run_final_tests`.

A lap that legitimately fixed a failing final test changes the tree and so never counts
toward the cap. This is what makes N=2 safe.

**Dominance: not applicable, by design.** The gate reads no `${captured.*}` variables, so
the `capture-reachability` rule (`scripts/little_loops/fsm/validation/reachability.py`) has
nothing to flag. This was a deliberate simplification — the earlier three-condition draft
referenced `${captured.continue_result.output}`, which is **unset** on the
`count_done.on_yes → final_verify → run_final_tests` path (a first pass that never entered
`continue_work`), and would have required a `:default=` on the ref plus a dominance
argument. Dropping the captured terms removes that class of problem outright. If a future
revision reintroduces a `${captured.*}` reference here, it MUST carry `:default=` — an
un-defaulted ref on an undominated path is a known interpolation failure mode.

**Guard against a git-less run.** `check_provisional_markers` already handles this: if
`baseline-ref.txt` is empty or `git rev-parse --git-dir` fails, it exits early with
`skipped: true`. The gate needs the equivalent — with no git, there is no fingerprint, so
it must fail open (echo `0`, allow the lap) rather than treating every lap as identical and
cutting off a healthy non-git run at N.

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

### Design Revision — 2026-08-20 (pre-implementation review)

Verified the refined design against `general-task.yaml` and the cited tests. All line
citations held (`spin_gate:296-307`, `select_step:192-198`/`:253-254`,
`run_final_tests.on_no:626`, `count_final.on_no:650`, `continue_work:837-846`,
`check_provisional_markers:653-676`; test anchors `test_general_task_loop.py:366,1309,1437`
and `test_builtin_loops.py:1593,1602`). Four changes to the design:

1. **Three-condition reset → single fingerprint condition.** `done_counts.total == 0` is a
   frozen value that can permanently disable the gate on the `continue_work.on_yes` entry
   path; `continue_result == WORK_COMPLETE` is a tautology on the guarded cycle and unset on
   the first-pass path. Both dropped. Rationale in Expected Behavior.
2. **Fingerprint is a content hash, not `--name-only`.** A `--name-only` listing against a
   fixed baseline is identical whether or not the current lap changed anything. Must hash
   diff content plus the untracked-file set.
3. **Cap promoted from "consider" to required**, as `context.max_final_verify_spins`.
4. **`summarize_partial`'s prompt body added to the change set** — it enumerates stop
   reasons and would otherwise mis-describe every spin-cutoff run.

## Implementation Steps

1. **Confirm the diagnosis in the graph.** Re-derive that `spin_gate` is unreachable from
   `run_final_tests`/`count_final`, and that `select_step:253` deletes the counter. Both are
   asserted in Current Behavior; make them a test before changing anything.
2. **Add the context value.** `max_final_verify_spins: 2` in the `context:` block
   (`general-task.yaml:24`), next to `max_step_attempts`.
3. **Add the state.** Write `final_verify_spin_gate` with its own counter file, its own
   fingerprint file, the cap read from context, and the single fingerprint-based reset.
   Include the no-git fail-open branch.
4. **Redirect the two edges.** `run_final_tests.on_no` and `count_final.on_no` →
   `final_verify_spin_gate`.
5. **Amend `summarize_partial`'s prompt** (`:848-862`) to name the third stop reason:
   repeated no-progress final-verify laps. Without this the operator-facing `summary.md`
   mis-describes every spin-cutoff run.
6. **Validate.** `ll-loop validate general-task` — confirm no MR-rule regressions and that
   the new state is reachable and has a terminating path.
7. **Test the bound.** Assert a permanently-failing `run_final_tests` terminates at
   `partial` within a bounded iteration count. Assert the complementary case: a lap that
   changes files resets the counter and is *not* cut off. Assert the untracked-file case
   specifically — a lap that only creates a new file must reset the counter, which a
   tracked-diff-only fingerprint would miss.
8. **Verify.** `python -m pytest scripts/tests/` exits 0.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_general_task_loop.py::test_run_final_tests_routing` (`:1437-1441`)
  — change `on_no` assertion from `"continue_work"` to `"final_verify_spin_gate"`
- Update `scripts/tests/test_general_task_loop.py::test_count_final_routes_no_to_continue_work`
  (`:1309-1310` and the duplicate at `~:1660-1663`) — change `on_no` assertion from
  `"continue_work"` to `"final_verify_spin_gate"`
- Add new routing/shape tests for `final_verify_spin_gate` in
  `scripts/tests/test_general_task_loop.py`, cloned from
  `test_spin_gate_routes_yes_to_check_done_no_to_summarize_partial` (`:366-375`)
- Add a subprocess-driven counter test for the new state's shell action, cloned from
  `_run_check_hedge_attempts` / `test_check_hedge_attempts_counts_up_and_gates_at_two`
  (`scripts/tests/test_builtin_loops.py:1592-1618`); extend it to cover all three reset
  conditions independently, since no existing precedent covers a multi-condition reset
- Update `docs/guides/LOOPS_REFERENCE.md` (`:122`) — note the new `final_verify_spin_gate` hop
  on the `run_final_tests`/`count_final` failure paths
- Update `docs/reference/loops.md` (`:1066-1085`) — note or replace the `recurrent_window`
  worked example, which now overlaps with this dedicated guard

## Impact

- **Severity**: P1. Not a root cause, but it converts a bounded bug into an unbounded one.
- **Scope**: one new state plus two edge redirects in `general-task.yaml`. Contained.
- **Risk**: a too-aggressive N would cut off legitimate late-stage recovery — cases where
  `continue_work` genuinely does fix a failing final test. The working-tree fingerprint is
  what makes N=2 safe: a lap that changed anything does not count toward the cap. The
  residual risk is a *false* no-progress reading — a lap that makes real progress the
  fingerprint cannot see (work landing outside the repo, or a commit that leaves the diff
  against the run-start baseline unchanged). Both are out-of-band for this loop's normal
  operation, and the failure mode is a `partial` terminal with a written summary, not a lost
  run.
- **Test**: assert that a run whose `run_final_tests` can never pass terminates at
  `partial` within a bounded number of iterations rather than running to `max_iterations`.
- **Design note**: the gate reads no captured variables. This is deliberate — see
  Expected Behavior § "Why the working-tree fingerprint is the *only* condition" for why
  the `done_counts` / `continue_result` terms in the original draft were dropped.

## Related Key Documentation

- `postmortems/general-task-final-verify-spin-2026-08-20.md` §3
- ENH-2585 — shipped the `select_step`-path spin guard; this is its coverage gap
- ENH-2857 — `check_step_halt` blocker-detection, adjacent to the existing guard
- ENH-2583 — the partial-credit chain this should divert into

## Status

**Open** | Created: 2026-08-20 | Priority: P1


## Session Log
- `/ll:confidence-check` - 2026-08-21T00:37:10 - `aa6e5584-37de-4177-905b-eaadb9c97749.jsonl`
- `/ll:confidence-check` - 2026-08-21T00:23:22 - `8fa51734-384b-46a2-a10c-bd13c601a684.jsonl`
- `/ll:wire-issue` - 2026-08-20T23:48:54 - `d1c4118b-f3cb-4064-8e75-ddacc30681ce.jsonl`
- `/ll:refine-issue` - 2026-08-20T23:06:40 - `eecdcf60-17f0-43fe-a3bb-f00297aad10d.jsonl`
