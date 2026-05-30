---
status: open
discovered_date: 2026-05-30
discovered_by: capture-issue
captured_at: "2026-05-30T22:43:51Z"
labels: [loop-refinement, harness, captured]
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

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/html-website-generator.yaml` — add `smoke_test` state, re-route `score.on_yes`

### Tests
- Existing tests in `scripts/tests/test_builtin_loops.py` should continue to pass (loop structure validation)
- Manual verification: run the loop against a known-broken HTML artifact and confirm `smoke_test` catches it

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `smoke_test` state definition to `html-website-generator.yaml`
2. Change `score.on_yes` from `done` to `smoke_test`
3. Run `ll-loop validate html-website-generator` to confirm no structural errors
4. Manual smoke test: run loop with a simple description, verify `smoke_test` state executes

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
- `/ll:format-issue` - 2026-05-30T22:46:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fabe793e-a48c-46ba-8f98-a5684209ca60.jsonl`
- `/ll:capture-issue` - 2026-05-30T22:43:51Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a21d14e7-ea27-437a-b7be-dfdc28dd7d84.jsonl`

---

**Open** | Created: 2026-05-30 | Priority: P3
