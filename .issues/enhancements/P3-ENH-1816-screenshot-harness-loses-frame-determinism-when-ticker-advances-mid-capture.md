---
id: ENH-1816
title: Screenshot harness loses frame determinism when ticker advances mid-capture
type: ENH
priority: P3
captured_at: '2026-05-30T22:06:48Z'
completed_at: '2026-06-01T16:57:17Z'
discovered_date: 2026-05-30
discovered_by: capture-issue
status: done
parent: EPIC-1744
decision_needed: false
confidence_score: 100
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
implementation_order_risk: true
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

> **Selected:** Option A — Ticker stop/start via `window.__pixiApp` — harness-side fix with optional chaining; correctness lives entirely in the `evaluate` action, not in LLM-generated sketch code.

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

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-01.

**Selected**: Option A — Ticker stop/start via `window.__pixiApp`

**Reasoning**: Option A keeps all correctness within the harness's `evaluate` shell action, reusing the established `page.evaluate()` pattern already present in `html-website-generator.yaml:157`. The optional chaining (`?.`) ensures old sketches silently degrade rather than error. Option B's correctness depends on LLM generation fidelity — if the generated sketch omits the `__pauseAtFrame` check, the race condition silently persists with no observable error, making it fundamentally less reliable.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (ticker.stop+start) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B (in-page pause hook) | 1/3 | 1/3 | 1/3 | 1/3 | 4/12 |

**Key evidence**:
- **Option A**: `page.evaluate()` has direct precedent at `html-website-generator.yaml:157`; `window.__loopFrame` convention established; 6 new lines total across 3 loop YAMLs; no new abstractions
- **Option B**: `__pauseAtFrame` has zero prior art; split-ownership (harness sets signal, LLM implements handler) unreliable; ticker boilerplate grows 150%; no test precedent for asserting generate-prompt instruction text

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

1. **Approach decided (2026-06-01)**: Option A — ticker.stop+start via `window.__pixiApp` — selected; see Proposed Solution and Decision Rationale for full context. No further decision step needed before coding.
2. **Update `generate` prompts** (one change per loop):
   - `scripts/little_loops/loops/pixi-generative-art.yaml` — in `generate` state action, add to the "Three Pixi-specific rules" block: require `window.__pixiApp = app` after `new PIXI.Application(...)` initialization (Option A) **or** add the `window.__pauseAtFrame` branch inside the ticker callback (Option B)
   - `scripts/little_loops/loops/pixi-data-viz.yaml` — same addition to `generate` state action (lines 97–174)
   - `scripts/little_loops/loops/p5js-sketch-generator.yaml` — no `window.__pixiApp` needed; p5 global mode already exposes `noLoop()` / `loop()` as globals; document in the generate prompt that `noLoop()`/`loop()` will be called by the harness
3. **Update `evaluate` shell actions** — wrap `page.screenshot(...)` in all three files:
   - `scripts/little_loops/loops/p5js-sketch-generator.yaml:142–143` — replace `await page.screenshot(...)` with: `await page.evaluate(() => noLoop()); await page.screenshot({...}); await page.evaluate(() => loop());`
   - `scripts/little_loops/loops/pixi-generative-art.yaml:183–184` — replace with: `await page.evaluate(() => window.__pixiApp?.ticker?.stop()); await page.screenshot({...}); await page.evaluate(() => window.__pixiApp?.ticker?.start());`
   - `scripts/little_loops/loops/pixi-data-viz.yaml:198–199` — same Pixi stop/start pattern
