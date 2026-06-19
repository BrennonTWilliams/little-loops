---
id: ENH-2225
title: "general-task \u2014 scope per-step verify_step so whole-suite gates don't\
  \ block every step"
type: enhancement
priority: P3
status: open
relates_to:
- BUG-2127
- BUG-1766
labels:
- general-task
- loops
- verification
- efficiency
captured_at: '2026-06-19T02:56:50Z'
discovered_date: '2026-06-19'
discovered_by: capture-issue
decision_needed: false
learning_tests_required:
- pytest
- pytest-cov
confidence_score: 88
outcome_confidence: 66
score_complexity: 22
score_test_coverage: 15
score_ambiguity: 7
score_change_surface: 22
implementation_order_risk: true
---

# ENH-2225: general-task — scope per-step verify_step so whole-suite gates don't block every step

## Summary

In the built-in `general-task` loop (`scripts/little_loops/loops/general-task.yaml`),
the `verify_step` state runs the **entire** project test command (resolved from
`context.test_cmd` → `project.test_cmd` → bare `pytest`) after each individual step and
gates on its exit code. When that command enforces a **whole-artifact** quality gate —
the canonical case is `pytest --cov-fail-under=N`, which is commonly injected via
`pyproject.toml`'s `[tool.pytest.ini_options] addopts` rather than the command string —
**no individual step can ever pass `verify_step` until the entire codebase is finished**,
because total coverage stays below the threshold during partial implementation. This is a
category error: coverage is a final-artifact criterion (correctly already in the DoD /
`final_verify`), not a per-step criterion.

Observed live in `audit-general-task-20260618T232725.md`: 11 of 34 plan steps were
abandoned after exhausting `max_step_attempts=3` each (~33 wasted iterations), every one
because the full suite reported `Required test coverage of 80% not reached. Total
coverage: 75.91%` while all 140 tests passed. The run hit `max_steps=200` and terminated
`partial` at 34.9% DoD pass rate.

## Current Behavior

`verify_step` (lines ~199–236) resolves a single project-wide test command and runs it
verbatim against the whole tree after every step. A whole-suite gate embedded in that
command (or re-injected by `pyproject.toml` `addopts`) fails for every step regardless of
whether the step's own work is correct. Because `do_work` succeeds and `verify_step`'s
`on_no` is a verdict (not a state failure), the `repeated_failure` circuit never trips;
the only escape is the per-step attempt cap (which abandons the step) or `max_steps`.

A symptom mitigation landed this session: `continue_work` now reads `verify-output.txt`
and is told to recognize a whole-suite gate as *not* a per-step failure (so it stops
appending phantom remediation steps). That reduces thrash but does **not** make the steps
pass — the structural category error remains.

## Expected Behavior

Per-step verification reflects whether *that step's* work is correct, independent of
whole-artifact gates that can only be satisfied once the task is complete. A step whose
own tests/files pass should be markable `[x]` even while project-wide coverage is still
below threshold. Whole-suite gates (coverage thresholds, etc.) continue to be enforced —
but only at DoD-completion time in `final_verify` / `count_final`, where they already
live.

## Motivation

The granular `select_step → do_work → verify_step → mark_done` design exists to let the
loop make incremental, verifiable progress. A per-step gate that can only pass when the
whole task is done defeats that design — it converts every step into an all-or-nothing
check and burns the iteration budget on verify thrash. This is the dominant failure mode
in the audited run and is latent for any project with a coverage gate in `pyproject.toml`
`addopts` (a very common configuration).

## Integration Map

