---
id: BUG-2594
title: ll_auto_learning_gate_check fragment crashes loop on untrusted ll-auto output
  interpolation
type: BUG
priority: P2
status: done
captured_at: '2026-07-10T00:00:00Z'
completed_at: '2026-07-11T02:18:40Z'
discovered_date: '2026-07-10'
discovered_by: audit-loop-run
source_loop: autodev
source_state: check_learning_gate
relates_to:
- BUG-2595
labels:
- loops
- fsm
- autodev
- rn-remediate
- shell-safety
- learning-gate
confidence_score: 98
outcome_confidence: 80
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 20
---

# BUG-2594: `ll_auto_learning_gate_check` fragment crashes the loop on untrusted ll-auto output interpolation

## Summary

The shared `ll_auto_learning_gate_check` fragment
(`scripts/little_loops/loops/lib/common.yaml`) inlines the captured multi-KB
`ll-auto` output directly into a double-quoted shell `echo`, and supplies **no
`on_error` route**. When `ll-auto`'s output contains shell-breaking characters
(backticks, `$`, unbalanced quotes, code fences — routine in Markdown output),
the interpolated `echo` fails to parse, the shell action exits non-zero for a
*reason unrelated to the gate*, the `output_contains` evaluator returns
`verdict=error`, and — because no `on_error` is defined — the FSM terminates
with `No valid transition`. The loop dies with no `summary.json`, so the run's
real outcome is lost. The fragment is used by both `autodev` and `rn-remediate`.

## Current Behavior

Observed in run `2026-07-11T011831-autodev` (single issue BUG-2588):

1. `implement_current` ran `ll-auto --only BUG-2588`, which halted at
   manage-issue's decision gate and exited 1 (verdict=no). Its output — a
   multi-KB Markdown block full of backticks, `$`, and fenced code — was
   captured as `ll_auto_output`.
2. `implement_current.on_no` routed to `check_learning_gate`.
3. `check_learning_gate` (fragment `ll_auto_learning_gate_check`) ran:
   ```
   if echo "${captured.ll_auto_output.output}" | grep -qF 'LEARNING_GATE_BLOCKED'; then ...
   ```
   The raw capture was substituted into the double-quoted `echo`, breaking shell
   parsing → `action_complete exit=2` with empty output.
4. `evaluate` (`output_contains: GATE_BLOCKED`) returned `verdict=error`.
5. The state has no `on_error` → `loop_complete terminated_by=error error="No
   valid transition" iterations=10`. No `summary.json` was written.

Verbatim from `events.jsonl` (final events):
```
action_complete   exit=2   (empty output)
evaluate          verdict=error
loop_complete     terminated_by=error  error="No valid transition"  iterations=10
```

> ⚠ Anchor `lib/common.yaml:337-346` is stale — the fragment is now at
> `lib/common.yaml:324` (action body at 338-347). See Proposed Solution ›
> Codebase Research Findings for current anchors.

Fragment source (`lib/common.yaml:337-346`) — note the absence of `on_error`,
and that the fragment's own guidance only requires callers to supply
`on_yes`/`on_no`:
```yaml
  ll_auto_learning_gate_check:
    action_type: shell
    action: |
      if echo "${captured.ll_auto_output.output}" | grep -qF 'LEARNING_GATE_BLOCKED'; then
        echo "GATE_BLOCKED"
      else
        echo "OK"
      fi
    evaluate:
      type: output_contains
      pattern: "GATE_BLOCKED"
```

## Expected Behavior

A shell fault while scanning `ll-auto` output must never terminate the loop, and
the gate detection must not depend on interpolating untrusted capture text into
a shell command string:

1. The gate check reads `ll-auto` output from a **file** rather than an inlined
   interpolation, so arbitrary output content cannot break shell parsing.
2. The fragment (or every caller) defines an `on_error` route so a shell fault
   degrades to the next check (`check_impl_auth`) instead of `No valid
   transition`.

## Root Cause

- **File**: `scripts/little_loops/loops/lib/common.yaml`
- **Anchor**: fragment `ll_auto_learning_gate_check` (and its callers
  `autodev.yaml:check_learning_gate`, `rn-remediate.yaml`)
