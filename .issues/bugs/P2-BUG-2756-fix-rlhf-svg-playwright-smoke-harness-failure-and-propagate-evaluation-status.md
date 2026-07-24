---
id: 2756
title: Fix rlhf SVG Playwright smoke harness failure and propagate evaluation status
type: BUG
priority: P2
status: open
discovered_by: ll-product-promotion
discovered_date: 2026-07-24
labels:
- artifact-loops
- evaluation
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

- [ ] `rlhf-svg-evaluate:smoke_test` no longer crashes with a
      minified-variable message (`n.split is not a function` or
      similar); the harness always emits either a clean
      `SMOKE_PASS` or a `SMOKE_FAIL: <human-readable cause>` line.
- [ ] The inline Playwright script coerces `pageerror` and
      `console-error` payloads to strings before pushing them onto
      `errors`; the post-capture aggregation (`errors.join`,
      `errors.length > 0`) is wrapped so a single non-string entry
      cannot abort the whole harness.
- [ ] A regression test is added under `scripts/tests/` (or the
      appropriate built-in-loop test file) that mocks a non-string
      `pageerror.message` and asserts the smoke harness still emits a
      `SMOKE_FAIL` line with a recognizable cause.
- [ ] `rlhf-svg-evaluate:done` (or an explicit sentinel state) emits
      a distinct marker for the three terminal classes —
      `VISION_PASS`, `VISION_FAIL`, and `UNEVALUATED` (smoke crashed or
      frames unavailable) — and the marker is visible in the
      sub-loop's `output` to the parent.
- [ ] The parent `rlhf-animated-svg` no longer treats
      `smoke_fail_exit → done` as an accepted artifact; the iteration's
      `score_fail_streak_max` accounting (ENH-033) and the final
      `optimization_summary.md` reflect an unevaluated run distinctly
      from a clean `VISION_PASS`.
- [ ] `ll-loop validate rlhf-svg-evaluate` and
      `ll-loop validate rlhf-animated-svg` pass with no new errors
      after the fix.

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
