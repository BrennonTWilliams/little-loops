---
id: ENH-2903
type: ENH
priority: P3
status: open
captured_at: '2026-07-28T00:00:00Z'
discovered_date: 2026-07-28
discovered_by: svg-image-generator-screenshot-hang-diagnosis
depends_on:
- BUG-2901
- BUG-2904
relates_to:
- BUG-2901
- BUG-2904
---

# ENH-2903: generator-evaluator screenshot failure has no escape route

## Summary

Every outcome of the `evaluate` state in
`scripts/little_loops/loops/oracles/generator-evaluator.yaml:82-84` routes to the
same place, so a failed screenshot cannot be distinguished from a bad artifact
and the loop keeps iterating blind.

This is the defect that **persists after** BUG-2901 and BUG-2904 are both fixed:
bounding the hang and reaping the tree still leaves the loop burning its full
step budget on un-evaluable iterations.

## Status

Open. BUG-2901 is `done` (commit `e2cb3d8e`). Still blocked on **BUG-2904 only**.

> **PREMISE CORRECTED 2026-07-29** (pre-implementation review). This issue
> previously said its design "assumes `exit_code: 124` is an observable signal
> downstream of `evaluate`" and described a timeout as reaching `on_error`.
> **It does not reach `on_error`.** The `evaluate` state inherits
> `evaluate.type: output_contains` / `pattern: "CAPTURED"` from the
> `playwright_screenshot` fragment, and `output_contains` never consults the
> exit code — only the no-`evaluate:` default path calls `evaluate_exit_code`
> (`scripts/little_loops/fsm/executor.py:1994`). A timed-out screenshot
> therefore yields verdict **`no`**, not `error`. The 124 is visible in the
> event stream but invisible to routing.
>
> This **does not invalidate the design** — detecting a missing/stale
> `screenshot.png` in `snapshot` is the right approach precisely *because*
> routing cannot discriminate. But an implementer reading the old text would
> wire an `on_error`-keyed detector that never fires. Do not do that.

## Current Behavior

```yaml
  on_yes: snapshot
  on_no: snapshot
  on_error: snapshot
```

A screenshot that fails — for any reason, including the timeout BUG-2904 will
start producing (which arrives as `on_no`, per the correction above) — advances
to `snapshot` → `score` → `check_stall` → `check_diff_stall` → `generate` and
iterates again. `snapshot` copies with `cp ... || true`, silently swallowing the
absent file, and `score` then rubric-scores an artifact whose screenshot is
missing or stale from a previous iteration.

Note `snapshot` swallows a missing **artifact** the same way:

```bash
      cp "$RUN_DIR/${context.artifact_path}" "$RUN_DIR/iter-$COUNTER/" 2>/dev/null || true
      cp "$RUN_DIR/screenshot.png" "$RUN_DIR/iter-$COUNTER/" 2>/dev/null || true
```

Same defect class, same state, same fix shape — in scope here rather than left
for a third issue.

## Expected Behavior

A persistently un-screenshottable artifact converges through the existing stall
machinery to a terminal state with an honest verdict, while a single transient
screenshot fault remains survivable.

## Impact

The loop cannot distinguish "the artifact is bad" from "we never managed to look
at the artifact." Rubric scores computed against stale screenshots are silently
wrong, and the run exhausts `max_steps` rather than terminating on a real signal.

## Proposed Solution

Keep `on_error: snapshot`, but make the downstream states able to *see* that the
screenshot is missing:

1. `snapshot` detects a missing or stale `screenshot.png` and records the miss.
   "Stale" means the file predates this iteration's artifact write — compare
   mtimes, or hash it against the previous iteration's copy in `iter-$((N-1))/`.
   Apply the same detection to the missing-artifact `cp` noted above.
2. `score` treats "no fresh screenshot this iteration" as a distinct,
   non-passing signal rather than silently scoring a stale image.
3. Consecutive screenshot misses feed `check_stall` / `check_diff_stall`, which
   already own convergence.

