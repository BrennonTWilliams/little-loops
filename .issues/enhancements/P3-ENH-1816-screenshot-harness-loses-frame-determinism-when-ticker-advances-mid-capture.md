---
id: ENH-1816
title: Screenshot harness loses frame determinism when ticker advances mid-capture
type: ENH
priority: P3
captured_at: "2026-05-30T22:06:48Z"
discovered_date: 2026-05-30
discovered_by: capture-issue
status: open
parent: EPIC-1744
---

# ENH-1816: Screenshot harness loses frame determinism when ticker advances mid-capture

## Summary

The animation-loop screenshot harness (`p5js-sketch-generator`, `pixi-generative-art`, `pixi-data-viz`) uses `page.waitForFunction(() => __loopFrame >= N)` to pin captures to specific frames. But the predicate returns the moment the condition becomes true, and the ticker keeps advancing during the ~50-100ms `page.screenshot()` call. So capture lands on frame N, N+1, or N+2 depending on system load, breaking byte-exact determinism across runs of identical `index.html`.

## Current Behavior

Two runs of the same sketch HTML produce screenshots differing by ~1KB on ~300KB files (measured this session on a Pixi flow-field sketch). Sketch code itself is clean — no `Date.now`, `performance.now`, `Math.random`, or `requestAnimationFrame` calls; all randomness is seeded mulberry32 and all motion is driven by `window.__loopFrame`. So the non-determinism is in the harness, not the sketch.

This matters because the `generate` prompts in all three loops explicitly promise:

> "The screenshot harness captures specific __loopFrame values and requires the same input to produce the same pixels."

That promise is currently false, which means iteration-to-iteration critique can chase noise that isn't actually a regression in the sketch.

## Expected Behavior

The harness should produce byte-identical screenshots for identical input HTML across runs. When `__loopFrame` is pinned to a specific frame N, the captured screenshot must always be frame N — never N+1 or N+2 — regardless of system load or timing variance during the `page.screenshot()` call.

This means: same `index.html` run twice → `cmp frame_*.png frame_*.png` reports no differences.

## Motivation

If the harness were deterministic, two iterations producing visually-similar but byte-different frames would be a real signal (the LLM changed something) rather than noise (the ticker happened to advance one extra tick). Determinism also makes it possible to assert pixel-equality in eval tests.

## Proposed Solution

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

## Success Metrics

- **Determinism test**: Same `index.html` run twice → `cmp` reports 0 byte differences across all captured frames
- **No regression**: Existing loops (p5js-sketch-generator, pixi-generative-art, pixi-data-viz) continue to produce valid screenshots with no functional regressions
- **Eval reliability**: Iteration-to-iteration screenshot diffs become genuine change signals rather than ticker-timing noise

## Scope Boundaries

- **In scope**: The three animation-loop screenshot harnesses (`p5js-sketch-generator`, `pixi-generative-art`, `pixi-data-viz`), their `generate` prompt instructions, and their `evaluate` shell actions
- **Out of scope**: Non-animation loops, static screenshot captures, non-Pixi/non-p5 rendering engines, changing the sketch code generation logic itself
- **Out of scope**: Guaranteeing determinism across different browser versions or platforms — only same-machine, same-browser determinism is targeted

## API/Interface

The harness-to-sketch contract changes: sketches must expose their renderer reference so the harness can stop/start the ticker around screenshots.

For Pixi sketches:
```js
// Sketch must expose:
window.__pixiApp = app;  // PIXI.Application instance
```

For p5 sketches:
```js
// Harness calls:
noLoop();  // before screenshot
loop();    // after screenshot
```

These are additive requirements — sketches that don't expose the reference will still work (unguarded `?.` access in the harness), but won't benefit from determinism.

## Implementation Steps

1. Pick one approach (ticker.stop+start vs. in-page pause hook).
2. Update the `generate` prompt in all three affected loops to require the sketch expose `window.__pixiApp` (or call `noLoop()`).
3. Update the `evaluate` shell action in all three to wrap screenshots with the stop/start dance.
4. Verify with a determinism test: same `index.html` run twice, `cmp` frames byte-exact.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/p5js-sketch-generator.yaml`
- `scripts/little_loops/loops/pixi-generative-art.yaml`
- `scripts/little_loops/loops/pixi-data-viz.yaml`

### Dependent Files (Callers/Importers)
- TBD - use grep to find references to the screenshot harness helpers

### Similar Patterns
- TBD - search for other loops that use `page.waitForFunction` + `page.screenshot` patterns

### Tests
- TBD - add determinism test: same HTML → two captures → cmp byte-exact

### Documentation
- TBD - update loop docs if prompt contract changes

### Configuration
- N/A

## Impact

- **Priority**: P3 - Determinism bug undermines eval signal quality but doesn't break functionality; loops still produce valid screenshots
- **Effort**: Small - Three loop YAML files, prompt text updates, and a stop/start wrapper in evaluate shell actions
- **Risk**: Low - Additive change using optional chaining (`?.`); sketches that don't expose the reference continue working
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `captured`

## Session Log
- `/ll:verify-issues` - 2026-05-31T05:40:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:format-issue` - 2026-05-31T02:12:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c1090c2-86b4-43c5-9308-02fd0823f906.jsonl`
- `/ll:capture-issue` - 2026-05-30T22:06:48Z - this session
**Open** | Created: 2026-05-30 | Priority: P3