_Added by `/ll:refine-issue` — anchors verified against the current (modified) loop file:_

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — the only implementation file in scope.
  - `verify_step` (lines **199–236**): resolves `CMD` via `${context.test_cmd}` →
    `project.test_cmd` (read from `.ll/ll-config.json` by an inline `python3` block,
    lines 215–221) → bare `pytest` fallback, then `eval "$CMD" > verify-output.txt` and
    gates on exit code via `output_contains: "VERIFY_PASS"`. `on_no: continue_work`
    (line 235) — a **verdict**, not a state failure, which is why the
    `repeated_failure` circuit never trips. This is where per-step scoping / gate
    neutralization (Implementation Steps 1–2) would land.
  - `final_verify` (lines **377–403**): LLM `prompt` state that re-verifies every DoD
    criterion. It does **not** run the resolved test command itself — it instructs the
    model to "read files / run commands". For Implementation Step 3 (whole-suite gate is
    final-only), `final_verify` must be the place the full ungated command actually runs
    so the coverage criterion is still enforced before `done`.
  - `count_final` (lines **405–427**): shell state, counts `FAILED` lines in the
    `## Final Verification` block; `eq 0` → `done`, else `continue_work`.
  - `continue_work` (lines **429–467**): already contains the landed mitigation —
    lines 437–443 instruct the model to classify a "whole-suite gate that no single step
    can satisfy mid-implementation (e.g. … coverage threshold …)" as **not** a per-step
    failure and stop appending remediation steps. This is the symptom mitigation noted in
    Current Behavior; the structural fix is still open.
  - `context.test_cmd` (line **14**, default `""`) and `max_step_attempts` (line 15,
    default `3`) are the relevant tunables. `max_steps: 200` (line 5) is the run cap that
    was hit.

### Dependent / Related States (no change, but in the data flow)
- `do_work` (writes `LAST_FILES:` to `${context.run_dir}/last-files.txt`, consumed by
  `verify_step` line 201 and `check_done` line 267) — the `LAST_FILES` list is the only
  per-step file signal available for Implementation Step 1's "scope to the step's own
  files/tests".
- `mark_done` (lines 238–256) — only reached on `verify_step → on_yes`; this is the
  state starved by the whole-suite-gate category error.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/proof-first-task.yaml` — its `run_impl` state delegates to
  `context.impl_loop` (**default `"general-task"`**) via `loop: "${context.impl_loop}"`,
  passing only `input:` through. **No change required** — it makes no assumptions about
  which internal general-task state runs the test command — but it is the primary wrapper
  that invokes this loop, so the per-step-vs-final gate change must not alter the context
  contract (`test_cmd` stays the same variable name). [Agent 1+2 finding]
- `scripts/little_loops/loops/lib/common.yaml` — source of the `shell_exit` fragment
  (`action_type: shell` + `evaluate.type: exit_code`, lines ~15–22) that the Decision
  Rationale selects for the final test-run state. **No change to this file** (already used
  by 40+ loops), but `general-task.yaml` must add an `import: lib/common.yaml` block to use
  it — see Implementation Steps wiring phase. [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — the `general-task` section has prose that is **already
  stale (BUG-2127) and further broken by Option 3**:
  - Line ~108 — `verify_step` bullet still says "runs `python -m pytest` on any Python
    files listed"; must be rewritten to describe the language-agnostic per-step smoke gate. [Agent 2 finding]
  - Line ~117 — `final_verify` paragraph describes it as a pure LLM DoD re-verification;
    must reflect that the final gate now runs the resolved whole-suite test command. [Agent 2 finding]
  - Line ~122 — per-step/terminal iteration-count math changes if a new shell state is
    inserted between `final_verify` and `count_final`. [Agent 2 finding]

### Tests
- `scripts/tests/test_builtin_loops.py` — built-in loop validation/structure tests
  (576 edits in the last 7 days; the natural home for a regression test asserting
  `verify_step` does not gate on a whole-suite coverage threshold).
- No fixture project with a coverage gate exists in-repo (see finding below) — Success
  Metric #1 will need one constructed.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_general_task_loop.py` — **the dedicated test file for
  `general-task.yaml`** (not `test_builtin_loops.py`, which only confirms the loop name is
  in the built-in enumeration). This is where the Option 3 structural tests live and break:
  - `TestChange8FinalVerifyGate` (lines ~935–985) — **WILL BREAK** if a new shell state
    (e.g. `run_final_tests`) is inserted into the `count_done → final_verify → count_final`
    chain: `test_count_done_routes_yes_to_final_verify` (line 938) asserts
    `count_done.on_yes == "final_verify"`; `test_final_verify_routes_next_to_count_final`
    (line 944) asserts `final_verify.next == "count_final"`; `test_final_verify_action_type_is_prompt`
    (line 941) asserts `final_verify` is a `prompt` state. Update these for the chosen wiring. [Agent 1+3 finding]
  - `test_verify_step_evaluate_is_output_contains` (line 341) — asserts `verify_step.evaluate.type == "output_contains"` and `pattern == "VERIFY_PASS"`; **breaks if the evaluator type changes** to `exit_code`. Option 3 should keep `verify_step` on `output_contains`/`VERIFY_PASS` to preserve this. [Agent 2+3 finding]
  - `TestVerifyStepShellAction` (lines ~426–454, three tests) — exercise the empty/non-Python `LAST_FILES` → `VERIFY_PASS` paths via `_load_state_script("verify_step")` + `_bash(...)`. **Survive** (LAST_FILES mechanism preserved) but verify they still test the intended smoke-gate contract, not a trivial pass. [Agent 2+3 finding]
  - `test_expected_states_present` (line 52) uses `issubset`, so it does **not** break if a new state is added — but the `diagnose` prompt's hardcoded state list must still be updated (see Configuration). [Agent 2 finding]
  - **New tests to write**: a `TestENH2225FinalOnlyGate` class asserting `verify_step` does
    NOT resolve `${context.test_cmd}`/read `ll-config.json`, and that the final-only gate DOES
    run the resolved test command; plus a `TestRunFinalTestsShellAction` exercising the new
    final shell state's exit-code pass/fail (pattern: `TestCountFinalShellScript` ~line 1021). [Agent 3 finding]
