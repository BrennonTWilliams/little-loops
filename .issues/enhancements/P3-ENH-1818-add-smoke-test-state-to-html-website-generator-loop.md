---
status: done
discovered_date: 2026-05-30
discovered_by: capture-issue
captured_at: '2026-05-30T22:43:51Z'
completed_at: '2026-05-31T00:27:39Z'
labels:
- loop-refinement
- harness
- captured
confidence_score: 100
outcome_confidence: 83
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
---

# P3-ENH-1818: Add smoke-test state to html-website-generator loop

## Summary

The `html-website-generator` loop's `score` state relies entirely on LLM screenshot evaluation, routing directly to the `done` terminal via `output_contains: "ALL_PASS"`. When the LLM cannot read the screenshot, it silently falls back to source-only scoring, missing functional defects like destroyed input focus and hardcoded content. Add a `smoke_test` state between `score` and `done` that runs Playwright-powered functional checks (console errors, content presence, basic interactivity) before accepting the artifact.

## Current Behavior

The `score` state uses `action_type: prompt` to read a screenshot and output `ALL_PASS` or `ITERATE`. The evaluator `output_contains: "ALL_PASS"` can verify the LLM wrote the pass string but cannot verify that the LLM actually processed the image vs. falling back to reading the HTML source. On `ALL_PASS`, routing goes directly to the `done` terminal with no functional verification of the generated website.

## Expected Behavior

After the LLM scores the design and outputs `ALL_PASS`, a `smoke_test` shell state runs Playwright to perform basic functional verification:

- No JavaScript console errors
- Page has meaningful text content (>20 chars of body text)
- Page has interactive elements (buttons, links, inputs, etc.)

If smoke tests pass, route to `done`. If they fail, route back to `generate` for another iteration with the failure reason in context.

## Motivation

The `/ll:debug-loop-run html-website-generator` analysis found that an artifact with two functional defects (renderAll destroying input focus, hardcoded slugs) passed the screenshot-based evaluator because the LLM fell back to source-only scoring. A shell-level smoke test state would have caught both defects — console errors from the broken renderAll, and missing dynamic content from the hardcoded slugs. This closes a systematic blind spot where `output_contains` on LLM text output cannot verify multimodal inputs were actually processed.

## Proposed Solution

Add a `smoke_test` state to `loops/html-website-generator.yaml` between `score` and `done`:

```yaml
smoke_test:
    action_type: shell
    action: |
      node -e "
      const { chromium } = require('playwright');
      (async () => {
        const browser = await chromium.launch();
        const page = await browser.newPage();
        const errors = [];
        page.on('pageerror', e => errors.push(e.message));
        await page.goto('file://' + process.cwd() + '/${context.run_dir}/index.html');
        await page.waitForTimeout(1500);
        const textLen = await page.evaluate(() => document.body.innerText.trim().length);
        if (textLen < 20) { console.log('FAIL:minimal_content'); process.exit(1); }
        if (errors.length > 0) { console.log('FAIL:js_errors'); process.exit(1); }
        console.log('SMOKE_PASS');
        await browser.close();
      })();
      " 2>&1 && echo "VERIFIED"
    evaluate:
      type: output_contains
      pattern: "VERIFIED"
    on_yes: done
    on_no: generate
    on_error: generate
```

Route `score.on_yes` to `smoke_test` instead of directly to `done`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Playwright package name**: The codebase pattern for inline Node.js Playwright scripts uses `require('@playwright/test')` (see `scripts/little_loops/loops/p5js-sketch-generator.yaml` state `evaluate` line 132, `pixi-data-viz.yaml` state `evaluate` line 188). The proposed snippet uses `require('playwright')` — align with the existing dependency to avoid requiring an additional npm package.
- **Playwright availability**: The `capture` state (line 82-90) already uses `playwright screenshot` CLI, proving Playwright is available in the loop's execution environment. The `on_error: generate` routing on `smoke_test` means transient Playwright failures retry rather than hard-fail, consistent with the `capture` state's `on_error: failed` which bails on missing/broken Playwright.
- **Established pattern**: `scripts/little_loops/loops/svg-textgrad.yaml` state `verify_score` (line 158) is the most direct analog — a shell verification state between LLM score and `done` terminal that exits with a compound token (`SHELL_PASS`) for unambiguous `output_contains` matching. The comment at the top of that state reads "Decoupling routing from the LLM prompt prevents self-certification inflation" — the exact same motivation as this issue.
- **Compound token convention**: Use a compound token like `SMOKE_PASS` (not bare `PASS`) for the `output_contains` pattern. The test at `scripts/tests/test_builtin_loops.py:136` (`test_no_bare_pass_token_in_output_contains`) enforces this across all built-in loops.
- **shell_exit fragment alternative**: `scripts/little_loops/loops/lib/common.yaml` (line 15) defines a `shell_exit` fragment that evaluates by exit code rather than `output_contains`. The proposed `output_contains` approach is preferable here because it can distinguish "smoke tests ran and passed" (exit 0 + `SMOKE_PASS` in output) from "shell succeeded silently" (exit 0 but no token), which bare `exit_code` evaluation cannot.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/html-website-generator.yaml` — add `smoke_test` state, re-route `score.on_yes`

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestHtmlWebsiteGeneratorLoop` class (line 2646) contains 10 structural tests that need updating:
  - `test_required_states_exist` (line 2663): add `"smoke_test"` to the `required` set. Note: this test currently references `"evaluate"` but the actual state is named `"capture"` — a pre-existing naming discrepancy to fix alongside this change.
  - `test_score_state_routes_to_done_on_pass` (line 2697): change assertion from `state.get("on_yes") == "done"` to `"smoke_test"`.
  - New test needed: `test_smoke_test_state_is_shell` — verify `smoke_test` uses `action_type: shell` with an `output_contains` evaluator.