The miss is recorded to a counter file under `${context.run_dir}/` (MR-3:
per-run isolation, never bare `.loops/tmp/`), alongside the existing
`.iter_counter` and `.score_history`.

### Why not simply `on_error: failed`

The original diagnosis recommended changing `on_error` to `failed`. That is too
blunt:

- It discards a run whose *artifact* may be perfectly good and whose only
  failure was the screenshot step — a transient Playwright/Chromium fault fails
  the whole generation.
- It is an unvalidated behavior change across every consumer of this oracle
  (`html-website-generator`, `html-anything`, `hitl-md`,
  `p5js-sketch-generator`, `svg-image-generator`). The diagnosis explicitly
  flagged that no consumer's dependence on the current snapshot-after-error path
  was checked.

## Scope Boundaries

In scope: the screenshot-miss signal and its propagation through `snapshot`,
`score`, and the stall detectors in `oracles/generator-evaluator.yaml`; the
parallel missing-artifact blindness in `snapshot`'s first `cp ... || true`; and
the MR-13 `"abandoned"` summary key on the convergence path.

Out of scope — two recommendations from the source diagnosis are deliberately
excluded:

- **Gating re-launch on `user-stop.marker`.** The marker written at `22:51:15Z`
  did not prevent a new run at `22:51:47Z`, but that orchestration lives in the
  `loop-sandbox` repo, not here.
- **A host-level `chrome-headless-shell` descendant counter.** Belt-and-braces
  defense against a leak that BUG-2901 fixes at the root; revisit only if
  orphaned trees are observed after that lands.

A `screenshot_timeout` event type was also considered and dropped — once
BUG-2901 works, the timeout already surfaces as `exit_code: 124` in the event
stream, which downstream tooling can key on without a new event type. (This
remains true: the 124 *is* in the event stream. It is only *routing* that cannot
see it — see the premise correction under Status.)

## Open Questions

All three resolved 2026-07-29 (pre-implementation review):

- **Dedicated counter, not `diff_stall` inference.** `diff_stall` compares
  artifact content; an absent screenshot alongside an unchanged artifact is a
  genuinely different condition, and overloading the detector would conflate
  "the generator has plateaued" with "we never got a look at the output." Use an
  explicit `.screenshot_misses` counter under `${context.run_dir}/`, and let it
  feed the existing stall states rather than replacing them.
- **Land in the shared oracle, not per-consumer.** "Do not rubric-score a stale
  screenshot" is correct for all five wrappers; per-wrapper tolerance is
  speculative, and there is no evidence any consumer wants the current silent
  behavior. Revisit only if a wrapper is later shown to need a different
  threshold.
- **Yes on MR-13.** If this converges to a terminal state via abandonment, the
  run must emit an `"abandoned"` key into `summary.json` and downgrade the
  verdict; otherwise `ll-loop validate` warns (MR-13, suppressible only via
  `abandonment_verdict_ok`, which is not the right answer here). Budget for a
  penultimate non-terminal state that writes the summary — a terminal state's
  own `action:` is dead code per the `terminal-action-ok` rule.

## Acceptance Criteria

- [x] BUG-2901 is merged — commit `e2cb3d8e`.
- [ ] BUG-2904 is merged (remaining hard prerequisite).
- [ ] A missing/stale `screenshot.png` is detectable downstream of `evaluate`
      **without relying on an `on_error` route** (a timeout arrives as `no`).
- [ ] A missing artifact in `snapshot`'s first `cp` is likewise detected rather
      than swallowed by `|| true`.
- [ ] `score` does not silently rubric-score a stale screenshot.
- [ ] Repeated screenshot failures converge to a terminal state with an honest
      verdict rather than exhausting `max_steps`.
- [ ] The convergence path emits an `"abandoned"` key into `summary.json` and
      downgrades the verdict (MR-13); `ll-loop validate` raises no MR-13 warning
      and no `abandonment_verdict_ok` suppression flag is added.
- [ ] No behavior change for consumers whose screenshots succeed.
- [ ] `ll-loop validate` passes for the oracle and all five wrappers.
- [ ] `python -m pytest scripts/tests/` exits 0.