- `scripts/tests/test_fsm_interpolation.py` — `test_general_task_check_done_safe_with_empty_captured` (line ~757) tests safe interpolation with empty captured context. If Option 3 puts `${context.test_cmd}` into `final_verify`/a new shell state's action, add an analogous `test_general_task_final_verify_safe_with_empty_context` to `TestBypassSafeInterpolation`. [Agent 3 finding]

### Configuration / Key Finding
- **This repo's own `scripts/pyproject.toml` (`[tool.pytest.ini_options] addopts`, lines
  136–142) sets `--cov=little_loops` and `--cov-report=…` but NOT `--cov-fail-under`.**
  So the canonical failure mode does *not* reproduce against little-loops itself — the
  audited failure came from the target project (`little-loops-hermes`), whose
  `pyproject.toml` injected a `--cov-fail-under=80` gate via `addopts`. The implementer
  must construct/point at a fixture project that sets `--cov-fail-under` to validate the
  fix; running `general-task` in this repo will not surface the bug.
- For the pytest-specific neutralization direction (Implementation Step 2): `-o addopts=`
  clears config-sourced `addopts`, and `--no-cov` (pytest-cov) disables coverage entirely
  — both are the externally-assumed behaviors recorded in `learning_tests_required`
  (`pytest`, `pytest-cov`; neither yet proven in the Learning Test Registry).

_Wiring pass added by `/ll:wire-issue` — in-file touchpoints in `general-task.yaml`:_
- `context.test_cmd` comment (line **14**, `# verify_step command; empty = read
  project.test_cmd …`) — becomes misleading under Option 3 since `test_cmd` now also drives
  the final whole-suite gate; update the inline comment. [Agent 2 finding]
- `diagnose` state prompt (line **~495**) — contains a **hardcoded state-name list** ending
  `"…count_final, continue_work, or summarize_partial"`. If Option 3 adds a new state (e.g.
  `run_final_tests`), append it to this operator-facing list so the diagnostic prompt stays
  accurate. [Agent 2 finding]
- `import:` block — **absent** in the current file. Add `import:\n  - lib/common.yaml` if the
  final test-run state reuses the `shell_exit` fragment (`test_validates_as_fsm`,
  `test_general_task_loop.py` line 43, will continue to pass once the import resolves). [Agent 2 finding]

## Implementation Steps

These are candidate directions, not a committed design — the right approach needs a
decision (see Open Questions):

1. **Scope verification to the step's own files/tests.** Use the `LAST_FILES` list (and,
   where derivable, the tests covering them) to run only the relevant subset rather than
   the whole suite. Language-agnostic scoping is hard; this may only be tractable for
   known runners.
2. **Neutralize whole-suite gates at the per-step layer only.** Strip/override
   threshold-style flags (e.g. `--cov-fail-under`, including the `addopts`-sourced case
   via `-o addopts=` or `--no-cov` for pytest) when running `verify_step`, while leaving
   the gate intact for `final_verify`. Reintroduces a runner-specific assumption into a
   deliberately language-agnostic state — weigh against goal of generality (see the Fix #1
   rationale comment at verify_step lines ~206–211).
