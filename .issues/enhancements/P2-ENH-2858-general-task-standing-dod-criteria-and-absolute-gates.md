---
id: ENH-2858
status: open
priority: P2
captured_at: "2026-07-27T16:17:56Z"
discovered_date: 2026-07-27
discovered_by: capture-issue
labels: [loops, general-task, verification]
parent: EPIC-2861
relates_to: [ENH-2857, ENH-2859, ENH-2860]
blocked_by: [ENH-2857]
---

# ENH-2858: general-task — plan-independent standing DoD criteria and absolute static-analysis gates in define_done

## Summary

`define_done` derives criteria solely from `${context.input}`, so the DoD can only
re-ask the plan's questions (pure PRD → plan → DoD narrowing). Three of the five Hermes
defects fall directly out of this (POSTMORTEM-general-task-verification-gaps.md,
Findings 2–3): a criterion naming a mechanism was satisfied by code violating the
contract (`get_db(db_path)` ignoring `db_path`); a defective criterion was enforced
faithfully (`SKILL.md` at repo root, unreachable in any non-editable install); a
property nobody named was checked by nobody (path traversal in `ll_create_loop`).
Separately, delta-framed static-analysis criteria ("without introducing new errors")
let the run go green with mypy fully red and taught the worker to copy known-broken
`# type: ignore` suppressions into new code.

## Current Behavior

- `define_done` (general-task.yaml, `define_done` state) asks only for criteria derived
  from the task description; no criterion source is independent of the plan.
- Nothing prevents delta-framed lint/type criteria; a permanently-red checker reports
  green and suppression rot propagates.

## Expected Behavior

`define_done`'s prompt requires a fixed `## Standing Criteria` block — explicitly "not
derived from the task description; apply to every changed module" — each tagged `[hard]`:

1. Every parameter of every changed public function is read on every code path
   (Hermes defect 1: accepted-and-discarded parameter).
2. Contract-over-mechanism: any criterion naming a data structure or library
   (`threading.local()`, "a cache", "a lock") must be accompanied by a behavioral
   criterion phrased over inputs and outputs.
3. Any model- or user-supplied string interpolated into a filesystem path, shell
   command, or SQL statement is validated before use (defect 4).
4. *Conditional — only when the task produces an installable package*: any file the
   package must read at runtime is reachable from a built artifact, verified by
   building a wheel and importing from it in a tmpdir, not an editable install
   (defect 2). Phrase conditionally so it isn't unsatisfiable noise for script/doc tasks.
5. No module carrying a `PROVISIONAL` / `TODO` / `GUESS` / `REPLACE BEFORE SHIPPING`
   marker survives the run without removal or an explicit deferral criterion (defect 5).
   **Implement this one as a mechanical shell grep over changed files, not (only) as
   a prose criterion the checker LLM applies** — the epic's own thesis is that LLM
   self-verification launders failures, and a marker grep needs no judgment. Two
   implementation constraints:
   - **Placement**: `final_verify` is a `check_semantic` LLM state — a shell grep
     cannot live inside it. Put the grep in a small dedicated shell state (or fold it
     into the existing `count_final`/`run_final_tests` shell path) that runs before
     `summarize_success`, routing to the partial chain on a hit.
   - **"Changed files" needs a mechanical baseline**: the loop records no starting
     git ref, and a whole-tree grep would fire on pre-existing markers in repos the
     run doesn't own (the same grandfathering problem in reverse). Capture
     `git rev-parse HEAD` (plus the dirty-tree file list) at loop init and grep only
     files changed since that baseline. When not in a git repo, degrade to
     skip-with-a-note — general-task must stay repo-agnostic per the decoupling
     constraint below.

   Criteria 1–3 genuinely require LLM judgment and stay as prompt criteria;
   criterion 4's wheel-build-and-import check is likewise mechanically verifiable
   (shell) when it applies.

Plus absolute static-analysis framing: lint/type criteria must be phrased "exits 0",
never "no new errors"; where a legacy baseline must genuinely be tolerated, it must be
an enumerated allowlist checked into the repo (set can only shrink; a new instance of
an old error class still fails).

## Motivation

The loop is rigorous about verifying the wrong things because its only source of "the
right things" is a plan that may never have named them. These standing criteria are
cheap, mechanical, task-agnostic, and each is derived from an actual shipped defect.

## Constraints

- Per feedback_general_purpose_loop_decoupling: `general-task` is a general-purpose
  loop — the standing criteria must remain task- and language-agnostic (they are; the
  wheel criterion is conditional, the marker-grep and parameter checks are universal).
- Do NOT change `run_final_tests`' baseline-compare (ENH-2244) — that delta gate for
  the *test suite* protects against pre-existing failures in repos the run doesn't own.
  The absolute framing applies to DoD lint/type criteria over the run's *own* changed code.
- Do not attempt a general "disagree with the spec" mechanism; the conditional
  wheel-reachability criterion covers defect 2's actual failure mode.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/general-task.yaml` — `define_done` prompt gains the "## Standing Criteria" block and exits-0 phrasing requirement; new shell state (baseline git-ref capture + changed-files marker grep) inserted before `summarize_success`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/proof-first-task.yaml` — wraps `general-task` as a sub-loop; verify the new state doesn't change the outer wrapper's expected terminal/capture contract [Agent 1 finding]
