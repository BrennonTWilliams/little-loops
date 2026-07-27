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

## Acceptance Criteria

- [ ] `define_done` prompt emits the Standing Criteria block on every run, independent of task text
- [ ] Prompt forbids delta-framed lint/type criteria and mandates exits-0 / enumerated-allowlist framing
- [ ] The `PROVISIONAL`/`TODO`-marker check runs as a shell grep over changed files in a shell state (not inside the `check_semantic` `final_verify` state), scoped to files changed since a baseline git ref captured at loop init, skipping with a note outside a git repo
- [ ] `ll-loop validate general-task` passes; structural test asserts the standing-block instruction is present in the `define_done` action

## Session Log
- `/ll:capture-issue` - 2026-07-27T16:17:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3601f984-5d3e-4c48-a9b5-5cb709fc86b3.jsonl`