- `scripts/tests/test_builtin_loops.py` — `TestBuiltinLoopFiles.test_all_validate_as_valid_fsm` (line 37): auto-validates all built-in loops; will catch structural errors automatically.
- Manual verification: run the loop against a known-broken HTML artifact and confirm `smoke_test` catches it

### Similar Patterns
- `scripts/little_loops/loops/svg-textgrad.yaml` state `verify_score` (line 158) — shell verification state between LLM `score` and `done` terminal. The same motivation: "Decoupling routing from the LLM prompt prevents self-certification inflation."
- `scripts/little_loops/loops/p5js-sketch-generator.yaml` state `evaluate` (line 131) — inline Node.js Playwright script via `node -e` with `require('@playwright/test')`. Uses `page.on('pageerror')`-style error capture pattern that the smoke_test state should follow.
- `scripts/little_loops/loops/general-task.yaml` state `verify_step` (line 160) — shell verification state with `output_contains` + compound token (`VERIFY_PASS`), routes back to work on failure.

### Related Issues
- `.issues/enhancements/P3-ENH-1819-*.md` — follow-up issue to add a validation WARNING when harness loops route LLM multimodal evaluation directly to a terminal (the systematic blind spot this fix addresses at the instance level)

### Existing Analysis
- `.loops/reviews/html-website-generator-20260530-061937.md` — loop review that identified the functional defects (renderAll destroying input focus, hardcoded slugs) that passed the screenshot-based evaluator

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — `html-website-generator` section (line 1192): FSM flow diagram at lines 1225-1229 hardcodes `ALL_PASS → done`; must update to `ALL_PASS → smoke_test → done`. Surrounding prose at line 1196 ("a scorer judges... routing back to the generator... until all scores clear...") describes current behavior without the smoke test gate — update to mention the smoke test verification step.

### Configuration
- N/A

## Implementation Steps

1. Add `smoke_test` state definition to `scripts/little_loops/loops/html-website-generator.yaml` (insert between `score` state ending at line 137 and `done` state starting at line 139)
2. Change `score.on_yes` at line 135 from `done` to `smoke_test`
3. Run `ll-loop validate html-website-generator` to confirm no structural errors (calls `load_and_validate()` → `validate_fsm()` in `scripts/little_loops/fsm/validation.py:739`)
4. Update tests in `scripts/tests/test_builtin_loops.py`:
   - `test_required_states_exist` (line 2663): add `"smoke_test"` to required set; also fix pre-existing naming discrepancy (`"evaluate"` → `"capture"`)
   - `test_score_state_routes_to_done_on_pass` (line 2697): change expected value from `"done"` to `"smoke_test"`
   - Add `test_smoke_test_state_is_shell` and `test_smoke_test_routes_to_done_on_pass` following existing test patterns in the class
5. Run `python -m pytest scripts/tests/test_builtin_loops.py::TestHtmlWebsiteGeneratorLoop -v` to verify all structural tests pass
6. Manual smoke test: run loop with a simple description, verify `smoke_test` state executes and routes correctly

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/guides/LOOPS_GUIDE.md` — `html-website-generator` section (line 1192): update FSM flow diagram (lines 1225-1229) from `ALL_PASS → done` to `ALL_PASS → smoke_test → done`; update surrounding prose to mention the smoke test verification step

## API/Interface

N/A - No public API changes (loop-internal state addition only)

## Success Metrics

- Loop completes `smoke_test` state before reaching `done` terminal
- A generated page with JS console errors is caught and routed back to `generate`
- A generated page with <20 chars of body text is caught and routed back to `generate`

## Scope Boundaries

- Smoke test covers only JS console errors and content presence — not accessibility, performance, or visual regression
- Does not add validation rules to the FSM validator (tracked separately in ENH-1819)
- Does not modify other harness loops (e.g., `svg-image-generator`)

## Impact

- **Priority**: P3 — closes a known blind spot but loop already works for the common case (screenshot is readable)
- **Effort**: Small — one new state, one routing change, ~25 lines
- **Risk**: Low — additive change, existing behavior unchanged; `on_error: generate` means Playwright failures retry rather than hard-fail
- **Breaking Change**: No

## Related Key Documentation

- [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md)
- [.claude/CLAUDE.md](../../.claude/CLAUDE.md)

## Labels

`loop-refinement`, `harness`, `captured`

## Session Log
- `/ll:manage-issue` - 2026-05-31T00:27:39Z - `662dff29-eba0-4da7-a26d-d3806b0f2630.jsonl`
- `/ll:ready-issue` - 2026-05-31T00:23:12 - `26f3ac82-3b0b-4510-bab6-71b9d6d07f0d.jsonl`
- `/ll:wire-issue` - 2026-05-31T00:17:08 - `1fcd27a7-fe20-47b8-9821-a80e9338e768.jsonl`
- `/ll:refine-issue` - 2026-05-31T00:13:14 - `4e73e9f8-d1ee-47ab-8ed9-a2af90a69a5e.jsonl`
- `/ll:format-issue` - 2026-05-30T22:46:44 - `fabe793e-a48c-46ba-8f98-a5684209ca60.jsonl`
- `/ll:capture-issue` - 2026-05-30T22:43:51Z - `a21d14e7-ea27-437a-b7be-dfdc28dd7d84.jsonl`
- `/ll:confidence-check` - 2026-05-30T23:45:00Z - `cfd01907-a230-402f-920c-2f7c5c0d48dc.jsonl`

---

**Open** | Created: 2026-05-30 | Priority: P3
