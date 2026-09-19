---
id: BUG-3516
type: BUG
title: 'Policy builder: fallback row highlighted as Try-it winner before any sample
  value is entered'
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T21:16:29Z'
relates_to:
- ENH-3500
- ENH-3514
blocked_by:
- ENH-3514
---

# BUG-3516: Policy builder: fallback row highlighted as Try-it winner before any sample value is entered

## Summary

Split from ENH-3514 (found by the ENH-3500 audit). In `decision_table` mode the "Otherwise →" fallback row is highlighted as the Try-it winner before any sample value has been entered. In `auth-populated-decision_table-dark-w1280-offline.png` this is the "saturated green block": `.rule-winner` on `#fallback-row`, painted only behind the label because `#f-fallback` has its own background.

## Current Behavior

`updateTryIt` (`policy-router-builder.html.tmpl`) skips blank `#tryit-inputs [data-dim]` values, so with every input blank it calls `evaluateModel(model, {})`; no rule matches, the result is `isFallback`, and `_highlightWinner` adds `.rule-winner` (`outline` + `background: var(--color-status-success-bg)`) to `#fallback-row` on every render of a freshly opened page. The `issue_lifecycle` path (`updateFrontmatterTryIt`) already clears the highlight when its input is blank — the two Try-it paths disagree.

## Expected Behavior

No winner is highlighted until at least one Try-it input has a value (matching `updateFrontmatterTryIt`). When the fallback genuinely wins, the highlight covers the row consistently (label and select) in both themes.

## Motivation

- A highlighted "winner" before any input reads as a result the user never asked for, and in dark theme looks like a styling glitch (it was filed as one in the ENH-3500 audit).
- The `decision_table` and `issue_lifecycle` Try-it paths disagree on blank input; aligning them removes a special case.

## Proposed Solution

In `updateTryIt`, when `scores` is empty call `_highlightWinner({ ruleIndex: -1, target: null, isFallback: false })` and return, mirroring the blank-input branch of `updateFrontmatterTryIt`. For the genuine-fallback-win case, make the `.rule-winner` treatment on `.fallback-row` read as one row (e.g. padding + transparent select background inside `.fallback-row.rule-winner`), reusing existing `--color-status-*` tokens so `test_enh3506_policy_builder_theme_parity.py` stays green.

## Integration Map

### Files to Modify
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — `updateTryIt`, `.rule-winner` / `.fallback-row` CSS