4. **Add test coverage** in `scripts/tests/test_builtin_loops.py` — add `TestP5jsSketchGeneratorLoop`, `TestPixiGenerativeArtLoop`, `TestPixiDataVizLoop` classes (model on `TestHtmlWebsiteGeneratorLoop` at line 2783 for structure; model on `TestSvgImageGeneratorLoop.test_evaluate_action_has_stderr_redirect` at line 2968 for action string assertions); each must assert the `evaluate` state shell action contains both the pause and resume calls using the 3-line pattern: `state = data["states"].get("evaluate", {}); action = state.get("action", ""); assert "ticker.stop" in action`
5. **Verify determinism**: run `ll-loop run pixi-generative-art` twice on the same input; `cmp frame_0.png frame_0.png` (from two separate run directories) should exit 0
6. **Update `scripts/little_loops/loops/README.md`** — add catalog entries (one-line descriptions) for `p5js-sketch-generator`, `pixi-generative-art`, and `pixi-data-viz` under a new `## Animation / Generative Art` section (or similar); coordinate with ENH-1824 / ENH-1837 to avoid duplicate documentation work

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/guides/LOOPS_GUIDE.md` — Technique paragraphs for all three loops: add the ticker-pause step between waitForFunction and page.screenshot
8. Update `docs/guides/LOOPS_GUIDE.md` — Notes bullets for pixi loops: clarify that `window.__pixiApp` exposure is a required harness contract (not just PRNG seeding) for byte-level reproducibility
9. Update `scripts/little_loops/loops/README.md` — add missing catalog table entries for the three animation loops

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/p5js-sketch-generator.yaml`
- `scripts/little_loops/loops/pixi-generative-art.yaml`
- `scripts/little_loops/loops/pixi-data-viz.yaml`

### Dependent Files (Callers/Importers)
- No external callers. Each of the three loop YAMLs is self-contained; the Node.js screenshot inline script exists only inside that file's `evaluate` state. There are no shared helper modules or imported screenshot utilities to update.

### Similar Patterns
- `scripts/little_loops/loops/html-website-generator.yaml:157` — only existing `page.evaluate()` call in any loop YAML; pattern: `await page.evaluate(() => document.body.innerText.trim().length)` — precedent for injecting JS into the page from within the same `node -e` block
- `scripts/tests/test_builtin_loops.py:TestHtmlWebsiteGeneratorLoop` (line 2783) — test class structure to model new animation-loop test classes after
- `scripts/tests/test_builtin_loops.py:TestSvgImageGeneratorLoop` (line 2876) — second test template; adds `action_has_stderr_redirect` and `on_error` assertions

### Tests
- `scripts/tests/test_builtin_loops.py` — add three new test classes (`TestP5jsSketchGeneratorLoop`, `TestPixiGenerativeArtLoop`, `TestPixiDataVizLoop`) modeled on `TestHtmlWebsiteGeneratorLoop` (line 2783); each should assert that the `evaluate` state shell action contains both a ticker-pause call and a ticker-resume call around `page.screenshot`
- New determinism test (shell): run the same `index.html` twice with `ll-loop run`, compare output PNGs with `cmp` — zero byte differences expected

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — documents harness loop patterns; update the screenshot harness section to describe the ticker stop/start contract and the `window.__pixiApp` / `noLoop()` exposure requirement

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — three specific sub-sections need updating (all currently contain stale determinism claims):
  - `### p5js-sketch-generator — GAN-Style p5.js Sketch Loop` Technique paragraph: describes "wait for frame then screenshot" but omits the `noLoop()`/`loop()` ticker-pause wrapper; update to include the stop/start step
  - `### p5js-sketch-generator` Notes bullet: "the screenshot harness polls when waiting for each frame" — add that `noLoop()`/`loop()` is called around `page.screenshot()` as the mechanism that makes the frame pin reliable
  - `### pixi-generative-art — PixiJS Generative Art Loop` and `### pixi-data-viz — PixiJS Data Visualization Loop` Technique paragraphs: update to describe the `ticker.stop()`/`ticker.start()` wrapper
  - Notes bullets in both pixi sections: "A seeded deterministic PRNG … reproducible across iterations" — add that PRNG alone is insufficient; `window.__pixiApp` exposure and ticker pause are also required for byte-level reproducibility
