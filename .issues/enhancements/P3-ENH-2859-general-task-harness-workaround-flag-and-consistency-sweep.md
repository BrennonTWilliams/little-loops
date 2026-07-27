---
id: ENH-2859
status: done
priority: P3
captured_at: '2026-07-27T16:17:56Z'
completed_at: '2026-07-27T21:22:26Z'
discovered_date: 2026-07-27
discovered_by: capture-issue
labels:
- loops
- general-task
- verification
parent: EPIC-2861
relates_to:
- ENH-2857
- ENH-2858
- ENH-2860
blocked_by:
- ENH-2857
confidence_score: 95
outcome_confidence: 88
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 24
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

## Impact

Prompt-only change confined to `general-task.yaml`'s `check_done`/`final_verify` states;
no execution-path or schema changes. Improves defect-detection fidelity for future
general-task runs by making harness-workaround masking and stale-doc rot visible in the
DoD/final-verification record instead of silently passing.

## Status

Open — refined and wired; unblocked (ENH-2857 is done). Ready for implementation.

## Motivation

Finding 4's fixture would have surfaced Hermes defect 1 a month earlier; Finding 5's
sweep catches invalidated-by-later-work rot that per-criterion verification structurally
cannot see. Both are prompt edits — no new states, no shell.

Known limitation: the harness-workaround flag is still the same agent grading itself,
the weakness this epic elsewhere works around. That's accepted for this prompt-only
scope; the eventual stronger fix is an independent evaluator via FEAT-2711's
`session_mode` machinery (fresh-session judgment for check states).

## Scope Boundaries

In scope: prompt-text edits to `check_done` and `final_verify` in
`scripts/little_loops/loops/general-task.yaml`, plus structural tests in
`scripts/tests/test_general_task_loop.py` asserting the new language is present.
Out of scope: adding a new FSM state, shell-side enforcement, or an independent
(non-self-grading) evaluator — the latter is deferred to FEAT-2711's `session_mode`
machinery per the Motivation section's known limitation.

## Proposed Solution

Extend the `check_done` and `final_verify` prompt actions in
`scripts/little_loops/loops/general-task.yaml`; fold the consistency sweep into
`final_verify` rather than adding a new state. Add structural tests asserting the
instructions are present (test_builtin_loops.py general-task class).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Target states (both prompt-only, no `evaluate`/`on_yes`/`on_no` — verdict is
expressed by editing `dod.md`, consumed downstream by mechanical shell parsers,
so no MR-4 routing branch is needed for this change):**

- `scripts/little_loops/loops/general-task.yaml:312-367` — `check_done`. Add the
  harness-workaround flag as a new bullet under **Step 2 — Delta-scoped criterion
  verification** (line 337), following the existing "For DoD criteria that..."
  bullet style. Suggested trigger condition text: "If the delta (LAST_FILES) touches
  only test files AND a previously-failing verification now passes, OR the diff adds
  an autouse fixture that resets global/module-level state, do NOT mark the criterion
  [x] without also appending a one-line justification noting *why* — a justification
  describing production behavior (e.g. masking/working around a real defect) rather
  than test isolation must leave the criterion unmarked [ ] with a note." Verdict is
  consumed by `count_done` (line 380-441) the same way `## Sample Verification`
  failures already are — no new evaluator field is required.
- `scripts/little_loops/loops/general-task.yaml:452-483` — `final_verify`. Add the
  consistency sweep as new prose before the existing "Append a new section..."
  instruction (~line 464), instructing the worker to (a) grep code/docstrings/comments
  changed or read during this run for count/enumeration claims ("six tools" class) and
  cross-check against the actual current count, and (b) for any module written before
  its corresponding verification doc landed (`docs/hermes-api-verification.md` class),
  diff the code against the doc and reconcile. Failures append to the existing
  `## Final Verification` fenced block with `FAILED — <reason>` exactly as today (line
  464-469), so `count_final` (line 518-540, awk-counts `FAILED` occurrences) picks up
  the failure with no changes needed on the shell side.

> ⚠ Anchor update (`/ll:refine-issue`, 2026-07-27): `general-task.yaml` has grown
> since the anchors above were recorded (ENH-2857/ENH-2860 landed in between,
> both touching this file). Current locations: `check_done` is now at
> `general-task.yaml:393-458` (Step 2 bullet to extend is at line ~423-424,
> the "For DoD criteria that mention or depend on any file in LAST_FILES..."
> bullet), and `final_verify` is now at `general-task.yaml:540-570`
> (insertion point before "Print the full DoD file to stdout." at line ~561).
> `ENH-2857` (the `blocked_by` dependency) is now `done`, so this issue is
> unblocked. Re-verify exact line numbers again before implementing, since
> ENH-2860 may shift them further.

**No local precedent for the workaround-flag language** — grepping
`scripts/little_loops/loops/*.yaml` for `autouse`/`test-only`/`workaround` returns
zero hits outside the issue file itself; this is genuinely new prompt text. The
nearest structural analog for a new fenced justification block is `check_done`'s
existing `## Sample Verification` section (lines 351-359).