- **Cause**: `${captured.ll_auto_output.output}` is textually substituted into a
  double-quoted `echo` before shell execution. `ll-auto`'s Markdown output
  routinely contains backticks, `$`, and quotes that break the shell, producing
  a non-gate exit code. The `output_contains` evaluator maps that to
  `verdict=error`, and the fragment defines no `on_error`, so the FSM has no
  valid transition and dies.

## Steps to Reproduce

1. Run `autodev` (or `rn-remediate`) on an issue where `ll-auto --only <ID>`
   exits non-zero and prints Markdown containing backticks/`$`/quotes (e.g. a
   decision-gate halt, which emits a fenced "To clear the gate" block).
2. Observe `check_learning_gate` `action_complete exit=2` with empty output.
3. Observe `evaluate verdict=error`, then `loop_complete terminated_by=error
   error="No valid transition"`, and no `summary.json`.

## Proposed Solution

Do not route the multi-KB capture through a shell string at all. Have the
`ll-auto` call site tee stdout to a run-dir file, and have the gate `grep` that
file:

```yaml
# implement_current (and rn-remediate's ll-auto state): tee output to a file
    action: |
      ...
      ll-auto --only "$CURRENT" $SKIP_FLAG 2>&1 | tee "${context.run_dir}/ll_auto_last.txt"
      exit ${PIPESTATUS[0]}
```

```yaml
# ll_auto_learning_gate_check fragment: grep the file, add on_error
    action: |
      if grep -qF 'LEARNING_GATE_BLOCKED' "${context.run_dir}/ll_auto_last.txt" 2>/dev/null; then
        echo "GATE_BLOCKED"
      else
        echo "OK"
      fi
    evaluate:
      type: output_contains
      pattern: "GATE_BLOCKED"
```

Additionally, require `on_error` on every state that uses this fragment (route
to the next check, e.g. `check_impl_auth`), and update the fragment's
`description` contract to state that callers MUST supply `on_error`. Consider a
`ll-loop validate` rule flagging any `output_contains`/`exit_code` state that
interpolates a `${captured.*.output}` value into a shell string without an
`on_error` route.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **The sibling `ll_auto_auth_check` fragment has the IDENTICAL hazard, and it
  is the *next* state after the gate check — so fixing only the learning-gate
  fragment does not close the crash.** `ll_auto_auth_check`
  (`scripts/little_loops/loops/lib/common.yaml:304`) runs
  `if echo "${captured.ll_auto_output.output}" | grep -qiE '401|403|...'` — the
  same untrusted double-quoted `echo` interpolation. In both loops the gate
  check's `on_no` routes to `check_impl_auth`, which uses this fragment. So the
  same multi-KB Markdown capture that breaks the learning-gate `echo` also
  breaks the auth `echo` one state later, and (see next finding) that state also
  lacks `on_error`. **The fix must cover BOTH fragments.**
- **The file-based capture approach fixes both fragments at once and is
  therefore simpler than the per-fragment view suggests:** tee the `ll-auto`
  output to `${context.run_dir}/ll_auto_last.txt` once at each call site, then
  have *both* `ll_auto_learning_gate_check` and `ll_auto_auth_check` `grep` that
  file instead of interpolating `${captured.ll_auto_output.output}`. This
  removes the interpolation hazard from the whole gate→auth chain in one change.
- **Current line anchors (the issue's `lib/common.yaml:337-346` reference is
  stale):** `ll_auto_learning_gate_check` is now at
  `scripts/little_loops/loops/lib/common.yaml:324` (action at 338-347);
  `ll_auto_auth_check` at `:304` (action at 314-322).
