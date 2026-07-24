---
id: BUG-2756
title: Fix rlhf SVG Playwright smoke harness failure and propagate evaluation status
type: BUG
priority: P2
status: done
discovered_by: ll-product-promotion
discovered_date: 2026-07-24
completed_at: '2026-07-24T18:16:49Z'
labels:
- artifact-loops
- evaluation
decision_needed: false
learning_tests_required:
- playwright
confidence_score: 90
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 25
---

# BUG-2756: Fix rlhf SVG Playwright smoke harness failure and propagate evaluation status

Origin: ll-product #BUG-025

# BUG-025: Fix rlhf-svg-evaluate Playwright smoke harness failure and propagate evaluation status

## Summary

The `rlhf-svg-evaluate` sub-loop's Playwright smoke test fails with
`'n.split is not a function'` *after* all four frame screenshots are
captured but *before* the `score` (vision API) pass can run. Because the
`smoke_test → smoke_fail_exit → done` branch ends the sub-loop in
`done` and the parent `rlhf-animated-svg` loop only checks for terminal
`done`, the run can terminate as "done" with no vision verdict — making an
unevaluated artifact look accepted. Two fixes are needed:

1. **Frame-capture argument handling** in the inline Playwright `node -e`
   block of `rlhf-svg-evaluate.yaml:smoke_test` so the smoke harness
   reaches `SMOKE_PASS` when the artifact is good (or surfaces a real
   error string when it isn't), and
2. **Status propagation** so the parent's `done` terminal reflects
   *workflow termination*, distinct from *successful artifact evaluation*,
   and the parent can route on the vision verdict without conflating the
   two.

## Current Behavior

In the `rlhf-animated-svg-20260723T230538` run on 2026-07-24T04:12:51Z,
the `smoke_test` state (depth=1, in the `rlhf-svg-evaluate` sub-loop)
executed its inline Playwright harness. The action output shows the
full sequence of expected lines followed by a single failure:

```
ARCHIVED: snapshots/output_iter_1.html
Screenshot saved to output_frame_1000ms.png
Screenshot saved to output.png
Screenshot saved to output_frame_5000ms.png
Screenshot saved to output_frame_7000ms.png
SMOKE_FAIL: n.split is not a function
```

- Exit code: `1`
- All four frame captures (`output_frame_1000ms.png`, `output.png`,
  `output_frame_5000ms.png`, `output_frame_7000ms.png`) succeeded and
  exist on disk in the run dir.
- The IIFE's outer `.catch` fired with `e.message === "n.split is not a
  function"` — a minified-variable runtime error originating from
  somewhere in the validation / post-screenshot block of the inline
  Playwright `node -e` script in
  `scripts/little_loops/loops/rlhf-svg-evaluate.yaml:smoke_test`
  (lines ~84–179).
- The state routed to `smoke_fail_exit`, which echoed
  `VISION_FAIL: smoke test failed — artifact did not pass browser validation`
  and transitioned to `done`. **No `score` (vision API) pass ran** for
  this iteration, and the parent observed the sub-loop as a normal
  completion — the final artifact shipped without any vision verdict.

### Why "n.split is not a function" specifically

The minified variable name `n` and the fact that the failure occurs
*after* the four `page.screenshot()` calls have all logged "Screenshot
saved to ..." place the throw in the post-capture block — most likely
inside the Playwright client when the validation or error-aggregation
block (`errors.join('; ')`, pageerror / console-error handler) is
finalized. The regression is reproducible whenever the harness captures
all four frames and at least one page error or console error fires
before `browser.close()` returns; the test never reaches a clean
`SMOKE_PASS`. The smoke harness does not handle the case where a
captured `pageerror` has a non-string `.message` (e.g. an `ErrorEvent`
from the browser runtime), so the `errors.join('; ')` aggregate
explodes.

## Expected Behavior

1. The inline Playwright harness in `smoke_test` must reach
   `SMOKE_PASS` when the artifact is well-formed and animate, even if a
   single page error fires after frame capture, and must surface a
   **specific, human-readable** error string (not a minified runtime
   message) on real failure.
2. When `smoke_test` fails for any reason, the sub-loop's terminal
   state must not be visually indistinguishable from a successful
   evaluation. The parent `rlhf-animated-svg` must be able to tell a
   *sub-loop completed without a vision verdict* apart from *sub-loop
   completed with VISION_PASS*.
3. The parent loop's `done` terminal should not silently treat
   `smoke_fail_exit → done` as an accepted artifact; the iteration
   counter and final-status summary should reflect an unevaluated run.

## Root Cause

**File**: `scripts/little_loops/loops/rlhf-svg-evaluate.yaml`

### Defect 1 — `smoke_test` Playwright harness crashes on page error aggregation

`smoke_test.action` is an inline `node -e` script (lines ~84–179) that
launches Chromium, captures four frames at t = 1000/3000/5000/7000 ms,
then aggregates any captured `pageerror` / `console-error` strings into
the `errors` array and either logs `SMOKE_PASS` (no errors) or
`SMOKE_FAIL: <joined message>` (errors present). The outer
`IIFE.catch(e => { console.log('SMOKE_FAIL: ' + e.message); process.exit(1); })`
catches a *runtime* error from the same harness — not a captured page
error — and emits the raw `e.message`. When the post-capture
aggregation touches an ErrorEvent whose `e.message` is not a string
(observed in the wild as the minified `n.split is not a function` from
Playwright internals), the join call throws before the harness can emit
a clean `SMOKE_FAIL` line. Result: the smoke state is indistinguishable
from a real `SMOKE_PASS`-followed-by-vision-success run on the parent's
side because the parent only checks for terminal `done`, not for the
`score` state's `VISION_PASS` sentinel.

### Defect 2 — Parent has no way to distinguish "smoke crashed" from "vision passed"

The parent `rlhf-animated-svg` (around line 88) invokes
`rlhf-svg-evaluate` as a sub-loop. The sub-loop's `done` terminal
emits whether the smoke test crashed, the vision API rejected, the
artifact was unevaluable, or the artifact genuinely cleared the bar. The
parent's only routing cue today is whether the *sub-loop* reached
`done`; there is no propagate-then-route step that maps
`SMOKE_FAIL`-only / `VISION_FAIL` / `VISION_PASS` to distinct
parent-level status flags. The most recent run (2026-07-24) confirms
this: `smoke_fail_exit → done` and the parent observed the iteration
as complete with no recorded vision verdict.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Precise anchors** in `scripts/little_loops/loops/rlhf-svg-evaluate.yaml`:
  `errors.push(e.message)` (pageerror handler) is line 97,
  `errors.push(msg.text())` (console-error handler) is line 98, the
  `errors.join('; ')` call is line 162, and the outer IIFE `.catch` is
  lines 175–178. There is exactly one `.join(` call in this state (grep
  confirmed) — the two `", ".join(...)` calls inside the `score` state's
  Python code (lines 283, 285) join a fixed `FRAME_DEFS`-derived list of
  plain Python strings and are not implicated.
- **Caveat on the join-throws hypothesis**: `Array.prototype.join`
  coerces `undefined`/`null` entries to an empty string and does not
  throw merely because `e.message` is `undefined` — the join call at
  line 162 is unlikely to be the literal throw site for a plain
  `undefined` value. The `'n.split is not a function'` signature (a
  minified internal reference) is more consistent with the throw
  originating inside Playwright/V8 internals invoked before or during
  error-event dispatch, rather than in the `errors.join('; ')` line
  itself. The fix should still add the coercion/try-catch guard (it's
  cheap insurance and covers non-nullish non-string `.message` values
  such as thrown objects), but implementers should not assume line 162
  is confirmed as the exact throw site — instrumenting with a
  try/catch around the whole post-capture block (not just the join)
  is the safer target per the Implementation Notes' existing guidance.
- **Same unguarded pattern exists elsewhere** — not just in the `p5js`
  plan referenced in Source Doc: `scripts/little_loops/loops/html-website-generator.yaml:139`
  (`page.on('pageerror', e => errors.push(e.message))`) and
  `scripts/little_loops/loops/interactive-component-generator.yaml:282,455`
  (two separate smoke states, same idiom, one prefixed `'page: ' + e.message`)
  have the identical unguarded-`e.message` exposure. No file in
  `scripts/little_loops/loops/*.yaml` currently does
  `String(e.message ?? e.text?.() ?? "UNKNOWN_PAGE_ERROR")` or wraps
  the aggregation in its own try/catch — there is no existing safe
  pattern to copy; this fix establishes the first one.
- **Stale reference**: `p5js-sketch-generator.yaml` (cited in Source
  Doc as `p5js-sketch-generator.yaml:127–139`) now has an empty
  `states: {}` block and delegates entirely via `from: generative-art`
  (ENH-2161 consolidation). A grep of `generative-art.yaml` for
  `pageerror`/`errors.join` found no matches — the multi-frame capture
  step, if present there, isn't phrased with the same
  `page.on('pageerror', ...)` idiom, so this cross-reference could not
  be confirmed against current code and may need re-verification
  before porting the fix there.

## Steps to Reproduce

1. From a fresh `rlhf-animated-svg` run dir, the parent enters the
   `rlhf-svg-evaluate` sub-loop and the sub-loop enters `smoke_test`
   (depth=1).
2. The sub-loop's `smoke_test.action` inline `node -e` block
   navigates Chromium to `output.html` and successfully captures
   `output_frame_1000ms.png`, `output.png`, `output_frame_5000ms.png`,
   and `output_frame_7000ms.png`.
3. Any post-capture page error whose `e.message` is not a string
   (e.g. a Playwright `ErrorEvent` from a deferred anime.js timeline
   callback) triggers the inner `errors.join('; ')` line to throw.
4. The outer `.catch` fires, logs `SMOKE_FAIL: n.split is not a
   function` (minified variable name), and `process.exit(1)`.
5. `smoke_test` routes `on_no: smoke_fail_exit` →
   `smoke_fail_exit.next: done` — **without ever entering `score`**.
6. The parent records the sub-loop as a normal completion; the
   artifact ships unevaluated.

## Acceptance Criteria

- [x] `rlhf-svg-evaluate:smoke_test` no longer crashes with a
      minified-variable message (`n.split is not a function` or
      similar); the harness always emits either a clean
      `SMOKE_PASS` or a `SMOKE_FAIL: <human-readable cause>` line.
- [x] The inline Playwright script coerces `pageerror` and
      `console-error` payloads to strings before pushing them onto
      `errors`; the post-capture aggregation (`errors.join`,
      `errors.length > 0`) is wrapped so a single non-string entry
      cannot abort the whole harness.
- [x] A regression test is added under `scripts/tests/` (or the
      appropriate built-in-loop test file) that mocks a non-string
      `pageerror.message` and asserts the smoke harness still emits a
      `SMOKE_FAIL` line with a recognizable cause.
- [x] `rlhf-svg-evaluate:done` (or an explicit sentinel state) emits
      a distinct marker for the three terminal classes —
      `VISION_PASS`, `VISION_FAIL`, and `UNEVALUATED` (smoke crashed or
      frames unavailable) — and the marker is visible in the
      sub-loop's `output` to the parent.
- [x] The parent `rlhf-animated-svg` no longer treats
      `smoke_fail_exit → done` as an accepted artifact; the iteration's
      `score_fail_streak_max` accounting (ENH-033) and the final
      `optimization_summary.md` reflect an unevaluated run distinctly
      from a clean `VISION_PASS`.
- [x] `ll-loop validate rlhf-svg-evaluate` and
      `ll-loop validate rlhf-animated-svg` pass with no new errors
      after the fix.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-24.

**Selected**: Option B — distinct `unevaluated: {terminal: true}` state, `smoke_fail_exit.next` retargeted from `done`

**Reasoning**: The FSM executor (`scripts/little_loops/fsm/executor.py:1004-1010`) already routes a sub-loop's parent `on_yes`/`on_no` purely by whether `final_state == "done"` by name — any other terminal state name automatically routes to `on_no`, with zero executor changes required. This exact two-distinct-terminal-name shape already ships in `loops/oracles/code-run-gate.yaml` and `loops/oracles/generator-evaluator.yaml`, and a directly analogous regression test (`test_sub_loop_terminal_failed_routes_to_on_no`, BUG-1017, `scripts/tests/test_fsm_executor.py:5542-5566`) already proves the mechanism. Option A, by contrast, would add an `evaluate: {type: output_contains, ...}` block to a `loop:`-typed state — but `_execute_sub_loop` dispatches before any `evaluate:`-consuming code path runs and never reads `state.evaluate`, so the block would be silently inert without an unimplemented change to `executor.py`, and `ll-loop validate` has no lint to catch that misconfiguration.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (content-based routing) | 0/3 | 1/3 | 1/3 | 0/3 | 2/12 |
| Option B (distinct terminal state) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |

**Key evidence**:
- Option A: No file in `scripts/little_loops/loops/*.yaml` pairs `evaluate:` with `loop:` on the same state; `_execute_sub_loop` never consults `state.evaluate`, so the block would be dead code without an executor change.
- Option B: Established, currently-shipping precedent (`oracles/code-run-gate.yaml:429-435`, `oracles/generator-evaluator.yaml:183-187`) plus an existing BUG-1017 regression test template — a one-line `next:` retarget and one new terminal block, no executor changes.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/rlhf-svg-evaluate.yaml` — primary
  change target; the `smoke_test.action` inline Playwright script and
  the `done` terminal (or new sentinel state) need updates.
- `scripts/little_loops/loops/rlhf-animated-svg.yaml` — secondary
  change; the parent's sub-loop wiring (around line 88) and the
  iteration-status accounting need to read the new `UNEVALUATED`
  sentinel.

### Sub-Loop Wiring (no change to *which* sub-loop is invoked, only how its verdict is read)

The parent already routes to the sub-loop and back; the only change is
on the *read* side — `prev.output` from the sub-loop's `done` is
parsed for `VISION_PASS` / `VISION_FAIL` / `UNEVALUATED` and the
iteration's status file (e.g. `.vision_scores.json` or a new
`.evaluation_status` file) carries the marker forward.

### Tests

- `scripts/tests/test_builtin_loops.py` — schema / validation gate for
  both `rlhf-svg-evaluate` and `rlhf-animated-svg` after the change.
- Add `scripts/tests/test_rlhf_svg_evaluate_smoke.py` (or extend the
  existing smoke-harness test if one exists) with a fixture that
  injects a non-string `pageerror.message` and asserts:
  - the smoke harness returns exit-code 1,
  - the captured `output` contains a `SMOKE_FAIL: <readable cause>`
    line, and
  - the harness never aborts with a raw minified runtime message.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **The actual parent routing mechanism** is generic FSM sub-loop
  dispatch, not anything specific to this loop pair:
  `scripts/little_loops/fsm/executor.py:_execute_sub_loop` (function
  starts ~line 799) decides `on_yes`/`on_no` purely from
  `child_result.final_state == "done"` by **name** (lines ~1004-1010).
  It never inspects `prev.output` text. `rlhf-animated-svg.yaml`'s
  `run_evaluate` state (lines 96-105) has no `evaluate:` block and no
  `output_contains` pattern at all — confirmed by grep, contrary to
  the Impact section's claim that "parent routing already keys on
  `output_contains: VISION_PASS`" (no such line exists in this file
  today).
- Because `rlhf-svg-evaluate.yaml`'s `done` (lines 686-687) is a bare
  `terminal: true` with no `action`/`capture`, and **every** path
  (smoke pass, smoke fail/crash, vision pass, vision fail, vision-scoring
  error) converges on this same state name, `_execute_sub_loop` always
  takes the `on_yes` branch (`run_evaluate.on_success: write_final_summary`)
  — the failure path (`on_failure: check_oscillation`, line 104) and all
  downstream ENH-033 streak-accounting states (`check_oscillation` 107-133,
  `check_score_streak` 151-187, `check_replan_budget` 246-280) are
  currently unreachable from any `rlhf-svg-evaluate` outcome.
- **This surfaces a lower-effort alternative fix shape** to the
  output-parsing approach implied by the Acceptance Criteria:

  **Option A**: Keep a single `done` terminal; add a distinct
  `UNEVALUATED` sentinel string to its output and have the parent's
  `run_evaluate` gain an `evaluate: {type: output_contains, pattern: "VISION_PASS"}`
  block so `on_yes`/`on_no` route on content, not just terminal-state name.

  **Option B**: Give the sub-loop two distinct terminal state names —

  > **Selected:** Option B — reuses the FSM's existing name-based
  > sub-loop routing with zero executor changes; Option A would require
  > an unimplemented `executor.py` change and produce a silently-inert
  > `evaluate:` block that `ll-loop validate` would not catch.

  e.g. keep `done` for `VISION_PASS`/`VISION_FAIL` (both already
  legitimate evaluations) and route `smoke_fail_exit` to a new
  `unevaluated: {terminal: true}` state instead of `done`. Since
  `_execute_sub_loop` already routes on `final_state == "done"` by
  name with no code change needed in `executor.py`, this needs zero
  changes to the generic sub-loop dispatch mechanism — only the
  `next:` target on `smoke_fail_exit` (currently `done`, line 194)
  changes, plus one new terminal state block.

  **Recommended**: Option B for the smoke-crash/UNEVALUATED split — it
  reuses the existing name-based routing with no executor change and
  is smaller-diff. Option A-style content-based routing may still be
  worth adding separately if the parent ever needs to distinguish
  `VISION_PASS` from `VISION_FAIL` (both currently reach `done` and
  are NOT distinguished by the parent at all today) — that finer split
  is a distinct concern from the UNEVALUATED gap this bug targets and
  is out of scope for a minimal fix.
- Existing test coverage is **structural-only**: `test_builtin_loops.py`'s
  `TestRlhfSvgEvaluateSubLoop` (line ~10198) and
  `TestRlhfAnimatedSvgParentOrchestration` (line ~10407) assert against
  the parsed YAML dict (state names, `on_yes`/`on_no`/`next` targets,
  substring checks on the raw `action:` string) — no test in this file
  executes the inline `node -e` script, launches Node, or mocks
  Playwright. The new `test_rlhf_svg_evaluate_smoke.py` regression test
  (per Acceptance Criteria) has no existing precedent of the same kind
  to model structurally; it will need a new test shape (e.g. shelling
  out to `node -e` with a stub `playwright` module, or extracting/executing
  the inline script directly against a fake page object).

### Validation Command

```bash
ll-loop validate rlhf-svg-evaluate
ll-loop validate rlhf-animated-svg
python -m pytest scripts/tests/test_builtin_loops.py -v
python -m pytest scripts/tests/test_rlhf_svg_evaluate_smoke.py -v   # new
```

## Implementation Notes

- The fix is a *robustness* patch, not a logic rewrite. The inline
  Playwright script's post-capture block should wrap
  `pageerror`/`console-error` aggregation in a `try { ... } catch {
  errors.push("NON_STRING_PAGE_ERROR"); }` and coerce any non-string
  message to `String(e.message ?? e.text() ?? "UNKNOWN_PAGE_ERROR")`
  before joining.
- The `done` terminal of the sub-loop can be a thin shell action
  that prints `UNEVALUATED` whenever the run reached `smoke_fail_exit`
  and never entered `score`; otherwise it prints the last seen
  `VISION_PASS` / `VISION_FAIL` from the `track_correlation` state's
  output. The parent already inspects `prev.output`, so making the
  marker explicit there is sufficient — no schema change required.
- The parent's `score_fail_streak_max` logic (ENH-033) should *not*
  increment on `UNEVALUATED`; only `VISION_FAIL` should count. A
  smoke-crash is a harness failure, not a model failure.

## Source Doc

Inlined summary of `docs/plans/pixi-js-2-loops-plan.md` (the hub's
listed source doc, included for round-trip traceability):

- The pixi plan documents the **Multi-frame Playwright capture**
  pattern that `rlhf-svg-evaluate` also uses (4 staggered screenshots
  for temporal evaluation, in this case t = 1000/3000/5000/7000 ms
  rather than the pixi plan's t = 0/90/240 with `__loopFrame`). The
  same robustness gap — minified-runtime error from inside Playwright
  when a captured page error has a non-string payload — applies to
  any loop using this pattern. The pixi loops (once implemented) will
  need the same coercion-on-page-error guard; this fix establishes
  the precedent.
- The plan's "Reused Patterns / Files Referenced" section points at
  `scripts/little_loops/loops/p5js-sketch-generator.yaml:127–139` as
  the canonical multi-frame Playwright capture invocation. The same
  pattern is the basis for the rlhf multi-frame capture; the
  aggregation block in p5js's evaluate state is similarly exposed
  and should be hardened in a follow-up if it isn't already.

## Impact

- **Priority**: P2 — vision gating is the only external evaluator in
  the rlhf family; a silent unevaluated-completion defeats the gate.
- **Effort**: Small–Medium — one inline-script robustness patch and
  one routing marker in the sub-loop's `done` terminal, plus a
  small parent-side read-side update.
- **Risk**: Low — no schema change; the new `UNEVALUATED` marker is
  additive and parent routing already keys on
  `output_contains: VISION_PASS`.
- **Breaking Change**: No.


## Resolution

- **Action**: fix
- **Completed**: 2026-07-24
- **Status**: Completed

### Changes Made
- `scripts/little_loops/loops/rlhf-svg-evaluate.yaml`: `smoke_test`'s inline
  Playwright script now coerces `pageerror`/`console-error` payloads via a
  guarded `toMessage()` helper (falls back to `UNKNOWN_PAGE_ERROR` /
  `NON_STRING_PAGE_ERROR` on non-string or throw-on-access `.message`) before
  pushing onto `errors`, and the post-capture `errors.join('; ')` aggregation
  is wrapped in its own try/catch. `smoke_fail_exit` now emits `UNEVALUATED:
  ...` and routes `next: unevaluated` (new terminal state) instead of `next:
  done`, so the parent's generic sub-loop dispatch (`_execute_sub_loop`,
  which routes purely on `final_state == "done"` by name) takes the
  `on_failure` branch — reaching the existing smoke-fail-streak accounting in
  `check_oscillation` — instead of `on_success`.
- `scripts/tests/test_rlhf_svg_evaluate_smoke.py` (new): extracts the real
  inline `node -e` script from the YAML and runs it under Node against a
  minimal Playwright stub that fires a non-string, throw-on-access
  `pageerror.message`; asserts exit code 1, a `SMOKE_FAIL:` line, and no leak
  of the raw minified message. Verified this test fails against the pre-fix
  script (reproducing `SMOKE_FAIL: n.split is not a function`) and passes
  against the fix.

### Verification Results
- Tests: PASS (`python -m pytest scripts/tests/` — 16097 passed, 1 pre-existing
  unrelated failure: `test_string_present_in_doc[README.md-39 typed CLI
  tools-FEAT-1045]`, a README/CLI-count drift test untouched by this change)
- Lint: PASS (`ruff check` / `ruff format --check` on the new test file)
- Types: PASS (`python -m mypy scripts/little_loops/`)
- `ll-loop validate rlhf-svg-evaluate`: PASS
- `ll-loop validate rlhf-animated-svg`: PASS

## Session Log
- `/ll:ready-issue` - 2026-07-24T18:03:28 - `d16ace1a-c22c-462b-9c70-ae96ef66c213.jsonl`
- `/ll:confidence-check` - 2026-07-24T18:30:00 - `04993c4c-e121-4fd4-b1fb-17b9e6e8c255.jsonl`
- `/ll:decide-issue` - 2026-07-24T17:54:51 - `0c365d2d-48a6-42ed-8e3a-999a4eeb223c.jsonl`
- `/ll:refine-issue` - 2026-07-24T17:48:56 - `9ff212b0-5349-4e29-8d32-150116f2dc69.jsonl`
- `/ll:manage-issue` - 2026-07-24T18:15:44 - fix BUG-2756
