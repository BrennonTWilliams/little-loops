---
id: ENH-1816
captured_at: "2026-05-30T22:06:48Z"
discovered_date: 2026-05-30
discovered_by: capture-issue
status: open
---

# ENH-1816: Screenshot harness loses frame determinism when ticker advances mid-capture

## Summary

The animation-loop screenshot harness (`p5js-sketch-generator`, `pixi-generative-art`, `pixi-data-viz`) uses `page.waitForFunction(() => __loopFrame >= N)` to pin captures to specific frames. But the predicate returns the moment the condition becomes true, and the ticker keeps advancing during the ~50-100ms `page.screenshot()` call. So capture lands on frame N, N+1, or N+2 depending on system load, breaking byte-exact determinism across runs of identical `index.html`.

## Current Behavior

Two runs of the same sketch HTML produce screenshots differing by ~1KB on ~300KB files (measured this session on a Pixi flow-field sketch). Sketch code itself is clean — no `Date.now`, `performance.now`, `Math.random`, or `requestAnimationFrame` calls; all randomness is seeded mulberry32 and all motion is driven by `window.__loopFrame`. So the non-determinism is in the harness, not the sketch.

This matters because the `generate` prompts in all three loops explicitly promise:

> "The screenshot harness captures specific __loopFrame values and requires the same input to produce the same pixels."

That promise is currently false, which means iteration-to-iteration critique can chase noise that isn't actually a regression in the sketch.

## Motivation

If the harness were deterministic, two iterations producing visually-similar but byte-different frames would be a real signal (the LLM changed something) rather than noise (the ticker happened to advance one extra tick). Determinism also makes it possible to assert pixel-equality in eval tests.

## Suggested Fix

Stop the ticker before screenshot, restart after. For Pixi:

```js
await page.waitForFunction(([n]) => window.__loopFrame >= Number(n), [f], { timeout: 30000 });
await page.evaluate(() => window.__pixiApp?.ticker?.stop());
await page.screenshot({ path: ... });
await page.evaluate(() => window.__pixiApp?.ticker?.start());
```

Requires the sketch to expose its `app` reference on `window.__pixiApp` — bake this into the `generate` prompt instructions for both pixi loops. For p5, `noLoop()` / `loop()` is the equivalent and must be similarly exposed.

Alternative: change the wait condition to fire only when `__loopFrame === N` exactly, with a one-shot in-page hook that pauses on the target frame:

```js
window.__pauseAtFrame = N;  // set from harness via page.evaluate
// In sketch ticker:
if (window.__pauseAtFrame !== undefined && window.__loopFrame >= window.__pauseAtFrame) {
  app.ticker.stop();
  window.__pauseAtFrame = undefined;
}
```

## Implementation Steps

1. Pick one approach (ticker.stop+start vs. in-page pause hook).
2. Update the `generate` prompt in all three affected loops to require the sketch expose `window.__pixiApp` (or call `noLoop()`).
3. Update the `evaluate` shell action in all three to wrap screenshots with the stop/start dance.
4. Verify with a determinism test: same `index.html` run twice, `cmp` frames byte-exact.

## Affected Files

- `scripts/little_loops/loops/p5js-sketch-generator.yaml`
- `scripts/little_loops/loops/pixi-generative-art.yaml`
- `scripts/little_loops/loops/pixi-data-viz.yaml`

## Session Log
- `/ll:capture-issue` - 2026-05-30T22:06:48Z - this session
