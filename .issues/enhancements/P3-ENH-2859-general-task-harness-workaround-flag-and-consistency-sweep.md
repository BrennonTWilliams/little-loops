---
id: ENH-2859
status: open
priority: P3
captured_at: "2026-07-27T16:17:56Z"
discovered_date: 2026-07-27
discovered_by: capture-issue
labels: [loops, general-task, verification]
parent: EPIC-2861
relates_to: [ENH-2857, ENH-2858, ENH-2860]
---

# ENH-2859: general-task — flag harness-side workarounds in check_done and add a closing consistency sweep to final_verify

## Summary

Two prompt-only additions from the general-task postmortem (Findings 4–5). (1) In the
Hermes runs, tests were written after the code, from the same spec, by the same agent;
when a test collided with a real production bug the cheapest repair was to change the
harness — an autouse fixture whose docstring accurately diagnosed the bug (thread-local
DB connection reuse across `tmp_path` DBs) was added to conftest.py and suppressed the
symptom for every subsequent run. (2) The plugin grew from 6 to 11 tools and
`plugin.py`/`README.md`/`SKILL.md` all still said "six tools"; verified facts landing in
a later doc (`docs/hermes-api-verification.md`) were never back-propagated into the
earlier-written `_hermes_compat.py`.

## Current Behavior

- `check_done` verifies DoD criteria but treats test-only diffs and new global-state-resetting
  autouse fixtures as neutral; nothing asks whether a fixture compensates for a defect.
- `final_verify` re-verifies criteria only; nothing checks whether new work invalidated
  previously written docs/docstrings/comments, or diffs guess-era code against
  later-landed verification docs.

## Expected Behavior

**check_done additions (Step 2 instructions):**
- If the delta touches only test files while a previously-failing verification now
  passes, OR introduces an autouse fixture resetting global/module-level state, the run
  must record a one-line justification in the DoD; a justification that describes
  *production* behavior rather than test isolation is a failed criterion (defect signal,
  not a test utility).

**final_verify additions (one standing closing check):**
- No documentation, docstring, or comment states a count or enumeration contradicted by
  the code ("six tools" class).
- For any module written before its corresponding verification doc landed, diff the code
  against the doc and reconcile (knowledge back-propagation; the stale-`PROVISIONAL`-vs-docs class).

## Motivation

Finding 4's fixture would have surfaced Hermes defect 1 a month earlier; Finding 5's
sweep catches invalidated-by-later-work rot that per-criterion verification structurally
cannot see. Both are prompt edits — no new states, no shell.

Known limitation: the harness-workaround flag is still the same agent grading itself,
the weakness this epic elsewhere works around. That's accepted for this prompt-only
scope; the eventual stronger fix is an independent evaluator via FEAT-2711's
`session_mode` machinery (fresh-session judgment for check states).

## Proposed Solution

Extend the `check_done` and `final_verify` prompt actions in
`scripts/little_loops/loops/general-task.yaml`; fold the consistency sweep into
`final_verify` rather than adding a new state. Add structural tests asserting the
instructions are present (test_builtin_loops.py general-task class).

## Acceptance Criteria

- [ ] `check_done` prompt contains the harness-workaround flag rules (test-only diff, autouse global-state fixture, justification requirement)
- [ ] `final_verify` prompt contains the count/enumeration consistency check and the code-vs-later-doc reconciliation check
- [ ] `ll-loop validate general-task` passes; structural tests added and green

## Session Log
- `/ll:capture-issue` - 2026-07-27T16:17:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3601f984-5d3e-4c48-a9b5-5cb709fc86b3.jsonl`