### Tests
- `.loops/probes/enh-3500-audit-probes.mjs` — add the blank/matching/fallback assertions (rendered DOM; on-demand, not a pytest gate)
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` — regenerate (byte-compared in `test_enh3035_artifact_template_kit.py`)
- `scripts/tests/js/policy_validator.test.mjs` — `updateTryIt` sits outside the `_newBug3502Sandbox` slices; confirm the literal slice markers do not move

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/js/policy_validator.test.mjs` — **new test**, `BUG-3516: updateTryIt with all-blank inputs clears winner`, next to the `BUG-3502:` tests; reuse `_extractBetween(_templateSrc, "function _highlightWinner(result) {", "// FEAT-3474: the issue_lifecycle Try-it panel", …)` and a `_newBug3502Sandbox`-style `vm` context (stub `state`, `buildModel`, `evaluateModel`, `updateFrontmatterTryIt`, `document.querySelectorAll` for `#tryit-inputs [data-dim]` / `.rule-card`, and `$("fallback-row").classList`). Assert no `rule-winner` when all blank, added on fallback-only match, cleared again on re-blank. Runs under pytest via `test_policy_builder_node_gate.py` (skips without node), so it covers the AC without a browser probe [Agent 3 finding]
- `scripts/tests/test_policy_builder_emit.py` — optional text-level assertion beside `test_fallback_footer_is_structured_not_free_text` that the stamped CSS contains a `.fallback-row.rule-winner` rule; `id="fallback-row"` markup must stay `<input`-free [Agent 3 finding]
- `scripts/tests/test_enh3035_artifact_template_kit.py::test_policy_builder_renders_byte_identically_to_golden_fixture` — the only test that breaks (byte-compare); golden lines affected: `.rule-winner` CSS (~L324), `.fallback-row` (~L339-340), `_highlightWinner`/`updateTryIt` (~L6022-6033) [Agent 2/3 finding]
- `.loops/verify-enh-3506-theme.yaml` + `.loops/probes/enh-3506-theme-probes.mjs` — on-demand theme/contrast check; rerun after adding the `.fallback-row.rule-winner` rule (it measures a synthetic `.rule-card.rule-winner`, not `#fallback-row`) [Agent 1/2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/POLICY_ROUTER_GUIDE.md` (~L292) — says the Try it panel "highlights the rule that would win"; still accurate, but verify it does not imply a winner shows before input. No edit expected [Agent 2 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/artifact/policy_builder.py` — `render_policy_builder_html` stamps the template verbatim (design-token CSS + core JS) into `policy-router-builder.html`; the only producer, so no packaged/mirror copy of the template needs a parallel edit [Agent 1/2 finding]
- `policy-router-builder.html.tmpl` `updatePreview` (~L1802) and `renderTryIt` (~L1205-1210) — both reach `updateTryIt`; `renderTryIt` rebuilds inputs blank, so the early return also fires after every render/mode switch; with zero dimensions "all blank" is vacuously true (highlight cleared, acceptable) [Agent 2 finding]
- `#fm-tryit-hint` / `#live-status` — not written by `updateTryIt`, so the early return leaves no stale result text [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- `updateTryIt` (`policy-router-builder.html.tmpl` ~1230-1246) filters blank inputs per element (`if (el.value === "") return;`, ~1241) but has no "all blank" check, so `scores` is `{}` and `evaluateModel(model, {})` still runs. `evaluateModel` (`policy_builder_core.mjs` ~452-469) compiles the authored rules plus a derived catch-all; `_traceCompiledRules` (~504) lets that catch-all win with `ruleIndex: -1, isFallback: true`.
- `_highlightWinner` (~1218-1228) is the only place `rule-winner` is added or removed. It always clears every `.rule-card` and `#fallback-row` first, then returns early when `result.target == null`. The existing no-winner shape `{ ruleIndex: -1, target: null, isFallback: false }` (used at ~1236, ~1271, ~1279) is therefore a complete clear.
- Callers of `updateTryIt`: `renderTryIt` (~1177-1211, end of decision_table path, and `oninput`/`onchange` at ~1205-1206) and `updatePreview` (~1802). `renderAll` calls `renderTryIt` then `updatePreview`, so `updateTryIt` runs twice per full render — the blank-state clear must be idempotent. `policy_builder_core.mjs` has no callers of `updateTryIt`/`_highlightWinner`.
- Related disagreement: `updateFrontmatterTryIt` clears only on blank or unparseable text; a non-blank frontmatter that encodes to zero scores still reaches `evaluateModel` and can highlight the fallback. Out of scope here, but the "no input → no winner" contract is per-path, not shared.
- CSS: `.rule-winner` (~131-134) sets `outline` + `background: var(--color-status-success-bg, #d4edda)` and no `color`. `.fallback-row` (~146-147) sets only `font-style`/`opacity`/select `max-width`; there is no `.fallback-row.rule-winner` rule and no `#f-fallback` rule. The select's opaque `background: var(--color-surface-primary)` comes from the generic `input, select, textarea, button` rule (~94-101) — that is the "painted only behind the label" cause. Markup is `<div class="row fallback-row" id="fallback-row"><span>Otherwise →</span><select id="f-fallback">` (~251-254).

### Constraints

- Theme parity (`test_enh3506_policy_builder_theme_parity.py`): every `var(--x)` in the template CSS must be declared in all stamped blocks (profiles `default`, `editorial-mono`, `warm-paper`; light and dark; packaged and mirror), or `test_refs_declared_with_resolved_values` fails (~line 149). `PAIRS` (~38-48) enforces 4.5:1 contrast for `--color-text-primary` on `--color-status-success-bg` (the `.rule-winner` inherited-text pair). Any new background/text combination on the winner row is not covered by `PAIRS` unless added.
- `test_policy_builder_emit.py::test_fallback_footer_is_structured_not_free_text` asserts `id="fallback-row"`, `<select id="f-fallback"`, and that the `<div class="row fallback-row"…>` element contains no `<input` and no "del" — the fallback-row markup must keep that shape.
- Golden `golden_policy_router_builder.html` is byte-compared in `test_enh3035_artifact_template_kit.py::test_policy_builder_renders_byte_identically_to_golden_fixture` (inputs pinned by `_pin_golden_render_inputs`: `default` profile, dark, empty skill catalog, version `0.0.0-golden`). Any template edit forces regeneration. No regeneration script or flag was found; other issues disagree on the method (ENH-3513: "by hand after reviewing the diff"; FEAT-3488/3503: "through the existing generator") — treat regeneration as rendering via `cmd_policy_builder` under the pinned inputs and review the diff.
- `policy_validator.test.mjs` has no references to `updateTryIt`, `_highlightWinner`, `rule-winner`, `fallback-row` or `f-fallback`. Its slice markers (`let state = seedExample();` … `function buildModel() {`; `$("open-project-input").onchange = …` … `$("undo-btn").onclick = …`) bracket regions that do not contain `updateTryIt`, so the edit is safe as long as those literal markers are untouched.
- Probe correction: `.loops/probes/enh-3500-audit-probes.mjs` is a data-collection audit (`COLLECT`, ~line 69) with no pass/fail assertions and no winner-state references; the blank/match/fallback checks are a new addition, not an extension of existing assertions. `.loops/probes/enh-3506-theme-probes.mjs` (~72, ~96) measures contrast on a synthetic `.rule-card.rule-winner` element and never drives `updateTryIt`. No existing test or probe exercises the winner class after a Try-it input event.

## Implementation Steps

1. In `updateTryIt`, clear the highlight and return when no Try-it input has a value.
2. Add a `.fallback-row.rule-winner` rule so a genuine fallback win paints the whole row, reusing existing tokens.
3. Add the blank / rule-match / fallback-match assertions to the ENH-3500 probe, rerun `CASE_ONLY='auth-populated-decision_table-.*'`, regenerate the golden.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add a node `vm`-sandbox regression test in `scripts/tests/js/policy_validator.test.mjs` (blank → no winner; fallback-only match → `#fallback-row`; re-blank → cleared) — this is the pytest-gated coverage; the ENH-3500 probe assertions remain on-demand
- Keep any new helper outside the `_BOOTSTRAP_SRC` / `_OPEN_HANDLER_SRC` slice markers in the template
- Regenerate `golden_policy_router_builder.html` after the template edit and review the diff
- Rerun `.loops/verify-enh-3506-theme.yaml` after adding the `.fallback-row.rule-winner` rule; add a `PAIRS` entry in `test_enh3506_policy_builder_theme_parity.py` only if the rule introduces a new text/background pairing

## Program Design

### Types

- None — DOM/CSS only; no new persisted shapes.

### Signatures

- `updateTryIt() -> void`
- `evaluateModel(model, scores) -> result`

### Call Path

`cmd_policy_builder` -> `render_policy_builder_html` (stamps the template) -> in-page `renderAll` -> `renderTryIt` -> `updateTryIt` -> `evaluateModel` -> `_highlightWinner`

## Impact

- **Priority**: P4 - cosmetic/misleading highlight, no data impact
- **Effort**: Small - one early return plus a CSS rule
- **Risk**: Low
- **Breaking Change**: No

## Steps to Reproduce

1. Open the offline builder in Decision Table mode with the seed example (dark theme makes it most visible).
2. Leave every Try-it input blank.
3. Observe: the "Otherwise →" row is outlined and half-filled green although nothing was tried.

## Acceptance Criteria

- [ ] Decision-table page with all Try-it inputs blank: neither `#fallback-row` nor any `.rule-card` has `.rule-winner` (probe: `auth-populated-decision_table-*`).
- [ ] Entering a value that matches no rule highlights `#fallback-row`; entering one that matches rule N highlights only that card; clearing all inputs removes the highlight (probe).
- [ ] `issue_lifecycle` Try-it behavior unchanged.
- [ ] No new CSS variables; theme-parity test passes; golden `golden_policy_router_builder.html` regenerated after reviewing the diff.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-19 | Priority: P4


## Session Log
- `/ll:wire-issue` - 2026-09-19T21:26:47 - `bdde24da-3994-4eee-b745-85fb52f99de6.jsonl`
- `/ll:refine-issue` - 2026-09-19T21:23:37 - `4a41a017-324d-4857-a14c-acc7242546eb.jsonl`
- `/ll:format-issue` - 2026-09-19T21:20:52 - `92521728-42bd-4ef9-abf0-e0733de02c8f.jsonl`
