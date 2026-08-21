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
blocked_by:
- BUG-3269
- BUG-3271
verify_verdict: VALID
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

**Why the existing `circuit:` block was also silent.** `general-task.yaml:27-30` declares
`circuit.repeated_failure` with `window: 3` / `on_repeated_failure: diagnose`, so the loop is
not entirely without a stall mechanism — it simply cannot see this shape.
`StallDetector.check()` (`scripts/little_loops/fsm/stall_detector.py:63-71`) fires only when
the last `window` recorded `(state, exit_code, verdict)` triples are **identical**, i.e. the
same state N times consecutively. On a 3-state cycle the triples rotate
(`continue_work`, `final_verify`, `run_final_tests`, …) and are never identical three in a
row, so the detector never fired across all 45 laps. The non-consecutive variant that *would*
have fired, `recurrent_window`, is unset on this loop (and on every loop in the repo — zero
matches in `scripts/little_loops/loops/`). See Proposed Solution § "Rejected alternative:
`circuit.recurrent_window`" for why enabling it is not the fix.

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
# NOTE: no bash ${VAR} brace form anywhere in this body — see Implementation
# Steps § brace interpolation. Unbraced "$VAR" only.
untracked() { git ls-files -o --exclude-standard -z -- . ':(exclude).loops/'; }
FP=$( { git diff "$BASELINE_REF" -- . ':(exclude).loops/'
        # paths, then their contents — two cheap passes, no temp file
        untracked | sort -z | tr '\0' '\n'
        untracked | sort -z | xargs -0 -r git hash-object
      } | git hash-object --stdin )