3. **Make whole-suite gating explicit and final-only.** Document that `verify_step` is a
   per-step smoke gate and that whole-artifact criteria belong solely in the DoD; ensure
   `final_verify` runs the full, ungated command so the coverage criterion is still
   enforced before `done`.
   > **Selected:** Option 3 — final-only whole-suite gating preserves the language-agnostic
   > `verify_step` contract (BUG-2127) and reuses the existing `shell_exit` fragment, where
   > Options 1 & 2 both re-introduce the runner-specific logic BUG-2127 removed.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-18.

**Selected**: Option 3 — Make whole-suite gating explicit and final-only.

**Reasoning**: Option 3 is the only direction that satisfies Success Metric #3 (no
language-specific regression). Options 1 (`pytest $FILES` scoping) and 2 (strip
`--cov-fail-under`) both re-introduce the exact runner-specific assumption that BUG-2127
deliberately removed from `verify_step` — the inline Fix #1 comment (general-task.yaml
~206–211) records that `python -m pytest $FILES` produced a false `VERIFY_PASS` for any
non-Python step. Option 3 instead moves the real test-command run to a final-only shell
gate, which can reuse the shared `shell_exit` fragment (`loops/lib/common.yaml`) already
used by 5 other loops (`fix-quality-and-tests`, `incremental-refactor`,
`test-coverage-improvement`, both harness templates), and the per-step-vs-whole-suite
contract is already articulated in `continue_work` (~439–443). Options 1 and 2 also each
require a fixture project with `--cov-fail-under` that does not exist in-repo and (Option
2) unproven pytest-cov Learning Test entries (`-o addopts=`, `--no-cov`); Option 3 carries
the lowest risk and highest existing-pattern reuse.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| 1 — Per-step file/test scoping | 1/3 | 1/3 | 1/3 | 0/3 | 3/12 |
| 2 — Neutralize gates at verify_step | 1/3 | 2/3 | 1/3 | 1/3 | 5/12 |
| 3 — Whole-suite gating final-only | 2/3 | 2/3 | 2/3 | 2/3 | 8/12 |

**Key evidence**:
- Option 1: `LAST_FILES`/`$FILES` plumbing already exists in `verify_step`, but no
  source→test mapping utility exists and `pytest $FILES` was already reverted in BUG-2127
  for the non-Python false-pass failure mode (reuse 1/3).
- Option 2: No loop manipulates `$CMD` after resolution; would be the only one. Documented
  reversal of BUG-2127's language-agnostic principle; pytest-cov flag behaviors unproven in
  the Learning Test Registry (reuse 0/3).
- Option 3: Reuses the `shell_exit` fragment and `test_cmd`-resolution pattern directly for
  a final test-run state; preserves `verify_step` as a language-agnostic smoke gate; only
  the optional verify_step line-filtering sub-point lacks precedent (reuse 2/3).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the Option 3
implementation:_

1. Add `import:\n  - lib/common.yaml` to `general-task.yaml` so the final test-run state can
   reuse the `shell_exit` fragment (`action_type: shell` + `evaluate.type: exit_code`).
2. Wire the new final-only whole-suite gate into the `count_done → final_verify →
   count_final` chain (e.g. a `run_final_tests` shell state running the resolved
   `${context.test_cmd}` before `count_final`), keeping `verify_step`'s `output_contains` /
   `VERIFY_PASS` evaluator unchanged.
3. Update `general-task.yaml` in-file docs: the `context.test_cmd` comment (line 14) and the
   `diagnose` prompt's hardcoded state-name list (line ~495, add any new state).
4. Update `scripts/tests/test_general_task_loop.py` — fix the breaking
   `TestChange8FinalVerifyGate` routing/action-type tests for the new chain; keep
   `test_verify_step_evaluate_is_output_contains` green by preserving the evaluator; add a
   `TestENH2225FinalOnlyGate` class (verify_step does not resolve `test_cmd`; final gate
   does) and a `TestRunFinalTestsShellAction` class (final shell state exit-code pass/fail).
5. If `${context.test_cmd}` lands in `final_verify`/the new shell state, add
   `test_general_task_final_verify_safe_with_empty_context` to `TestBypassSafeInterpolation`
   in `scripts/tests/test_fsm_interpolation.py`.
6. Update `docs/guides/LOOPS_REFERENCE.md` — rewrite the `verify_step` bullet (line ~108,
   also fixing the stale BUG-2127 "python -m pytest" prose), the `final_verify` paragraph
   (line ~117), and the iteration-count math (line ~122).

