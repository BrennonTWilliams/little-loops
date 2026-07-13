---
id: ENH-2625
priority: P3
type: ENH
status: done
discovered_date: 2026-07-13
discovered_by: capture-issue
confidence_score: 92
outcome_confidence: 88
completed_at: 2026-07-13T01:13:20-05:00
---

# ENH-2625: Iframe-free Shadow DOM composition for interactive-component-generator

## Summary

Make the `interactive-component-generator` FSM loop iframe-free by defaulting its
`compose_isolation` knob to **Shadow DOM** (per-component custom elements) and replacing
`iframe` with two non-shadow fallbacks. The loop still emits a single self-contained,
interaction-first, animated `index.html` — it just no longer relies on iframes to keep
independently-built components from colliding.

## Current Behavior

`scripts/little_loops/loops/interactive-component-generator.yaml` composed the winning
components into one file using `compose_isolation` defaulting to `iframe` (`srcdoc`), with
`shadow`/`scoped` as alternates. iframes gave brute-force CSS+JS+lib isolation but fought
every quality goal of the artifact:

- blocked inherited fonts/colors, so theming had to be re-injected per frame;
- fired `@media` breakpoints against each frame's own narrow viewport, breaking responsiveness;
- required a `ResizeObserver`/`onload` auto-size hack (a standing bug class);
- fragmented the accessibility tree and tab order, and broke Ctrl-F / print.

## Motivation

For a polished, cohesive, animated page the iframe is the *worst* isolation choice — the only
thing it buys is isolation, and that can be re-solved at compose time. Shadow DOM gives native
CSS + `id`-namespace encapsulation while inheritable properties and design tokens still flow in
via `:host`, so components read as one page with no sizing hack, better a11y, and clean printing.

### Two facts that drove the design

1. **Shadow DOM encapsulates CSS and `id`s, NOT JS scope.** Two components with top-level
   `const data = …` still throw a page-killing `SyntaxError`. So *every* non-iframe mode must
   give each component its own JS scope (IIFE/closure) with a scoped `root`, querying `root`
   instead of `document`.
2. **Manifest selectors must stay resolvable.** Each `manifest.json` selector (e.g. `#sort-btn`)
   is authored against the isolated component. Shadow DOM re-scopes ids per component so manifests
   keep working unchanged; pure namespacing does not (duplicate `#sort-btn` becomes ambiguous).
   This is the decisive reason Shadow is the default over `scoped`.

## Expected Behavior

Delivered — all loop changes in `scripts/little_loops/loops/interactive-component-generator.yaml`:

1. **`context.compose_isolation`** default `"iframe"` → `"shadow"`. Modes are now
   `shadow` (default, native CSS+id isolation) | `scope-css` (`@scope`, most seamless theming) |
   `scoped` (build-time namespacing, most portable). `iframe` removed entirely.
2. **`compose` state** — rewrote the embedding block:
   - **shadow (default):** each winner becomes a `<ll-comp-<id> data-ll-component="<id>">` custom
     element whose `connectedCallback` attaches an open shadow root, injects the component's
     `<style>` + markup, and runs its JS in that closure with `const root = this.shadowRoot`,
     rewriting `document.querySelector*`/`getElementById` → `root.*`. Design tokens pass down as
     CSS custom properties on the host so `:host`/`var(--…)` inherit them.
   - **scope-css:** inline in `<div data-ll-component="<id>">`, wrap CSS in
     `@scope ([data-ll-component="<id>"]) { … }`, prefix `@keyframes`/`@font-face` names with the
     id, IIFE the JS against a scoped `root`.
   - **scoped:** full namespacing (classes/ids/keyframes prefixed, IIFE) + prefixed manifest
     selectors, as the portable fallback.
   - Deleted the iframe `srcdoc` bullet and the shared auto-size script; added a mode-agnostic
     "own JS scope + carry `data-ll-component`" rule.
3. **`verify_final` state** — replaced iframe `contentFrame()` dispatch with host-scoped
   `page.locator('[data-ll-component="<id>"]').locator(selector)`, which auto-pierces open shadow
   roots and disambiguates duplicate ids under the non-shadow modes.
4. **`build_component` generate_prompt** — hardened the per-component contract so components are
   born shadow-relocatable: scope DOM queries to the `#ll-root` subtree, don't style bare
   `body`/`html`/`:root` or rely on a global reset, and prefix any `@keyframes` name with the
   component id.

Documentation kept in sync (mode lists only):

- `docs/guides/LOOPS_REFERENCE.md` — `iframe / shadow / scoped` → `shadow / scope-css / scoped`.
- `scripts/little_loops/loops/README.md` — same mode-list update.

## Impact

The composed `index.html` now reads as one cohesive page: design tokens inherit through the shadow
boundary (no per-frame theme re-injection), components respond to the real page width, the
`ResizeObserver` auto-size hack is gone (a whole bug class removed), and accessibility, Ctrl-F, and
printing work across the full document. Isolation is preserved via native Shadow DOM encapsulation
plus per-component JS scoping. No test or FSM-validation surface changed (knob keys are unchanged).

## Verification

- `python -c "import yaml; yaml.safe_load(open('.../interactive-component-generator.yaml'))"` — parses.
- `ll-loop validate interactive-component-generator` — valid (meta-rules MR-1…MR-11 unaffected; no
  new `$$`/bash-default violations in the edited shell body).
- `python -m pytest scripts/tests/test_builtin_loops.py -k InteractiveComponentGenerator` — 10 passed
  (structural + `compose_isolation`/knob-existence tests; those assert keys, not values).

## Scope Boundaries

- FEAT-2343 (the loop's origin issue) still documents the original "defaulting to iframe" design
  decision; left as historical record per the session's chosen scope.
- The `oracles/generator-evaluator` oracle itself was not modified — the born-composable contract
  change is confined to this loop's `generate_prompt`.
- No changes to FSM engine, validation rules, or the test suite (knob keys unchanged).

## Status

Done — implemented and verified this session (2026-07-13). YAML parses, `ll-loop validate`
passes, and the 10 `InteractiveComponentGenerator` tests pass. Not yet committed.


## Session Log
- `hook:posttooluse-status-done` - 2026-07-13T06:14:19 - `b51e9b61-18e5-40ec-90d6-3ebc8d50bf90.jsonl`