```

A shell **function**, not a `CMD="git ls-files …"` string reused twice: the pathspec must
survive as one argument, and a string would rely on word-splitting (which zsh does not do
by default, so the string form silently breaks if the action is ever run under a
non-bash shell).

**Verified empirically** against a throwaway repo whose `.loops/` is deliberately *not*
gitignored — the consuming-project default. `BASELINE_REF` fixed at the run-start commit, as
`check_baseline_tests` writes it:

| Lap shape | Fingerprint | Gate reads it as |
|---|---|---|
| nothing changed | unchanged | no progress ✓ |
| run-dir churn only (`.events.jsonl`, counter, fingerprint files) | unchanged | no progress ✓ |
| new untracked file | changes | progress ✓ |
| **content edit to an already-untracked file** | changes | progress ✓ |
| tracked-file edit | changes | progress ✓ |
| that same edit then committed | unchanged | no progress ✓ (no *new* work) |

The last row is why `BASELINE_REF` must be the fixed run-start ref from `baseline-ref.txt`
and must never be re-resolved to `HEAD` per lap: with a moving baseline, committing the
lap's own work makes the diff go empty and the fingerprint jumps *backwards* to a prior
lap's value — a false no-progress reading on the most productive kind of lap. Confirmed by
reproducing exactly that inversion when the recipe recomputes `git rev-parse HEAD` itself.

The untracked-file listing matters: newly created files are the common shape of forward
progress in this loop and never appear in a tracked-file diff. Both the path list and the
per-path content hashes go into the digest — paths alone miss content edits (below),
hashes alone miss a pure rename.

`xargs -0 -r git hash-object` rather than a `while read` loop with a `$(git hash-object
"$f")` subshell per path: this state is entered on **every** failing lap, and a
per-file fork over a large untracked tree (build output, an un-ignored `node_modules` or
`.venv`) costs thousands of processes per lap. One `git hash-object` invocation hashes the
whole list in order.

**Untracked files must be hashed by content, not just listed by name.** `git ls-files -o
--exclude-standard` emits **paths only**. The modal shape of progress in this loop is
*create a new file in lap 1, refine it in laps 2–3* — those refinements touch no tracked
file and change no path in the listing, so a name-only untracked listing yields an
**identical fingerprint** and the gate counts real work as no-progress, cutting off a
healthy run at the cap. The `git hash-object` per untracked path in the recipe above is
what closes this; it is not optional. (See Impact — this is the primary false-no-progress
mode, not a residual one.)

**The run dir must be pruned by explicit pathspec, not by `--exclude-standard`.** The gate's
own `final-verify-spin-counter.txt` / `final-verify-fingerprint.txt`, plus the per-lap
`dod.md`, `.events.jsonl`, and `verify-output.txt` churn, all live under
`${context.run_dir}` and change on every lap. If any of them reaches the fingerprint, every
lap's fingerprint differs and the guard **silently never fires** — reproducing the exact
defect it exists to fix, with no failing test to signal it.

`--exclude-standard` alone does **not** prune them, outside this repo. This repo's
`.gitignore:81-89` lists `.loops/runs/` et al., but that block is hand-maintained here and is
**not shipped to consuming projects**: `ll-init`'s `_GITIGNORE_ENTRIES`
(`scripts/little_loops/init/writers.py:59-73`) contains no `.loops/` entry of any form.
`rn-refine.yaml:527` already hedges on the same assumption in a comment ("*Normally*
`.loops/runs/` is gitignored so this is a no-op"). In a consuming project that has not
hand-added the rule — the default — `git ls-files -o --exclude-standard` lists every run-dir
artifact and the guard is dead on arrival.

Therefore: pass `':(exclude).loops/'` explicitly on both the `git diff` and the
`git ls-files` pathspec, as in the recipe above. Keep `--exclude-standard` as well (it is
still the right thing for the project's own ignored paths), but it is a complement to the
explicit prune, not a substitute for it. Any edit to this recipe must preserve **both**.

The corresponding test case must use a temp repo that does **not** ignore `.loops/`;
against a repo that does, the "run_dir churn → no reset" assertion passes vacuously and
proves nothing.

### Rejected alternative: `circuit.repeated_failure.recurrent_window`

This is the closest thing to a one-key fix and must be addressed head-on, because
`docs/reference/loops.md:1071-1080` documents `recurrent_window` using **this exact cycle in
this exact loop** as its worked example, and `general-task.yaml` already carries a `circuit:`
block. Adding `recurrent_window: 5` next to the existing `window: 3` would have fired in the
observed run: `(run_final_tests, <exit>, "no")` recurs every lap, and
`executor.py:1960-1975` routes to `on_repeated_failure` once the total count crosses the
threshold. It is nonetheless the wrong mechanism here, for three independent reasons:

1. **It is progress-blind.** The recurrent path builds `rw_triple = (self.current_state,
   stall_exit_code, verdict)` at `executor.py:1967` — note the absence of the progress
   fingerprint that `record()` receives on the consecutive path. So `recurrent_window` counts
   *total* failures over the whole run with no notion of whether the tree changed in between.
   A healthy long run whose final suite legitimately fails five times across five rounds of
   real work is cut off exactly like the pathological one. Avoiding that false positive is
   the entire reason this issue's gate hashes the working tree.
2. **`on_repeated_failure` is a single key shared by both detectors.** There is one target
   (`executor.py:1941` and `:1972` read the same field), so pointing the recurrent fire at
   `summarize_partial` would simultaneously re-point the existing consecutive detector away
   from `diagnose` — a behavior change to an unrelated, working guard.
3. **`diagnose` is the wrong landing.** `general-task.yaml:1019-1030` ends `diagnose` at
   `next: failed`, the failure terminal. This issue's whole point is to land repeated
   no-progress laps in the ENH-2583 partial-credit chain (`summarize_partial` → `partial`),
   preserving the run's completed work.

**Related prior art, also not reusable.** `circuit.repeated_failure.progress_paths` /
`exclude_paths` (`executor.py:1260-1300`) is an existing file-progress fingerprint — an
`(mtime, size)` tuple over an explicit path list, which resets the *consecutive* window on
change (`stall_detector.py:56-60`). It is the same idea as this issue's fingerprint and is
weaker in three ways: `(mtime, size)` misses a same-size content edit, it requires
enumerating paths up front rather than observing the repo, and it feeds only the consecutive
detector — which, per Current Behavior, structurally cannot fire on a 3-state cycle no matter
what the fingerprint says.

**Documentation consequence.** `docs/reference/loops.md`'s worked example uses this cycle
precisely because it was unguarded. Once this gate lands, that example needs a note that
`general-task` now carries a dedicated guard, or a different loop's cycle substituted;
`recurrent_window` remains valid as a generic mechanism. Already tracked in Integration Map ›
Documentation.

### Rejected alternative: the `diff_stall` evaluator

`evaluate_diff_stall()` (`scripts/little_loops/fsm/evaluators.py:619-712`, exposed as the
`diff_stall` evaluator type and the `diff_stall_gate` fragment) implements the same "N
consecutive no-progress laps" semantics and is the closest in-tree analog. **Do not use
it here**, and do not "simplify" the shell gate into it later:

1. `evaluators.py:646` builds `git diff --stat` with **no ref**, so it compares the working
   tree to the *index*. It misses staged changes and committed changes entirely — and this
   loop's laps routinely stage and commit.
2. It never lists untracked paths (`git diff` cannot, by construction), so it has the
   new-file blind spot described above with no way to close it from the YAML side.
3. Its state lives at `.loops/tmp/ll-diff-stall-<md5(scope)>.txt`, keyed by `scope` rather
   than `${context.run_dir}` — concurrent `ll-parallel` runs of this loop collide on one
   counter, unlike every other counter cited in this issue.

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
_Anchors below are the current ones, re-verified 2026-08-20 (third pre-implementation
review). Earlier drafts' pre-drift numbers have been replaced in place rather than
annotated; the drift history is in Codebase Research Findings._

  - new `final_verify_spin_gate` state
  - `run_final_tests.on_no` (`:704`) — currently `continue_work`
  - `count_final.on_no` (`:729`) — currently `continue_work`
  - `context:` block (`:16-25`) — add `max_final_verify_spins: 2` alongside
    `max_step_attempts` (`:25`)
  - `summarize_partial` prompt body (`:927-948`) — currently tells the model the run stopped
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

_Wiring pass added by `/ll:wire-issue`, anchors corrected 2026-08-20 (pre-implementation
review) — the wiring pass's citations predate the anchor drift recorded in Codebase Research
Findings; the numbers below are re-verified against the current file:_
- `scripts/tests/test_general_task_loop.py::test_run_final_tests_routing` (**`:1518`**, assert
  at **`:1521`**; wiring pass cited `:1437-1441`) — **will break**: hard-asserts
  `state["on_no"] == "continue_work"` for `run_final_tests`; update to
  `"final_verify_spin_gate"`. [Agent 2/3 finding]
- `scripts/tests/test_general_task_loop.py::test_count_final_routes_no_to_continue_work`
  (**`:1349-1350`**; wiring pass cited `:1309-1310`) — **will break**: hard-asserts
  `raw_data["states"]["count_final"]["on_no"] == "continue_work"`; update to
  `"final_verify_spin_gate"`, **and rename the test** — the name asserts the old routing and
  becomes false. [Agent 2/3 finding]
  - **The claimed duplicate at `~:1660-1663` does not exist.** There is exactly one
    `count_final.on_no` assertion in the file. Do not go hunting for a second.
  - **Do not sweep up `verify_step.on_no == "continue_work"` (`:403`)** while grepping for
    `"continue_work"` assertions. That is a different, unaffected edge — this issue redirects
    only `run_final_tests.on_no` and `count_final.on_no`. Several other `continue_work`
    assertions (`:191`, `:390-392`, and the `action`-body checks) are likewise unrelated.
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
  between laps → reset to `"0"`; **new untracked file** between laps → reset to `"0"`;
  **edit to the *content* of an already-untracked file** between laps → reset to `"0"` (the
  case a name-only untracked listing misses — see Proposed Solution); run_dir artifacts
  churning between laps (`.events.jsonl`, `dod.md`, the gate's own counter/fingerprint
  files) → **no** reset, i.e. still `"1"` then `"2"`, proving the run-dir prune holds —
  **this case must use a temp repo whose `.gitignore` does NOT list `.loops/`**, or it
  passes vacuously and proves nothing (see Proposed Solution: `ll-init` does not ship that
  ignore rule, so un-ignored is the consuming-project default); no git repo at all → counts
  up against the
  `max_final_verify_spins * 3` cap rather than pinning at `"0"`. [Agent 3 finding, revised
  2026-08-20 pre-implementation review]
- `scripts/tests/test_general_task_loop.py::test_validates_as_fsm` (`:43-47`) — runs
  `load_and_validate` + `validate_fsm` against the real YAML and fails on any ERROR-severity
  finding; safety net for a mis-wired `final_verify_spin_gate` (unreachable, missing
  `on_yes`/`on_no`). No change needed, but will fail loudly on a mis-wire. [Agent 2/3 finding]

### Documentation
- ~~`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the spin-guard rule~~ — **removed from the
  change set.** The 2026-08-21 refine pass searched that file for `continue_work`,
  `final_verify`, `run_final_tests`, `count_final`, `spin_gate`, and "spin"+"cycle" and found
  zero matches; its content is the meta-loop MR-1..MR-14 table (rules for loops that edit
  other loops' artifacts), a different subject from a loop's own internal per-cycle spin
  guard. `general-task` is not a meta-loop. No edit needed here. The two docs below are the
  real ones.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` (`:122`; current mention of `continue_work` at
  `:125-132`) — prose narrates the exact edges being redirected
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- **Anchor drift since last refine pass**: every state's line number cited in this issue's Integration Map/Program Design (from the `2026-08-20T23:06:40` refine pass) has moved in `scripts/little_loops/loops/general-task.yaml`, confirmed by re-reading the file directly:
  - `spin_gate` — cited `:296-307`, now `:327-338` (+31)
  - `select_step` counter increment — cited `:192-198`, now `:226-230` (+34)
  - `select_step` counter reset (`rm -f "$SPIN_COUNTER"`) — cited `:253-254`, now `:285` (+31)
  - `run_final_tests` — cited `:596-627`, now `:635-705`; `on_yes` now `:703`, **`on_no` now `:704`** (cited `:626`) — this is one of the two edges to redirect
  - `count_final` — cited `:629-651`, now `:707-730`; **`on_no` now `:729`** (cited `:650`) — the second edge to redirect
  - `final_verify` — cited `:553-594`, now `:585-633` (`on_error: summarize_partial` at `:633`)
  - `continue_work` — cited `:776-846`, now `:855-925` (`capture` `:916`, `evaluate` `:917-920`, `on_yes`/`on_no`/`on_error` `:921-923`, `max_retries`/`on_retry_exhausted` `:924-925`)
  - `check_provisional_markers` — cited `:653-676`, now `:732-755` (`BASELINE_REF_FILE` read `:734`, `git diff --name-only` `:740`)
  - `summarize_partial` prompt body — cited `:848-862`, now `:927-948`
  - `context:` block / `max_step_attempts` — cited `:24`, now `max_step_attempts: 3` at `:25` (block starts `:16`) — smallest drift, still the correct sibling line for a new `max_final_verify_spins` entry
  - Root cause of the drift: a small (+31 to +34 line) shift through `select_step`/`spin_gate`/`final_verify` from the ENH-2857 `check_step_halt` state (`:307-317`) and its blocker-check block added inside `select_step` (`:242-283`), then a jump to a stable **+78/+79** offset starting at `run_final_tests`, caused by the BUG-3271 `STRIP_DOD`/`strip_stale_final_sections` block now inside `run_final_tests`'s action body (`:646-676`).
- **Documentation citation check**: `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`, cited above as covering "the spin-guard rule," has zero textual overlap with this issue's subject as of this pass — a direct search of that file for `continue_work`, `final_verify`, `run_final_tests`, `count_final`, `spin_gate`, and "spin"+"cycle" returns no matches. Its content is the generic meta-loop MR-1..MR-14 design-rules table (safety rules for loops that edit other loops' artifacts), a different subject from this loop's own internal per-cycle spin guard.
- `docs/guides/LOOPS_REFERENCE.md` — confirmed current mention of `continue_work` at `:125-132` (issue cited `:122`); still does not mention `final_verify`/`run_final_tests`/`count_final`/spin-guard concepts, consistent with the wiring-phase note that this prose needs updating once the new state lands.
- `docs/reference/loops.md` — the `recurrent_window` worked example using this cycle is now at `:1071-1075` (issue cited `:1066-1085`).
- **Test anchor drift** in `scripts/tests/test_general_task_loop.py` (re-derived from direct search, not yet cross-checked line-by-line against issue's wiring-phase citations): `test_final_verify_routes_next_to_run_final_tests` `:1297`, `test_final_verify_routes_error_to_summarize_partial` `:1302`, `test_count_final_routes_no_to_continue_work` `:1349` (issue cited `:1309-1310`/`~:1660-1663`), `test_run_final_tests_routing` `:1518` (issue cited `:1437-1441`), `TestGeneralTaskShellExecutionSpinGate` class `:604`.

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

**Cap semantics — the name is off by one from the lap count, deliberately.** Because first
entry stores the fingerprint and echoes `0`, `max_final_verify_spins: 2` cuts off on the
**third** consecutive byte-identical lap: lap 1 → `0`, lap 2 → `1`, lap 3 → `2`, and
`2 lt 2` is false → `summarize_partial`. That is the intended bound (see Expected Behavior:
"no scenario where a third byte-identical lap produces a different answer"), but the context
key reads as "2 spins allowed". The bounded-termination test must assert **three** identical
laps at the default cap, not two.
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

**On the `count_final.on_no` path the fingerprint is deliberately blind to what that path is
about.** `count_final` fails on `FAILED` markers inside `${context.run_dir}/dod.md`
(`general-task.yaml:707-730`), and the run dir is pruned from the fingerprint by explicit
pathspec (see Proposed Solution). So a lap that only rewrites `dod.md` — including
`final_verify` re-writing its `## Final Verification` section — reads as no-progress and
counts toward the cap. The effective bound on that path is therefore "three laps unless the
**repo** changes."

This is intended, not an accident of the recipe. BUG-3271 was precisely the case of
`final_verify` re-emitting `dod.md` sections lap after lap while changing nothing real; a
fingerprint that counted `dod.md` churn as progress would let that shape spin forever.
Marking a criterion PASSED without touching the repo is not work the gate should reward.

**Dominance: not applicable, by design.** The gate reads no `${captured.*}` variables, so
the `capture-reachability` rule (`scripts/little_loops/fsm/validation/reachability.py`) has
nothing to flag. This was a deliberate simplification — the earlier three-condition draft
referenced `${captured.continue_result.output}`, which is **unset** on the
`count_done.on_yes → final_verify → run_final_tests` path (a first pass that never entered
`continue_work`), and would have required a `:default=` on the ref plus a dominance
argument. Dropping the captured terms removes that class of problem outright. If a future
revision reintroduces a `${captured.*}` reference here, it MUST carry `:default=` — an
un-defaulted ref on an undominated path is a known interpolation failure mode.

**Guard against a git-less run — but do not fail *fully* open.** `check_provisional_markers`
handles the no-git case by exiting early with `skipped: true` (`general-task.yaml:734-738`);
reuse its `BASELINE_REF` resolution and `git rev-parse --git-dir` probe. With no git there is
no fingerprint, so the gate cannot distinguish a productive lap from an identical one — but
echoing a bare `0` forever leaves non-git projects **completely unguarded**, and the observed
trigger (BUG-3269, an unsatisfiable `test_cmd`) is entirely git-independent. `general-task`
sets no `max_iterations` (verified: unset, and the executor's `max_iterations` counts full
loop passes / maintain-mode restarts, not state transitions — `fsm/executor.py:535-556`), so
nothing else bounds the cycle in that case. The fix would land and the identical 45-lap
hang would still be reachable in any non-git consuming project.

Required behavior on the no-git branch: still count laps, unconditionally, against a looser
cap — `max_final_verify_spins * 3` — and divert to `summarize_partial` at that cap. Without
a fingerprint every lap is indistinguishable, so the looser cap is the price of not
false-positiving on a productive run; it is still a bound. Store the count in the same
`final-verify-spin-counter.txt` and skip the fingerprint file entirely on this branch.

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

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- **An existing FSM-level "N consecutive no-progress" primitive already exists** and was not evaluated against by the current Proposed Solution: `evaluate_diff_stall()` (`scripts/little_loops/fsm/evaluators.py:619-712`), exposed as the `diff_stall` evaluator type and wrapped into a reusable `evaluate:` block by the `diff_stall_gate` fragment (`scripts/little_loops/loops/lib/common.yaml:176-188`). It is used live today in `harness-single-shot.yaml:44-54` (`check_stall` state), `harness-plan-research-implement-report.yaml`, and `harness-multi-item.yaml`.
- **Concrete differences from this issue's proposed fingerprint**, confirmed by reading the evaluator body:
  - Comparison basis is `git diff --stat` **text equality** across calls (`current_diff == previous_diff`), not a `git hash-object` content hash.
  - It does **not** include `git ls-files -o --exclude-standard` — `git diff` never lists untracked paths by construction, so a lap whose only change is a newly created file reads as "no change" to this evaluator. This is the same untracked-file blind spot the issue's Expected Behavior section already identifies as a requirement its own fingerprint must satisfy.
  - State persists at `.loops/tmp/ll-diff-stall-<md5(scope)>.txt` / `.count` — a process/filesystem-global cache keyed by `scope`, not `${context.run_dir}` — unlike every other counter cited in this issue (`spin_gate`, `check_hedge_attempts`, `check_reconcile_limit`, `check_refine_limit`), which all live under `${context.run_dir}`.
  - Threshold shape: `max_stall` consecutive identical-diff readings (default 1) before returning `no`, resetting to 0 on any diff change — the same "N consecutive no-progress laps" semantics this issue wants, implemented as a evaluator type rather than inline loop-YAML shell.
  - A repo-wide search for `git hash-object` and `git ls-files -o --exclude-standard` outside this issue's own text returns no other hits in `scripts/little_loops/` or any loop YAML — the content-hash-plus-untracked-files fingerprint this issue proposes has no existing in-tree precedent to model against; `evaluate_diff_stall` is the closest analog and differs in exactly the two ways this issue's design calls out as required.
- **Counter-shape convention, confirmed**: the "independent, scoped counter" shape (own file under `${context.run_dir}`, own gate state, own target) recurs at `spin_gate` (`general-task.yaml:327-338`), `check_hedge_attempts` (`refine-to-ready-issue.yaml:380-401`), `check_reconcile_limit` (`:453-476`), and `check_refine_limit` (`:670-689`) — all four share the identical read-`cat ... 2>/dev/null || echo 0`-increment-write-`printf`-echo body, differing only in counter filename, `target`, and `on_yes`/`on_no` destinations, with `on_error` fail-open in every instance. This is documented as an explicit alternative to `autodev.yaml`'s shared-counter-plus-consume-once-marker layering (`autodev.yaml:1892-1958`, `count_repair_cycle_refine_for_design`/`count_repair_cycle_reconcile`, one shared counter across six repair-class states plus per-issue marker files) — the distinction between the two shapes is written down at `.issues/enhancements/P2-ENH-3248-...md:459-465` ("Counter shape: independent and scoped").
- **`check_provisional_markers` re-confirmed** (`general-task.yaml:732-755`, drifted from the issue's cited `:653-676`) as a third, distinct git-diff usage already in this same loop file: fixed run-start `baseline-ref.txt` (written once by `check_baseline_tests`, `general-task.yaml:71`) diffed with `--name-only` against the current tree — the exact pattern this issue's Proposed Solution already warns not to reuse verbatim, now re-verified at its current anchor.

### Design Revisions (changelog)

One line per decision; the reasoning for each now lives in the body section named after it,
not here. Anchors throughout the issue are the current ones — earlier passes' pre-drift
numbers were replaced in place, with the drift history retained in Codebase Research
Findings.

**Pass 1 — 2026-08-20, pre-implementation review.**

1. Three-condition reset → single fingerprint condition; `done_counts.total == 0` and
   `continue_result == WORK_COMPLETE` dropped. → Expected Behavior § "Why the working-tree
   fingerprint is the *only* condition".
2. Fingerprint is a content hash, not `--name-only`. → Proposed Solution.
3. Cap promoted from "consider" to required, as `context.max_final_verify_spins`.
4. `summarize_partial`'s prompt body added to the change set.

**Pass 2 — 2026-08-20, second pre-implementation review.** All Pass-1 anchors re-verified;
both `blocked_by` entries (BUG-3269, BUG-3271) confirmed `done`, so this is unblocked.

5. Untracked files hashed by **content**, not listed by name — the modal
   create-then-refine progress shape would otherwise read as no-progress. → Proposed
   Solution; Impact (reclassified primary risk).
6. Run-dir artifacts must be excluded from the fingerprint or the guard never fires.
   → Proposed Solution (superseded in Pass 3: the mechanism is an explicit pathspec, not
   `--exclude-standard`).
7. No-git branch counts against `max_final_verify_spins * 3` rather than failing fully
   open. → State contract.
8. Cap off-by-one written down: `max_final_verify_spins: 2` cuts off on the *third*
   identical lap. → State contract § "Cap semantics".
9. `diff_stall` rejected (no-ref diff, untracked blind spot, scope-keyed global cache).
   → Proposed Solution § "Rejected alternative: the `diff_stall` evaluator".
10. Change-set corrections: test anchors `:1518` / `:1349-1350`; no duplicate `count_final`
    assertion exists; `verify_step.on_no` (`:403`) out of scope;
    `test_count_final_routes_no_to_continue_work` needs renaming;
    `HARNESS_OPTIMIZATION_GUIDE.md` dropped for zero topical overlap.

**Pass 3 — 2026-08-20, third pre-implementation review.** Six changes:

11. **Run-dir prune is an explicit `':(exclude).loops/'` pathspec, not `--exclude-standard`**
    — corrects Pass-2 item 6, which rested on `.gitignore:85`, an entry `ll-init` does
    **not** ship (`init/writers.py:59-73`). Consuming projects are un-ignored by default,
    where the Pass-2 recipe made the guard dead on arrival. Test case must use a repo that
    does not ignore `.loops/`. → Proposed Solution.
12. **`circuit.repeated_failure.recurrent_window` evaluated and rejected**, with the reason
    the existing `circuit:` block was silent for all 45 laps. Previously unaddressed despite
    `docs/reference/loops.md` documenting it against this exact cycle. → Current Behavior;
    Proposed Solution § "Rejected alternative: `circuit.recurrent_window`".
13. **Untracked hashing batched** via `xargs -0 -r git hash-object` instead of a per-file
    subshell fork. → Proposed Solution.
14. **Brace-interpolation trap recorded**: no bash `${VAR}` in the action body; it is a
    runtime failure `ll-loop validate` cannot catch, made silent by the gate's fail-open
    `on_error`. → Implementation Steps § 3.
15. **`count_final.on_no` fingerprint blindness stated as intentional** — `dod.md` churn does
    not reset the counter, per BUG-3271. → State contract.
16. Stale anchors replaced in place; the two prior Design Revision sections folded into this
    changelog.
17. **Recipe smoke-tested** rather than reasoned about: all six lap shapes verified in a
    throwaway repo with an un-ignored `.loops/`, results tabulated in Proposed Solution. Two
    findings folded back in — the `untracked()` helper must be a function (a reused string
    breaks under zsh's no-word-splitting), and `BASELINE_REF` must never be re-resolved per
    lap or the fingerprint inverts on the most productive laps.

## Implementation Steps

1. **Confirm the diagnosis in the graph.** Re-derive that `spin_gate` is unreachable from
   `run_final_tests`/`count_final`, and that `select_step:253` deletes the counter. Both are
   asserted in Current Behavior; make them a test before changing anything.
2. **Add the context value.** `max_final_verify_spins: 2` in the `context:` block, next to
   `max_step_attempts` (`general-task.yaml:25`).
3. **Add the state.** Write `final_verify_spin_gate` with its own counter file, its own
   fingerprint file, the cap read from context, and the single fingerprint-based reset.
   Hash untracked-file **contents**, not just their paths; keep both `--exclude-standard`
   **and** the explicit `':(exclude).loops/'` pathspec. Include the no-git branch —
   counting against `max_final_verify_spins * 3`, not pinning at `0`.
   > ⚠ Superseded — earlier drafts of this step said to rely on `--exclude-standard` alone
   > to keep run-dir artifacts out of the fingerprint. That is stale: `ll-init` does not
   > ship a `.loops/` ignore rule (`init/writers.py:59-73`), so in a consuming project the
   > flag prunes nothing and the guard silently never fires. The explicit
   > `':(exclude).loops/'` pathspec is now required on both the `git diff` and the
   > `git ls-files` call. See Proposed Solution.
   - **Use no bash `${VAR}` brace form anywhere in the action body.** The FSM interpolates
     the entire action string — comments included — *before* handing it to bash, so a bare
     `${FP}` is parsed as a namespace path and raises `expected namespace.path` at runtime.
     Write `"$FP"` unbraced, or escape as `$${FP}`. This is a runtime failure, not a
     validation one: `ll-loop validate` will not catch it, and the state's `on_error:
     continue_work` fail-open posture means a broken gate degrades silently back into the
     exact unguarded cycle. The recipe in Proposed Solution is already written in the
     unbraced form; keep it that way.
4. **Redirect the two edges.** `run_final_tests.on_no` and `count_final.on_no` →
   `final_verify_spin_gate`.
5. **Amend `summarize_partial`'s prompt** (`:927-948`) to name the third stop reason:
   repeated no-progress final-verify laps. Without this the operator-facing `summary.md`
   mis-describes every spin-cutoff run.
6. **Validate.** `ll-loop validate general-task` — confirm no MR-rule regressions and that
   the new state is reachable and has a terminating path.
7. **Test the bound.** Assert a permanently-failing `run_final_tests` terminates at
   `partial` after **three** consecutive byte-identical laps at the default cap (see State
   contract § "Cap semantics" for the off-by-one), not by exhausting some outer limit —
   `general-task` sets no `max_iterations`, so there is no outer limit to fall back on.
   Assert the complementary cases: a lap that changes files resets the counter and is *not*
   cut off; a lap that only creates a new untracked file resets it (a tracked-diff-only
   fingerprint would miss this); a lap that only edits the *contents* of an
   already-untracked file also resets it (a name-only untracked listing would miss this).
8. **Verify.** `python -m pytest scripts/tests/` exits 0.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_general_task_loop.py::test_run_final_tests_routing` (**`:1518`**,
  assert at `:1521`) — change `on_no` assertion from `"continue_work"` to
  `"final_verify_spin_gate"`
- Update `scripts/tests/test_general_task_loop.py::test_count_final_routes_no_to_continue_work`
  (**`:1349-1350`**) — change `on_no` assertion from `"continue_work"` to
  `"final_verify_spin_gate"`, and rename the test. There is no second occurrence; leave
  `verify_step.on_no == "continue_work"` (`:403`) and the other `continue_work` assertions
  alone
- Add new routing/shape tests for `final_verify_spin_gate` in
  `scripts/tests/test_general_task_loop.py`, cloned from
  `test_spin_gate_routes_yes_to_check_done_no_to_summarize_partial` (`:366-375`)
- Add a subprocess-driven counter test for the new state's shell action, cloned from
  `_run_check_hedge_attempts` / `test_check_hedge_attempts_counts_up_and_gates_at_two`
  (`scripts/tests/test_builtin_loops.py:1592-1618`); extend it to cover each reset condition
  independently (see Integration Map › Tests for the full case list, including the
  untracked-content and run-dir-prune cases), since no existing precedent covers a
  fingerprint-driven reset
- Update `docs/guides/LOOPS_REFERENCE.md` (`:122`) — note the new `final_verify_spin_gate` hop
  on the `run_final_tests`/`count_final` failure paths
- Update `docs/reference/loops.md` (`:1066-1085`) — note or replace the `recurrent_window`
  worked example, which now overlaps with this dedicated guard

## Impact

- **Severity**: P1. Not a root cause, but it converts a bounded bug into an unbounded one.
- **Scope**: one new state plus two edge redirects in `general-task.yaml`. Contained.
- **Risk**: a too-aggressive N would cut off legitimate late-stage recovery — cases where
  `continue_work` genuinely does fix a failing final test. The working-tree fingerprint is
  what makes N=2 safe: a lap that changed anything does not count toward the cap. **The
  dominant risk is therefore a *false* no-progress reading, and the fingerprint recipe is
  what controls it** — specifically the untracked-file **content** hash. Create-then-refine
  (new file in lap 1, edits in laps 2–3) is the modal shape of progress in this loop, and a
  name-only untracked listing reads every one of those refinements as no-progress. That is
  not a residual risk; it is the primary one, and Proposed Solution's recipe exists to close
  it. Genuinely residual after that: work landing outside the repo, or in a gitignored path.
  Both are out-of-band for this loop's normal operation, and the failure mode is a `partial`
  terminal with a written summary, not a lost run.
- **Coverage limit**: in a **non-git** project the fingerprint is unavailable, so the guard
  degrades to a plain lap counter at `max_final_verify_spins * 3` (see State contract). The
  originally observed trigger (BUG-3269, an unsatisfiable `test_cmd`) is git-independent, so
  this branch is not hypothetical — without it the fix would land and the identical hang
  would remain reachable in any non-git consuming project.
- **Test**: assert that a run whose `run_final_tests` can never pass terminates at `partial`
  after three consecutive byte-identical laps. Note there is **no** `max_iterations` on
  `general-task` to fall back on — it is unset, and the executor's `max_iterations` counts
  full loop passes rather than state transitions (`fsm/executor.py:535-556`), so this gate
  is the only bound on the cycle.
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
- `/ll:verify-issues` - 2026-08-21T04:59:42 - `a341924e-a8a7-4d9a-8ab5-d56e4e233347.jsonl`
- `/ll:refine-issue` - 2026-08-21T04:35:09 - `f4215495-4bea-4ed7-8672-c75bc402ce45.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-21T02:37:31 - `c4d0cb49-2d47-43ee-bd0a-5286b5885739.jsonl`
- `/ll:confidence-check` - 2026-08-21T00:37:10 - `aa6e5584-37de-4177-905b-eaadb9c97749.jsonl`
- `/ll:confidence-check` - 2026-08-21T00:23:22 - `8fa51734-384b-46a2-a10c-bd13c601a684.jsonl`
- `/ll:wire-issue` - 2026-08-20T23:48:54 - `d1c4118b-f3cb-4064-8e75-ddacc30681ce.jsonl`
- `/ll:refine-issue` - 2026-08-20T23:06:40 - `eecdcf60-17f0-43fe-a3bb-f00297aad10d.jsonl`