- `scripts/little_loops/loops/spike-gate.yaml` — also invokes `general-task` as a nested loop; same check [Agent 1 finding]
- `scripts/little_loops/fsm/validation.py` — MR-1/MR-3/MR-7/MR-9/MR-11 lint rules will apply to the new shell state (bash escaping, `${context.run_dir}` artifact isolation, unsafe interpolation) [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — "Define Done" and the `final_verify` → `run_final_tests` → `count_final` → `summarize_success` narrative need updating for the Standing Criteria block and the new grep-gate state [Agent 2 finding]
- `CHANGELOG.md` — every prior `general-task` behavioral change (ENH-2244, ENH-2365, ENH-2575, etc.) has its own entry; add one under a concrete released version, never `[Unreleased]` (`feedback_changelog_no_unreleased`) [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_general_task_loop.py` — add a new `TestENH2858...` class (existing convention: one class per landed change) asserting: (1) `define_done.action` contains `"## Standing Criteria"` and the five fixed criteria; (2) lint/type criterion phrasing asserts `"exits 0"` is present and delta-framed `"no new errors"` language is absent; (3) the new baseline-git-ref-capture state exists and writes its marker under `${context.run_dir}`, modeled on `test_check_baseline_tests_writes_baseline_exit_to_run_dir`; (4) the new grep-gate shell state greps only files changed since the baseline ref and correctly skips-with-a-note outside a git repo — needs new `git init`/`git commit`/`git diff` fixture scaffolding, no existing analog for this piece [Agent 3 finding]
- `scripts/tests/test_general_task_loop.py::test_count_final_routes_yes_to_summarize_success` (appears twice — `TestChange8FinalVerifyGate` and `TestENH2365SummarizeSuccess`) — **will break**: both assert `count_final.on_yes == "summarize_success"` directly; if the new grep-gate state is spliced in between `count_final` and `summarize_success` per the issue's placement, `count_final.on_yes` must repoint to the new state and these two assertions need updating [Agent 3 finding]
- `scripts/tests/fixtures/tier0_traces/general-task-*.json` — locked trace fixtures encode the current state sequence; inserting a new state changes the expected sequence, requiring trace regeneration [Agent 2 + 3 finding]

## Acceptance Criteria

- [ ] `define_done` prompt emits the Standing Criteria block on every run, independent of task text
- [ ] Prompt forbids delta-framed lint/type criteria and mandates exits-0 / enumerated-allowlist framing
- [ ] The `PROVISIONAL`/`TODO`-marker check runs as a shell grep over changed files in a shell state (not inside the `check_semantic` `final_verify` state), scoped to files changed since a baseline git ref captured at loop init, skipping with a note outside a git repo
- [ ] `ll-loop validate general-task` passes; structural test asserts the standing-block instruction is present in the `define_done` action

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — `define_done` state (lines 42-81): its prompt opens with `Your task is: ${context.input}` (line 44) as the sole DoD input; add the fixed Standing Criteria block here, independent of task text. No `capture:` key currently — DoD content only lives in the `dod.md` file it writes.
- `scripts/little_loops/loops/general-task.yaml` — `check_baseline_tests` state (lines 33-40, `initial: check_baseline_tests` at line 4): currently writes `${context.run_dir}/baseline-test-output.txt` and `${context.run_dir}/baseline-exit.txt`; add a sibling git-ref capture here (`git rev-parse HEAD 2>/dev/null || echo ""` → `${context.run_dir}/baseline-ref.txt`), following the same `on_error: define_done` degrade-forward precedent already used for the test-baseline capture.
- `scripts/little_loops/loops/general-task.yaml` — new shell state inserted between `count_final` (lines 518-540) and `summarize_success` (line 542) for the PROVISIONAL/TODO/GUESS marker grep, scoped to `git diff --name-only "$BASELINE_REF" -- .` read from `baseline-ref.txt`, degrading to skip-with-note when `git rev-parse` fails (non-repo). Route `on_no`/hit → `summarize_partial` (line 660), the existing partial-chain entry point (also reached via loop-level `on_max_steps: summarize_partial` at line 9 and `final_verify.on_error: summarize_partial` at line 483).

### Dependent Files (Callers/Importers)
- `run_final_tests` (lines 485-516, uses `fragment: shell_exit`) reads `baseline-exit.txt` written by `check_baseline_tests` and does the delta-compare (`FINAL_EXIT` vs `BASELINE_EXIT`) that ENH-2244 protects and this issue explicitly says NOT to change — this is the pattern the new git-ref capture should mirror mechanically (write-at-init → read-at-gate) without touching the exit-code delta logic itself.
- `count_final` (lines 518-540) is the closest existing internal pattern for "mechanical gate on LLM-authored artifact": it awk-parses `dod.md`'s `## Final Verification` section for `FAILED` lines and routes via `evaluate: {type: output_json, path: ".failed_finals", operator: eq, target: 0}` → `on_yes: summarize_success`, `on_no: continue_work`. The new marker-grep state should use the same `output_json`/`exit_code` mechanical-evaluator shape (per `scripts/little_loops/loops/lib/common.yaml:14-22`'s `shell_exit` fragment), not an LLM judgment.
- `scripts/little_loops/fsm/validation.py:1429-1483` (`_validate_meta_loop_evaluation`) enforces MR-1 (non-LLM evaluator required alongside any `check_semantic`/`llm_structured` state) via `NON_LLM_EVALUATOR_TYPES`; the new marker-grep state's `exit_code`/`output_json` evaluator satisfies this by construction.

### Similar Patterns
- `scripts/little_loops/loops/harness-optimize.yaml` (~line 191-197, `commit_and_log` state) captures `git rev-parse HEAD` post-commit via `capture: last_commit` — same syntactic mechanic (not baseline-compare) for the new init-time ref capture.
- `scripts/little_loops/loops/rl-coding-agent.yaml:82` does an inline (not init-captured) `git diff --name-only HEAD` for a file-list — closest existing "scope to changed files" usage, but ad hoc at evaluation time rather than baseline-captured at init; the new state is the first to combine both (captured baseline + later diff-scoped grep).
- `scripts/little_loops/loops/harness-single-shot.yaml` lines 60-167 (`check_concrete` → `check_semantic` → `check_invariants`) is the canonical MR-1-compliant chain: an `exit_code`-evaluated shell gate before an `llm_structured` gate, followed by another mechanical `output_numeric` gate — model the marker-grep placement (mechanical gate ahead of/replacing prose judgment) after this shape.
- `scripts/little_loops/cli/verify_cli_allowlist.py` (BUG-2764) is the closest existing "enumerated allowlist, not delta" precedent: computes `canonical_set - allowlist_set`, returns `exit_code = 1 if any missing else 0`. No existing mypy/ruff baseline-allowlist file exists in-repo yet — the AC's "enumerated allowlist checked into the repo" requirement has no direct prior art to reuse, only this CLI's set-difference shape to follow.

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestGeneralTaskLoop` class (starting ~line 11637) is the exact test class to extend. It follows a fixture (`data` = `yaml.safe_load(LOOP_FILE.read_text())`) + one-assertion-per-structural-claim shape, e.g. `test_check_baseline_tests_writes_baseline_exit_to_run_dir` asserts `"${context.run_dir}/baseline-exit.txt" in action`. Add analogous tests: `initial` state or `check_baseline_tests` action contains the git-ref write; the new marker-grep state exists, reads `baseline-ref.txt`, and routes to `summarize_partial`; `define_done`'s action contains the Standing Criteria block markers (e.g. a distinctive substring like `"## Standing Criteria"` or `"not derived from the task description"`).
- `scripts/tests/test_fsm_validation.py` — covers `ll-loop validate`-adjacent FSM validation; the AC's "`ll-loop validate general-task` passes" should be exercised here or via a CLI-level test.

### Configuration
- None identified — this is a loop-YAML-only change, no `.ll/ll-config.json` keys are read by `define_done`/`check_baseline_tests` beyond the existing `project.test_cmd` resolution already in `check_baseline_tests` (lines 33-40).

## Root Cause

N/A — this is an enhancement, not a bug; see Current Behavior above for the `define_done` prompt-composition gap (single `${context.input}`-only interpolation, no standing block).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `define_done`'s runtime-surface nudge (lines 72-76, "If the task involves running code... DoD MUST include criteria for that runtime behavior") is itself gated on task text mentioning runtime behavior — it is prose guidance, not an enforced/injected criterion, and remains input-dependent rather than standing. The new Standing Criteria block must be unconditionally injected regardless of this existing conditional text.
- The "partial chain" the AC references resolves concretely to `summarize_partial` (lines 660-681, `action_type: prompt`) → `write_partial_summary` (lines 683-728) → terminal state `partial` (lines 730-735, deliberately distinct from `done`/`failed` per an inline ENH-2825-era comment about sub-loop routing semantics). Any new failure route for the marker-grep gate should point at `summarize_partial`, matching the two other existing entry points (loop-level `on_max_steps` and `final_verify.on_error`).
- No existing FSM loop captures a git ref at init and later scopes a grep to "files changed since that ref" — this is a genuinely new mechanic in this codebase, though it composes cleanly from two existing idioms (`check_baseline_tests`'s write-once-at-init pattern + `rl-coding-agent.yaml:82`'s inline `git diff --name-only` file-list scoping).

## Session Log
- `/ll:wire-issue` - 2026-07-27T17:44:16 - `36180741-eeee-45c6-ba38-1e8c5047aab7.jsonl`
- `/ll:refine-issue` - 2026-07-27T17:43:08 - `1e2ea2ff-18a7-448b-97c6-c9baeddfc25f.jsonl`
- `/ll:capture-issue` - 2026-07-27T16:17:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3601f984-5d3e-4c48-a9b5-5cb709fc86b3.jsonl`