- **The FSM engine already supports `on_error` on fragment-based shell states** —
  both loops use it extensively on other states (e.g. autodev
  `check_wire_needed`, rn-remediate `check_impl_auth`'s neighbors), so adding
  `on_error` to the gate/auth states requires no engine change, only YAML.

_Added by `/ll:wire-issue`:_

- **`scripts/little_loops/loops/eval-driven-development.yaml` is a third,
  previously-unlisted caller of `ll_auto_auth_check`** (its `implement` state,
  line 22-25, sets `capture: ll_auto_output`; `check_impl_auth`, line 32-36,
  uses the fragment). It has no learning-gate stage, so only the auth-check
  half of the fix applies, but it still needs the same tee-to-
  `${context.run_dir}/ll_auto_last.txt` treatment on `implement` — otherwise
  the auth-check silently always evaluates `OK` post-fix (file absent → grep
  no-match → non-block), quietly regressing the ENH-2353 auth fast-fail rather
  than crashing.
- **The `${context.run_dir}/*.txt` tee pattern already has direct precedent** —
  `harness-multi-item.yaml:96`, `test-coverage-improvement.yaml` (multiple
  states), and `general-task.yaml:36-37,485` all tee/read run-dir files today,
  confirming the proposed fix mirrors an established convention rather than
  introducing a new one.
- **No existing loop uses `PIPESTATUS[0]`** to preserve exit code through a
  `| tee` pipe (the Proposed Solution's snippet uses it). The closest
  precedent, `general-task.yaml:37`, instead captures `$?` to a file
  immediately after a plain redirect (`> file 2>&1`) and reads it back
  separately — consider that alternative if `PIPESTATUS` portability across
  the loop runner's shell invocation is a concern.
- **The fragment `description:` fields in `lib/common.yaml` (lines 304-312,
  324-336) document the `capture: ll_auto_output` contract in prose** and must
  be updated alongside the action bodies, not just the action bodies alone.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/lib/common.yaml` — `ll_auto_learning_gate_check`
  fragment (grep a file; document `on_error` requirement)
- `scripts/little_loops/loops/autodev.yaml` — `implement_current` (tee output),
  `check_learning_gate` (add `on_error: check_impl_auth`)
- `scripts/little_loops/loops/rn-remediate.yaml` — matching `ll-auto` call site
  + learning-gate state

### Dependent Files (Callers/Importers)
- `grep -rln ll_auto_learning_gate_check scripts/little_loops/loops/` →
  `autodev.yaml`, `rn-remediate.yaml` (both affected)

### Similar Patterns
- `ll_auto_auth_check` fragment (`check_impl_auth`) and any other state reading
  `${captured.ll_auto_output.output}` via inlined shell — audit for the same
  interpolation hazard.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/eval-driven-development.yaml` — a **third,
  previously unlisted consumer** of the `ll_auto_output` capture contract.
  `implement` (line 22-25) runs `ll-auto --priority P1,P2 --quiet` with
  `capture: ll_auto_output`; `check_impl_auth` (line 32-36) uses
  `fragment: ll_auto_auth_check`. This loop has no learning-gate stage, so it's
  only exposed to the `ll_auto_auth_check` half of the fix, not the
  learning-gate half. **If `ll_auto_auth_check` switches to grepping
  `${context.run_dir}/ll_auto_last.txt` without also updating this loop's
  `implement` state to tee to that file, the auth-check silently degrades to
  always-`OK`** (file absent → `grep ... 2>/dev/null` → no match → non-block) —
  a silent regression of the ENH-2353 auth fast-fail, not a crash, so it would
  go unnoticed without an explicit check. `implement` must be added to the
  Files to Modify list alongside `implement_current`/`implement` in
  autodev.yaml/rn-remediate.yaml.
- `scripts/little_loops/loops/lib/common.yaml:304-312,324-336` — the fragment
  `description:` prose for both `ll_auto_auth_check` and
  `ll_auto_learning_gate_check` explicitly documents the
  `capture: ll_auto_output` / `${captured.ll_auto_output.output}` contract in
  text ("Callers MUST set capture: ll_auto_output..."). This description text
  must be rewritten to describe the new file-based contract
  (`${context.run_dir}/ll_auto_last.txt`), not just the action bodies.

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against current code:_

- **`ll_auto_auth_check` is NOT just "similar" — it is the same hazard on the
  crash path.** `scripts/little_loops/loops/lib/common.yaml:304` (action at
  314-322) interpolates `${captured.ll_auto_output.output}` into a double-quoted
  `echo` exactly like the learning-gate fragment. Promote it from "audit" to
  "must fix" and add `capture: ll_auto_output`-file grep + `on_error` here too.
- **Exact caller states and their current routing (all four lack `on_error`):**
  - `scripts/little_loops/loops/autodev.yaml` — `implement_current` (~line 403;
    runs `ll-auto --only "$CURRENT" $SKIP_FLAG` with NO tee-to-file),
    `check_learning_gate` (~line 439; `on_yes: mark_gate_blocked`,
    `on_no: check_impl_auth`, **no `on_error`**), `check_impl_auth` (~line 470;
    `on_yes: abort_env_not_ready`, `on_no: dequeue_next`, **no `on_error`**).
  - `scripts/little_loops/loops/rn-remediate.yaml` — `implement` (~line 493;
    runs `ll-auto --only "$ID" $SKIP_FLAG 2>&1` with NO tee-to-file),
    `check_learning_gate` (~line 590; `on_yes: emit_learning_gate_blocked`,
    `on_no: check_impl_auth`, **no `on_error`**), `check_impl_auth` (~line 607;
    `on_yes: emit_env_not_ready`, `on_no: emit_implement_failed`,
    **no `on_error`**).
- **Suggested `on_error` targets** (route to the fail-open path each loop already
  uses): autodev `check_learning_gate.on_error → check_impl_auth` and
  `check_impl_auth.on_error → dequeue_next`; rn-remediate
  `check_learning_gate.on_error → check_impl_auth` and
  `check_impl_auth.on_error → emit_implement_failed`.

### Tests
- `scripts/tests/test_builtin_loops.py` — add a case feeding `ll-auto` output
  containing backticks/`$`/quotes through the gate and asserting the loop does
  not terminate with `No valid transition`.
- FSM validation test if a lint rule is added.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_fragments.py:2504-2511` —
  `TestLlAutoAuthCheckFragment.test_fragment_action_references_ll_auto_output_capture`
  **will break**, not just "should be audited": it hard-asserts
  `"captured.ll_auto_output.output" in action`, which the file-grep rewrite of
  `ll_auto_auth_check`'s action body removes outright. Update the assertion to
  check the new file-path pattern instead (e.g.
  `"context.run_dir" in action` / `"ll_auto_last.txt" in action`).
- `scripts/tests/test_rn_remediate.py:1932-1937` —
  `test_implement_captures_ll_auto_output` asserts
  `impl.get("capture") == "ll_auto_output"` on `rn-remediate.yaml`'s `implement`
  state. Breaks only if the fix drops the `capture:` attribute entirely when
  switching to tee-based output (verify against the final action shape chosen).
- `scripts/tests/test_builtin_loops.py` — existing **structural** tests need
  new `on_error` assertions added (they currently only assert `on_yes`/`on_no`,
  matching today's bug where `on_error` is absent):
  `test_check_learning_gate_routes_to_auth_check_on_no` (line 2665, autodev),
  `test_rn_remediate_check_learning_gate_falls_through_to_auth` (line 9521).
  `test_fragment_defined_and_matches_marker` (line 9505) may also need revision
  if it starts asserting on the fragment's `action` body content.
- Adversarial-string execution test template: `_run_record` helper
  (`scripts/tests/test_builtin_loops.py:1492`) shows the
  `subprocess.run(["bash", "-c", script], ...)` pattern for actually executing
  a fragment's `action` body against real content — reuse this shape (not a
  pure-YAML structural assertion) for the new backtick/`$`/quote regression
  test, since no existing test executes fragment shell bodies against
  adversarial input today.
- If the issue's suggested `ll-loop validate` lint rule is pursued: template
  classes `TestBashDefaultInterpolation` (MR-7,
  `scripts/tests/test_fsm_validation.py:3199`) and `TestOverescapedShell` (MR-9,
  `:3269`) show the 5-part structure to copy (fires-on-bad-pattern,
  does-not-fire-on-safe-pattern, suppressed-by-`*_ok`-flag, wired-into-
  `validate_fsm()`, top-level-key-recognized round-trip).

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — learning-gate section (note the
  file-based, non-interpolating pattern).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md:236-259` — the "learning-gate routing is
  consistent across all three core implementation loops" section narrates how
  `ll_auto_learning_gate_check` screens `ll-auto`'s captured output before the
  auth/failure checks. The gate→auth ordering this section describes must be
  preserved by the fix (both fragments still read the *same* file, gate first);
  the prose is generic enough it likely doesn't need a factual correction, but
  should be reviewed once the fix lands to confirm it doesn't imply the
  now-removed `${captured...}` interpolation mechanism.

### Configuration
- N/A

## Motivation

This defect silently destroys run outcomes: the loop crashes before writing
`summary.json`, so an operator (or `audit-loop-run`) sees only `No valid
transition` with no honest failure record. Because the trigger — non-zero
`ll-auto` exit with Markdown output — is common (every decision-gate halt,
learning-gate block, or implementation error prints fenced Markdown), the crash
is easy to hit, and it affects two production loops via the shared fragment.

## Impact

- **Priority**: P2 — crashes the loop and discards the run summary on a common
  input (any `ll-auto` non-zero exit whose output contains shell metacharacters);
  shared across `autodev` and `rn-remediate`. Borderline P1 given the loss of
  outcome data, but downstream issue state is not corrupted.
- **Effort**: Small — file-based grep + `on_error` route; mirrors existing
  run-dir file patterns already used in the loop.
- **Risk**: Low — the fix removes an interpolation hazard and adds a strictly
  safer route; behavior on the happy path is unchanged.
- **Breaking Change**: No

## Resolution

Fixed by teeing `ll-auto` output to `${context.run_dir}/ll_auto_last.txt` (with
`set -o pipefail` to preserve the exit code through the pipe) at all four call
sites (`autodev.implement_current`, `rn-remediate.implement`,
`eval-driven-development.implement`), and rewriting both
`ll_auto_auth_check` and `ll_auto_learning_gate_check`
(`scripts/little_loops/loops/lib/common.yaml`) to `grep` that file instead of
interpolating `${captured.ll_auto_output.output}` into a double-quoted shell
`echo`. Added `on_error` routes to all four fragment-caller states
(`autodev.check_learning_gate → check_impl_auth`,
`autodev.check_impl_auth → dequeue_next`,
`rn-remediate.check_learning_gate → check_impl_auth`,
`rn-remediate.check_impl_auth → emit_implement_failed`,
`eval-driven-development.check_impl_auth → commit_impl`) so a residual shell
fault degrades to the next check instead of terminating the FSM. `capture:
ll_auto_output` was left in place at all call sites (unused by the rewritten
fragments, but still asserted by `test_rn_remediate.py`).

Added a regression test (`test_fsm_fragments.py::TestLlAutoFragmentsAdversarialOutput`)
that executes both fragments' real shell bodies against output containing
backticks/`$`/quotes/fenced code via `subprocess.run`, plus `on_error`
structural assertions in `test_builtin_loops.py`. Updated
`test_fragment_action_references_ll_auto_output_capture` →
`test_fragment_action_reads_run_dir_file_not_captured_output` to match the new
contract. Full suite: 14542 passed, 36 skipped. `ll-loop validate` clean on
`autodev`, `rn-remediate`, `eval-driven-development`.

## Status

**Done** | Created: 2026-07-10 | Priority: P2


## Session Log
- `/ll:ready-issue` - 2026-07-11T02:10:11 - `ea6f445e-a6eb-4e55-a3cd-1266afdad3e5.jsonl`
- `/ll:confidence-check` - 2026-07-10T00:00:00Z - `2cc3287b-895b-4bae-b9c4-28ac6d02f83d.jsonl`
- `/ll:wire-issue` - 2026-07-11T02:05:43 - `3baa7e71-8334-480a-991a-3217d923e118.jsonl`
- `/ll:refine-issue` - 2026-07-11T01:58:38 - `b86cdd2d-af1a-4714-b989-7e3ce0fb2ec6.jsonl`
- `/ll:manage-issue` - 2026-07-11T02:18:01 - `765df719-996e-42c4-9688-258d5edf3ec9.jsonl`
