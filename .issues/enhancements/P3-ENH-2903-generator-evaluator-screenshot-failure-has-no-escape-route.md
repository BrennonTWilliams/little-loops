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
`scripts/little_loops/loops/oracles/generator-evaluator.yaml:75-77` routes to the
same place, so a failed screenshot cannot be distinguished from a bad artifact
and the loop keeps iterating blind.

This is the defect that **persists after** BUG-2901 and BUG-2904 are both fixed:
bounding the hang and reaping the tree still leaves the loop burning its full
step budget on un-evaluable iterations.

## Status

Open. Blocked on BUG-2901 and BUG-2904.

## Current Behavior

```yaml
  on_yes: snapshot
  on_no: snapshot
  on_error: snapshot
```

A screenshot that fails — for any reason, including the `exit_code: 124` timeout
that BUG-2904 will start producing — advances to `snapshot` → `score` →
`check_stall` → `check_diff_stall` → `generate` and iterates again. `snapshot`
copies with `cp ... || true`, silently swallowing the absent file, and `score`
then rubric-scores an artifact whose screenshot is missing or stale from a
previous iteration.

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
2. `score` treats "no fresh screenshot this iteration" as a distinct,
   non-passing signal rather than silently scoring a stale image.
3. Consecutive screenshot misses feed `check_stall` / `check_diff_stall`, which
   already own convergence.

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
`score`, and the stall detectors in `oracles/generator-evaluator.yaml`.

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
stream, which downstream tooling can key on without a new event type.

## Open Questions

- Is a dedicated `screenshot_missing` counter warranted, or can the existing
  `diff_stall` detector infer it from an unchanged/absent screenshot?
- Should this land as a change to the shared oracle, or per-consumer? The five
  wrappers may want different tolerances.
- Per MR-13, does an abandonment path here need to surface an `"abandoned"` key
  in the run's `summary.json` and downgrade the verdict?

## Acceptance Criteria

- [ ] BUG-2901 and BUG-2904 are merged.
- [ ] A missing/stale `screenshot.png` is detectable downstream of `evaluate`.
- [ ] `score` does not silently rubric-score a stale screenshot.
- [ ] Repeated screenshot failures converge to a terminal state with an honest
      verdict rather than exhausting `max_steps`.
- [ ] No behavior change for consumers whose screenshots succeed.
- [ ] `ll-loop validate` passes for the oracle and all five wrappers.
- [ ] `python -m pytest scripts/tests/` exits 0.