**Nearest precedent for the count/enumeration check** is `docs-sync.yaml`'s
`fix_docs` state (`scripts/little_loops/loops/docs-sync.yaml:40-59`, "Update counts
that don't match actual file counts"), which is a separate loop invoking
`ll-verify-docs` (`scripts/little_loops/cli/docs.py`) as its own shell state — not
embedded prose in another prompt, and `general-task.yaml` does not reference
`ll-verify-docs` anywhere. ENH-2859's check is scoped as pure prose folded into
`final_verify`, not a new shell state.

**Structural test pattern to follow** (`TestGeneralTaskLoop`,
`scripts/tests/test_builtin_loops.py:11637-11794`): each new test reads the target
state's `action` string and asserts required substrings, e.g.:
```python
def test_check_done_flags_harness_workarounds(self, data: dict) -> None:
    """check_done must flag test-only diffs / autouse global-state fixtures (ENH-2859)."""
    state = data["states"].get("check_done", {})
    action = state.get("action", "")
    assert "autouse" in action and "justification" in action
```
Add one test asserting `check_done`'s workaround-flag language and one (or two)
asserting `final_verify`'s count/enumeration and doc-reconciliation language,
mirroring existing tests like `test_run_final_tests_reads_baseline_exit` and
`test_continue_work_prompt_detects_oom_exit_code` in the same class.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — `check_done` (line 312-367) and `final_verify` (line 452-483) prompt bodies
- `scripts/tests/test_builtin_loops.py` — `TestGeneralTaskLoop` class (line 11637-11794) — new structural assertions

### Similar Patterns
- `scripts/little_loops/loops/general-task.yaml:351-359` — `## Sample Verification` fenced-block convention, nearest analog for a new justification/flag block
- `scripts/little_loops/loops/docs-sync.yaml:40-59` (`fix_docs` state) — nearest existing "counts that don't match" prose, though implemented as its own shell state calling `ll-verify-docs`, not embedded prompt text

### Tests
- `scripts/tests/test_builtin_loops.py:11637` — `TestGeneralTaskLoop`, add assertions per Proposed Solution → Codebase Research Findings

_Wiring pass added by `/ll:wire-issue`:_
- **Correction to the target above**: `scripts/tests/test_general_task_loop.py` — not `test_builtin_loops.py` — is the dedicated file with existing substring assertions against `raw_data["states"]["check_done"]["action"]` / `["final_verify"]["action"]` (e.g. `TestChange2CheckDoneReconcileAndSampleVerify`, `TestChange8FinalVerifyGate`). `test_builtin_loops.py`'s `TestGeneralTaskLoop` only covers `check_baseline_tests`/`capture_work_exit`/`continue_work` and has never asserted on `check_done`/`final_verify` content — adding the new assertions there would be a stray addition to an unrelated class. Prefer a new class in `test_general_task_loop.py`; optionally mirror in `test_builtin_loops.py` too, but the former is load-bearing.
- New assertions must not break existing substrings in `test_general_task_loop.py`: `"dod.md"`, `"plan.md"`, `"## Sample Verification"`, `"plausibly affected"`, `"LAST_STEP"`, `"LAST_FILES"`, `"## Final Verification"`, and must avoid introducing `"append a"` adjacent to `"sample verification"` (breaks `test_check_done_replaces_not_appends_sample_verification`).
- `test_builtin_loops.py`'s generic `test_all_validate_as_valid_fsm` and `test_general_task_loop.py`'s scoped `test_validates_as_fsm` re-run FSM structural validation on general-task.yaml; both must keep passing (structural only, unaffected by prompt-text content).

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` (~lines 107-132) — narrates the current `check_done`/`final_verify` three-step verification policy in prose; not test-enforced, but will describe stale behavior once the harness-workaround flag and consistency sweep are added unless updated alongside the YAML change.

## Acceptance Criteria

- [x] `check_done` prompt contains the harness-workaround flag rules (test-only diff, autouse global-state fixture, justification requirement)
- [x] `final_verify` prompt contains the count/enumeration consistency check and the code-vs-later-doc reconciliation check
- [x] `ll-loop validate general-task` passes; structural tests added and green in `scripts/tests/test_general_task_loop.py` (the file with existing check_done/final_verify substring assertions, not `test_builtin_loops.py`)

## Resolution

Added the harness-workaround flag as a new bullet in `check_done`'s Step 2 (delta-scoped
criterion verification), and the closing consistency sweep as new prose in `final_verify`
before the existing "Append a new section..." instruction, in
`scripts/little_loops/loops/general-task.yaml`. Both are pure prompt-text additions — no
new states, no shell changes; sweep failures feed the existing `## Final Verification`
`FAILED — <reason>` format already consumed by `count_final`. Added
`TestENH2859HarnessWorkaroundAndConsistencySweep` (6 tests) to
`scripts/tests/test_general_task_loop.py`, and updated
`docs/guides/LOOPS_REFERENCE.md` to describe both additions in the verification-policy
narrative. `ll-loop validate general-task` passes; full suite green except 4 pre-existing
failures on `main` unrelated to this change (`test_no_failure_edge_routes_to_a_success_terminal`,
two `TestSelectStepShellAction` tests, `test_no_prose_dependency_drift_in_repo` — confirmed
via `git stash` before implementing).

## Session Log
- `/ll:manage-issue` - 2026-07-27T21:22:00Z - `0f986a55-aa7a-4af5-9738-3911a3d11406.jsonl`
- `/ll:ready-issue` - 2026-07-27T21:16:22 - `09439c75-b854-4a23-bf3e-5fe5c561f1b4.jsonl`
- `/ll:refine-issue` - 2026-07-27T21:09:09 - `1364ef69-3d20-4292-84bc-fe1627d39068.jsonl`
- `/ll:wire-issue` - 2026-07-27T17:49:37 - `9188e54f-5830-4cf3-b9ff-2c70903a6916.jsonl`
- `/ll:refine-issue` - 2026-07-27T17:46:49 - `f5467fde-e024-4ec9-87d2-6176113f6da9.jsonl`
- `/ll:capture-issue` - 2026-07-27T16:17:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3601f984-5d3e-4c48-a9b5-5cb709fc86b3.jsonl`
