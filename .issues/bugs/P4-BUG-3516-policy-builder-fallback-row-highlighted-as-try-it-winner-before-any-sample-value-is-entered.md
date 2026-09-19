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

## Implementation Steps

1. In `updateTryIt`, clear the highlight and return when no Try-it input has a value.
2. Add a `.fallback-row.rule-winner` rule so a genuine fallback win paints the whole row, reusing existing tokens.
3. Add the blank / rule-match / fallback-match assertions to the ENH-3500 probe, rerun `CASE_ONLY='auth-populated-decision_table-.*'`, regenerate the golden.

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