## Success Metrics

- A general-task run on a project whose `pyproject.toml` sets
  `addopts = "--cov --cov-fail-under=80"` completes individual steps (`verify_step`
  passes for steps whose own work is correct) without abandoning them on the global
  coverage gate.
- The whole-suite coverage criterion is still enforced before terminal `done` (via
  `final_verify` / `count_final`), not silently dropped.
- No regression for non-Python tasks: the chosen fix must not reintroduce a
  language-specific assumption that breaks docs/YAML/JS/shell tasks (cf. BUG-2127).

## Scope Boundaries

- **In scope**: `verify_step` (and, if needed, `final_verify`) in
  `scripts/little_loops/loops/general-task.yaml`; how per-step verification is scoped or
  how whole-suite gates are deferred to completion-time.
- **Out of scope**: The `continue_work` diagnostic mitigation already landed this session;
  per-project config advice (e.g. setting `project.test_cmd`); changes to the FSM executor
  itself.

## Open Questions

- Is per-step file/test scoping feasible language-agnostically, or should the loop only
  attempt it for recognized runners (pytest, etc.) and fall back to whole-suite otherwise?
- Should whole-suite gates be stripped at the verify_step layer (defense-in-depth) even
  though it reintroduces runner-specific logic, or is documenting "verify_step is a
  per-step smoke gate; whole-artifact criteria are DoD-only" the cleaner contract?

## Impact

- **Priority**: P3 — but this is the dominant failure mode in the audited run (11/34
  steps abandoned, ~33 wasted iterations) and is latent for any project with a coverage
  gate in `pyproject.toml` `addopts` (a very common configuration).
- **Effort**: Medium — the change is localized to `verify_step`/`final_verify` in one
  loop YAML, but a design decision is required first (see Open Questions) before
  implementation.
- **Risk**: Medium — the leading fix directions reintroduce runner-specific logic into a
  deliberately language-agnostic state; the chosen approach must not regress non-Python
  tasks (cf. BUG-2127).
- **Breaking Change**: No — whole-suite gates remain enforced at `final_verify`; only the
  per-step gate behavior changes.

## Related

- **BUG-2127** (done) — fixed verify_step being Python-only and the unbounded per-step
  retry spin. Adjacent in the same state, but did not address the whole-suite-gate
  category error.
- **BUG-1766** (done) — general-task convergence/efficiency cluster.
- Source: `audit-general-task-20260618T232725.md` (run 2026-06-18T232725).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-18_

**Readiness Score**: 88/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 66/100 → MODERATE (below 75 threshold)

### Concerns
- Design decision between Options 1, 2, and 3 is explicitly unresolved (`decision_needed: true`); implementation cannot start productively without choosing a direction.
- Learning tests for pytest/pytest-cov behaviors (`-o addopts=`, `--no-cov`) are unproven in the Learning Test Registry — material if Option 2 is chosen.

### Outcome Risk Factors
- **Open decision: resolve before implementing** — Options 1, 2, and 3 have materially different implementations; beginning coding without a chosen direction risks abandoned work.
- **Test fixture project with coverage gate does not exist in-repo** — implement tests first so the verify_step fix is validated against the actual failure mode (`addopts = "--cov-fail-under=80"`). This is the co-deliverable for Success Metric #1.
- **pytest-cov API behaviors unproven** (conditional on Option 2): `-o addopts=` and `--no-cov` have not been exercised via `/ll:explore-api`; confirm before choosing Option 2.

## Session Log
- `/ll:wire-issue` - 2026-06-19T03:27:20 - `2403a95e-6aec-4f51-850f-42597ab89472.jsonl`
- `/ll:decide-issue` - 2026-06-19T03:18:57 - `aebe692c-d6ef-4f0d-a27f-423135e8f4c5.jsonl`
- `/ll:refine-issue` - 2026-06-19T03:03:59 - `d025886e-68c1-41de-8b12-16f2bb5ae5a7.jsonl`
- `/ll:format-issue` - 2026-06-19T03:00:13 - `4a91af29-5615-4435-be44-36af99fe1d58.jsonl`
- `/ll:confidence-check` - 2026-06-18T00:00:00 - `11b1a532-674a-4cfa-9105-80ab242b6601.jsonl`

---

## Status

- **Status**: open
- **Created**: 2026-06-19 via capture-issue
