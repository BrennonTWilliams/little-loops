---
id: BUG-2726
title: refine-to-ready-issue diagnose prompt carries no failure evidence, producing
  confabulated wrong-run diagnoses
type: BUG
status: done
priority: P2
captured_at: '2026-07-21T22:10:00Z'
completed_at: '2026-07-22T15:38:03Z'
discovered_date: '2026-07-21'
discovered_by: audit-loop-run
labels:
- loops
- fsm
- diagnostics
relates_to:
- ENH-2469
- ENH-2522
decision_needed: false
reconcile_attempted: true
confidence_score: 97
outcome_confidence: 87
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 22
---

# BUG-2726: refine-to-ready-issue `diagnose` prompt carries no failure evidence, producing confabulated wrong-run diagnoses

## Summary

The `diagnose` state in `scripts/little_loops/loops/refine-to-ready-issue.yaml` is
reached via `on_error` from states like `refine_issue`, but its prompt interpolates
only the issue ID — not the failing state's exit code, stderr, output tail, or the
current run's `run_dir`/event trail. The diagnosis session must therefore guess
what failed.

## Evidence (run `2026-07-21T214941-autodev`)

- `refine_issue` (`/ll:refine-issue ENH-2722 --auto`) exited **143 (SIGTERM)** after
  155,886 ms — an external kill (the FSM runner's timeout path returns 124, not 143).
- The subsequent `diagnose` output analyzed a *different, earlier* run
  (`.loops/.history/2026-07-21T181435-autodev`), asserted "the wrapping autodev loop
  … never reached a refine/ready-issue state for ENH-2722 at all", and never
  mentioned the SIGTERM — even though in the current run the refine session had been
  actively researching ENH-2722 when killed.
- The diagnose prompt text (from `events.jsonl`): "The refine-to-ready-issue loop
  has terminated with an unrecoverable failure. … Report the issue ID being
  refined: ENH-2722 — Identify which state failed …" — no exit code, no stderr, no
  run ID is passed.

## Proposed Fix

Interpolate concrete failure context into the diagnose prompt:

- failing state name and `${prev_result.exit_code}` / last `action_complete` exit code
- stderr/output tail of the failed action (ENH-2469's `stderr_preview` helps here)
- the current run's `run_dir` and run ID, with an instruction to confine analysis to
  that run's `events.jsonl`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The `diagnose` state (`scripts/little_loops/loops/refine-to-ready-issue.yaml:344-356`)
  is a bare `action_type: prompt` with a single unconditional `next: failed`. Its only
  interpolated variable today is `${captured.issue_id.output}`.
- **Already available for free, no executor change needed**: the FSM executor populates
  `self.prev_result = {"output": ..., "exit_code": ..., "state": ...}` right before any
  `on_error` routing decision (`scripts/little_loops/fsm/executor.py:1271-1275` for the
  unconditional-`next:` path, `:1324-1328` for the evaluate/route path), and
  `_build_context()` wires it into the `prev` namespace
  (`scripts/little_loops/fsm/executor.py:2282`). So `${prev.state}` (failing state name),
  `${prev.exit_code}`, and `${prev.output}` all resolve today via
  `scripts/little_loops/fsm/interpolation.py:89-92` — `${prev.state}` alone would satisfy
  "Identify which state failed" without LLM guesswork. `${context.run_dir}` is also
  already populated and used elsewhere in this same loop (e.g. `resolve_issue` line
  39-41, `check_refine_limit` line 279).
- **`prev_result` has no `stderr` key** — only `output`, `exit_code`, `state`. ENH-2469's
  `stderr_preview` (computed at `executor.py:1623`, `result.stderr[-2000:].strip()`) is
  emitted only onto the `action_complete` event in `events.jsonl`
  (`executor.py:1620-1653`) — it is not wired into `InterpolationContext` or
  `prev_result`, so there is no `${prev.stderr}` or `${prev.stderr_preview}` path.
- **Verified against the bug's own evidence**: a positive exit code of `143` (SIGTERM,
  not the FSM runner's internal `-9` SIGKILL signal branch at `executor.py:1276-1281`)
  falls through the ordinary nonzero-exit branch (`executor.py:1283`), which *does*
  populate `prev_result` first — so `${prev.exit_code}` would have resolved to `143` in
  the reported run had the prompt referenced it.
- **Decision point — how to surface stderr** (the one piece not available via `prev`):

**Option A**: Instruct the `diagnose` prompt to read `${context.run_dir}/events.jsonl`
directly, find the last `action_complete` event for the state named in `${prev.state}`,
and use its `stderr_preview`/`output_preview` fields (already populated by ENH-2469, no
other-state changes needed). Touches only the `diagnose` state itself.

**Option B**: Add `capture: <name>` to every state that currently routes to `diagnose`
via `on_error` (`resolve_issue`, `check_lifetime_limit`, `refine_issue`,
`refine_followup`, `confidence_check`, `check_outcome`, `check_scores_from_file`,
`breakdown_issue` — 8+ states), then reference `${captured.<name>.stderr}` in the
diagnose prompt (`captured.<name>.stderr` is populated at `executor.py:1677-1683`, full
untruncated text). Gives structured, pre-parsed stderr but touches every failure-source
state.

> **Selected:** Option B — structured `capture:` beats prompting the diagnose LLM to
> parse `events.jsonl` by hand; see Decision Rationale below.

**Initial author recommendation (superseded, see Decision Rationale below)**: Option A
— a single localized change to the `diagnose` state, reuses the already-completed
ENH-2469 `stderr_preview` field instead of duplicating capture logic across 8 states,
and keeps the diff small for a P2 fix.

### Decision Rationale

**Selected: Option B** (add `capture:` to the 8 failure-source states, reference
`${captured.<name>.stderr}` in the diagnose prompt), overriding this issue's own
initial "Recommended: Option A" note based on codebase evidence gathered via
`/ll:decide-issue`.

Option A's mechanism — instructing the `diagnose` LLM prompt to open
`${context.run_dir}/events.jsonl`, find the last `action_complete` event for
`${prev.state}`, and read its `stderr_preview` — turns out to reproduce the exact
failure mode this bug reports. `action_complete` payloads carry no `state` key
(`executor.py:1620-1653`), so "the last event for state X" must be inferred by an LLM
scanning event order, not a direct field match; retried states additionally emit
multiple `action_complete` entries per state name in the same append-only log. No
loop YAML anywhere in the codebase asks a prompt to do this kind of log correlation —
the two related precedents (`rn-refine.yaml:706`, `auto-refine-and-implement.yaml:844`)
explicitly document choosing a dedicated summary/ledger artifact *instead of*
re-parsing `events.jsonl`. Option A also has no non-LLM evaluator for whether the
prompt picked the right event (MR-1-class gap).

Option B's `capture:` → `${captured.<name>.stderr}` path is deterministic, already
unit-tested (`test_fsm_executor.py:1210`), and needs no LLM-side log correlation. Its
cost is real — 7 of the 8 states need a net-new `capture:` block (only `resolve_issue`
has one today), `confidence_check`'s `loop:` sub-invocation capture shape has no
`.stderr` key at all (`executor.py:967-974`, needs special-casing or a fallback), and
`check_outcome`/`check_scores_from_file` wrap the real subprocess in an inner heredoc
so their outer `stderr` won't surface the inner `ll-issues show` failure without
touching the heredoc script itself — but none of this risk is speculative-LLM risk,
it's ordinary, testable code risk.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-----------:|:----------:|:------------:|:----:|:-----:|
| A (events.jsonl parse) | 0 | 1 | 0 | 2 | 3/12 |
| B (capture: on 8 states) | 1 | 1 | 2 | 2 | 6/12 |

**Evidence for B**: `capture:` → `.stderr` mechanism is unit-tested and deterministic
(`executor.py:1677-1683`, `test_fsm_executor.py:1210`); no LLM-side log parsing
required.

**Evidence against B**: 7 of 8 states need new `capture:` annotations;
`confidence_check`'s sub-loop capture shape lacks `.stderr`; `check_outcome`/
`check_scores_from_file` need their inner heredoc scripts touched to surface the real
subprocess stderr, not just a one-line `capture:` add.

**Evidence for A**: touches only the `diagnose` state; smallest diff.

**Evidence against A**: no precedent for LLM-prompt `events.jsonl` correlation
anywhere in the codebase; `action_complete` events have no `state` key so "last event
for state X" is ambiguous under retries; no non-LLM evaluator possible — the approach
risks reproducing this bug's own confabulation failure mode.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` (Option B):
  - Add `capture: <name>` to the 7 failure-source states that lack one today:
    `check_lifetime_limit` (line 110), `refine_issue` (line 123), `confidence_check`
    sub-loop `on_failure`/`on_error` (lines 188-189), `check_outcome` (line 253),
    `check_refine_limit` (line 294), `check_scores_from_file` (line 327),
    `breakdown_issue` (line 333). `resolve_issue` (line 48) already has one.
  - Special-case `confidence_check`'s sub-loop capture, which has no `.stderr` key
    (`executor.py:967-974`) — fall back to `${prev.output}` in the diagnose prompt
    when `${captured.confidence_check.stderr}` is unavailable.
  - Touch the inner heredoc scripts of `check_outcome` and `check_scores_from_file`
    so their outer `stderr` surfaces the real inner `ll-issues show` failure instead
    of the heredoc wrapper's own exit status.
  - Rewrite the `diagnose` state's prompt (lines 344-356) to interpolate
    `${prev.state}` (failing state name), `${prev.exit_code}`,
    `${captured.<name>.stderr}` (falling back to `${prev.output}` where no `.stderr`
    exists), and `${context.run_dir}`, replacing the current guesswork instruction
    with these concrete values, and instructing the session to confine analysis to
    that run only.

### on_error Sites Routing Into `diagnose` (unaffected by the fix, but define the scope of "any failure" the new prompt must handle)
- `resolve_issue` (line 48), `check_lifetime_limit` (line 110), `refine_issue`
  (line 123), `confidence_check` sub-loop `on_failure`/`on_error` (lines 188-189),
  `check_outcome` (line 253), `check_refine_limit` (line 294), `check_scores_from_file`
  (line 327), `breakdown_issue` (line 333), and the loop-level
  `circuit.repeated_failure.on_repeated_failure: diagnose` (lines 31-34).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/autodev.yaml:144` — invokes `refine-to-ready-issue` as a `loop:` sub-loop; only consumes its terminal `on_success`/`on_failure` signal, not `diagnose`'s prompt text, so unaffected by this fix [Agent 1 finding]
- `scripts/little_loops/loops/recursive-refine.yaml:224` — same sub-loop invocation pattern as `autodev.yaml`; unaffected [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/loops/general-task.yaml` `do_work`/`capture_work_exit`/
  `continue_work` chain (lines 222-249, 586-627) — models exit-code-driven branching
  prompt text (124 = timeout, -9 = OOM, else = generic failure) directly in the prompt
  string, the closest existing example of the target pattern.
- `scripts/little_loops/loops/lib/common.yaml` `loop_failure_diagnose` fragment
  (lines 276-302, used by `rn-refine.yaml`, `rn-plan.yaml`) — has the *same* evidence
  gap as this bug targets; out of scope for this fix (issue is scoped to
  `refine-to-ready-issue.yaml` only) but worth a follow-up issue.
- `scripts/little_loops/loops/rlhf-svg-refine.yaml` (lines 67, 181, 473, 623) —
  `${prev.output}` used directly in prompts without any `capture:` annotation, confirming
  the `prev` namespace works standalone.

### Tests
- `scripts/tests/test_builtin_loops.py` `TestRefineToReadyIssueSubLoop` (line 1078+) —
  existing `test_diagnose_state_exists`, `test_diagnose_routes_to_failed`,
  `test_diagnose_is_not_terminal` (~lines 1300-1309) use a `raw_data` fixture loading the
  un-interpolated YAML; extend with a new test asserting the `diagnose.action` string
  references `prev.exit_code` / `prev.state` / `context.run_dir` (AC3).
- `scripts/tests/test_general_task_loop.py` `test_continue_work_handles_oom_exit_code`
  (~lines 1521-1526) — the raw-string-containment assertion pattern to model the new
  test after (`assert "..." in raw_data["states"]["diagnose"]["action"]`).
- `scripts/tests/test_fsm_executor.py` `TestStderrPreview` (line 9266+) — confirms
  `stderr_preview` truncation/None-handling behavior if Option A's `events.jsonl` read
  is chosen.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py` — no existing test asserts the captured-dict
  *shape* that `_execute_sub_loop` produces for a `capture:`-bearing `loop:` state
  (`executor.py:967-974`, `{"output": ..., "exit_code": None}`, no `stderr` key) or the
  `child_result.terminated_by == "error"` merge path (`executor.py:989-990`). This
  directly underpins step 2's `confidence_check` `.stderr`-less fallback — add a test
  confirming `${captured.confidence_check.stderr}` is absent/empty and
  `${captured.confidence_check.output}` is populated, so the fallback logic in the
  rewritten `diagnose` prompt is exercised against the real shape rather than an
  assumption [Agent 3 finding].
- `scripts/tests/test_builtin_loops.py` `test_diagnose_error_prompt_uses_run_dir`
  (line 1977) — a closer precedent than `test_continue_work_handles_oom_exit_code`
  for the new diagnose-prompt-content test: it asserts a specific `${context.run_dir}`
  substring is present (and a stale hardcoded path is absent) in a prompt state's
  `action` field — model the new `${prev.state}`/`${prev.exit_code}`/`${context.run_dir}`
  assertions after this test's structure [Agent 3 finding].

## Implementation Steps

1. Add `capture: <name>` to the 7 failure-source states in
   `scripts/little_loops/loops/refine-to-ready-issue.yaml` that lack one today:
   `check_lifetime_limit`, `refine_issue`, `confidence_check` sub-loop, `check_outcome`,
   `check_refine_limit`, `check_scores_from_file`, `breakdown_issue` (`resolve_issue`
   already has one).
2. Handle `confidence_check`'s sub-loop capture shape, which has no `.stderr` key
   (`executor.py:967-974`) — special-case a fallback to `${prev.output}` for this state.
3. Touch the inner heredoc scripts of `check_outcome` and `check_scores_from_file` so
   their captured `stderr` reflects the real inner `ll-issues show` failure rather than
   the heredoc wrapper's own exit status.
4. Rewrite the `diagnose` state's `action:` (lines 344-356) to interpolate
   `${prev.state}` (failing state name), `${prev.exit_code}`,
   `${captured.<name>.stderr}` (falling back to `${prev.output}` where unavailable),
   and `${context.run_dir}`, replacing the current guesswork instruction ("Identify
   which state failed... ") with these concrete values, and instructing the session to
   confine analysis to that run only.
5. Extend `scripts/tests/test_builtin_loops.py::TestRefineToReadyIssueSubLoop` with a
   raw-string-containment test asserting the new `diagnose.action` references
   `prev.exit_code`, `prev.state`, and `context.run_dir`, and that the 7 failure-source
   states carry `capture:` blocks (follows the pattern at
   `scripts/tests/test_builtin_loops.py:test_diagnose_error_prompt_uses_run_dir`,
   line 1977).
6. Add a `test_fsm_executor.py` test confirming `_execute_sub_loop`'s captured-dict
   shape (`executor.py:967-974`) has no `stderr` key, so the `confidence_check`
   `${prev.output}` fallback added in step 2 is exercised against the real shape
   (`/ll:wire-issue` finding).
7. Run `python -m pytest scripts/tests/test_builtin_loops.py -k RefineToReadyIssue` and
   `python -m pytest scripts/tests/test_fsm_executor.py -k "StderrPreview or SubLoop"`
   to verify.

## Acceptance Criteria

- [x] All 8 states that route to `diagnose` via `on_error` (`resolve_issue`,
      `check_lifetime_limit`, `refine_issue`, `confidence_check`, `check_outcome`,
      `check_refine_limit`, `check_scores_from_file`, `breakdown_issue`) have a
      `capture:` block, so `${captured.<name>.stderr}` resolves for each
- [x] `diagnose` prompt includes the failing state name (`${prev.state}`), exit code
      (`${prev.exit_code}`), and stderr via `${captured.<name>.stderr}` (falling back to
      `${prev.output}` for `confidence_check`, which has no `.stderr` key)
- [x] `diagnose` prompt includes the current run ID / `run_dir` and instructs the
      session to analyze only that run
- [x] `check_outcome`/`check_scores_from_file`'s captured stderr reflects the real
      inner `ll-issues show` failure, not just the heredoc wrapper's exit status
- [x] A refine kill with exit 143 produces a diagnosis that cites exit 143 (add or
      extend a test/fixture asserting the interpolated prompt content)


## Resolution

Implemented Option B (2026-07-22). `scripts/little_loops/loops/refine-to-ready-issue.yaml`:

- Added `capture:` to the 7 failure-source states that lacked one
  (`check_lifetime_limit`, `refine_issue`, `refine_followup`, `confidence_check`,
  `check_outcome`, `check_refine_limit`, `check_scores_from_file`,
  `breakdown_issue`); `resolve_issue` already captured as `issue_id`. Note
  `refine_followup` (a 9th on_error→diagnose source the issue's AC omitted) was
  captured too for completeness.
- Rewrote the `diagnose` prompt to interpolate `${prev.state}`, `${prev.exit_code}`,
  `${prev.output?}`, `${context.run_dir}`, and a per-source `${captured.<name>.stderr?}`
  block (confidence_check falls back to `${captured.confidence_check.output?}`, as its
  sub-loop capture has no `.stderr` key). Every `${captured.*}` ref uses the `?`
  nullable suffix because only the failing state's capture is populated per run.
  The prompt now names `.loops/.history/` explicitly to confine analysis to the
  current run and instructs that a positive exit code (143 SIGTERM / 137 SIGKILL)
  means an external kill, not an unreached state.
- Made `check_outcome` / `check_scores_from_file` heredocs forward the inner
  `ll-issues show` stderr to `sys.stderr` and `sys.exit(2)` on real failure (verdict
  `error` → `on_error: diagnose`), instead of a bare `json.loads` traceback exiting 1
  (verdict `no` → misroute to `check_decision_needed`).

Supporting change: `scripts/little_loops/fsm/validation.py` `_unguarded_captured_refs`
now treats the `?` nullable suffix as a guard (like `:default=`), since a `?` ref
provably cannot raise `InterpolationError` — this keeps the capture-reachability
ratchet clean for the intentional multi-source `diagnose` state.

Tests: `test_builtin_loops.py::TestRefineToReadyIssueSubLoop` (8 new: capture
presence, prompt interpolation, nullable-ref invariant, run confinement, heredoc
stderr surfacing, and an AC5 interpolation test rendering the real prompt with a
143-SIGTERM context); `test_fsm_executor.py` (sub-loop capture shape has no
`stderr` key); `test_fsm_validation.py` (`?`-nullable guard recognized). Full suite:
15776 passed, 38 skipped.

## Session Log
- `/ll:manage-issue` - 2026-07-22T15:37:18 - `67b88634-4225-48a0-a702-ea88d0295b2d.jsonl`
- `/ll:ready-issue` - 2026-07-22T15:21:41 - `56b39b50-3bd6-4abc-8bfb-a17468fdba18.jsonl`
- `/ll:confidence-check` - 2026-07-22T15:04:56 - `2653913a-f368-4bcb-bc32-f13d389b9078.jsonl`
- `/ll:wire-issue` - 2026-07-22T15:00:04 - `875f5fb8-22d9-406e-a187-4f979d7da6b3.jsonl`
- `/ll:reconcile-issue` - 2026-07-22T14:53:30 - `df2bd37b-4e5c-47b0-b145-19160c6c691e.jsonl`
- `/ll:decide-issue` - 2026-07-22T14:49:10 - `a2b88be3-dba3-4b7c-8292-268acb856f82.jsonl`
- `/ll:refine-issue` - 2026-07-22T14:36:56 - `27fadd5b-ad44-4ce4-91b0-807f37e53f34.jsonl`
- `/ll:verify-issues` - 2026-07-21T23:08:29 - `9fc8185c-278a-4573-8071-af3d44765f41.jsonl`