- `scripts/little_loops/loops/README.md` — the three target loops (`p5js-sketch-generator`, `pixi-generative-art`, `pixi-data-viz`) are entirely absent from the loop catalog table; add one-line description entries (overlaps with ENH-1824 and ENH-1837 scope — coordinate to avoid duplicate work)

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-01_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 59/100 → LOW

### Outcome Risk Factors
- **Open decision must be resolved before starting** — Option A (ticker.stop/start via `window.__pixiApp`) vs Option B (in-page `window.__pauseAtFrame` pause hook) is unresolved. `decision_needed: true` already set. Run `/ll:decide-issue ENH-1816` first; the option choice determines what you write in the `generate` prompt and `evaluate` shell action across all 3 YAMLs.
- **Tests are co-deliverables** — no existing tests cover the three animation loops; `TestP5jsSketchGeneratorLoop`, `TestPixiGenerativeArtLoop`, `TestPixiDataVizLoop` must be written alongside the YAML changes (not after), so ticker-pause regressions are caught immediately rather than discovered during integration.
- **Moderate breadth across 6 sites** — 3 loop YAMLs + test file + LOOPS_GUIDE.md (4+ subsections per wiring analysis) + README.md; each change is locally contained but the total scope is broader than a typical 1-3 file fix; plan to stage LOOPS_GUIDE.md updates after the YAML and test work is complete.

## Resolution

Implemented Option A (ticker stop/start via `window.__pixiApp`):

- **`p5js-sketch-generator.yaml`**: `evaluate` state wraps `page.screenshot()` with `page.evaluate(() => noLoop())` before and `page.evaluate(() => loop())` after; `generate` prompt updated to document the harness contract.
- **`pixi-generative-art.yaml`**: `evaluate` state wraps `page.screenshot()` with `ticker?.stop()` / `ticker?.start()` via `window.__pixiApp`; `generate` prompt updated to require `window.__pixiApp = app` after initialization; comment block updated to four Pixi-specific rules.
- **`pixi-data-viz.yaml`**: Same Pixi ticker-pause treatment as `pixi-generative-art`.
- **`test_builtin_loops.py`**: Added `TestP5jsSketchGeneratorLoop` (13 tests), `TestPixiGenerativeArtLoop` (14 tests), `TestPixiDataVizLoop` (16 tests) — all assert the ticker-pause pattern is present and correctly ordered relative to `page.screenshot()`.
- **`docs/guides/LOOPS_GUIDE.md`**: Updated Technique paragraphs and Notes bullets for all three loops to describe the ticker-pause contract and clarify that PRNG seeding alone is insufficient for byte-exact reproducibility.
- **`scripts/little_loops/loops/README.md`**: Added `## Animation / Generative Art` section with catalog entries for all three loops.

42/42 new tests pass; pre-existing `test_cli_e2e` failure unrelated to this change.

## Session Log
- `/ll:manage-issue` - 2026-06-01T16:57:17Z - this session
- `/ll:ready-issue` - 2026-06-01T16:51:33 - `2614b32d-713a-4cbc-bfca-54faf6bf005d.jsonl`
- `/ll:confidence-check` - 2026-06-01T17:00:00 - `8f03e91a-c329-4afe-a781-e978a91f6da2.jsonl`
- `/ll:decide-issue` - 2026-06-01T16:46:31 - `52ddc94b-9fa4-4009-b7bb-9b3ebbaa93ed.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00 - `b847a03e-89d6-4a61-892d-ecc5a92b0fa2.jsonl`
- `/ll:wire-issue` - 2026-06-01T16:37:48 - `53fe137e-1768-4b04-961c-6f3bedb719cb.jsonl`
- `/ll:refine-issue` - 2026-06-01T16:31:37 - `92bcd8b4-38a6-46b1-9488-9de681167c3e.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:16 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:17 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:format-issue` - 2026-05-31T02:12:19 - `6c1090c2-86b4-43c5-9308-02fd0823f906.jsonl`
- `/ll:capture-issue` - 2026-05-30T22:06:48Z - this session
**Open** | Created: 2026-05-30 | Priority: P3
