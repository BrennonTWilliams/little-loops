---
id: BUG-3516
type: BUG
title: 'Policy builder: fallback row highlighted as Try-it winner before any sample
  value is entered'
priority: P4
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T21:16:29Z'
completed_at: '2026-09-20T04:08:58Z'
relates_to:
- ENH-3500
- ENH-3514
parent: EPIC-3493
epic: EPIC-3493
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

In `updateTryIt`, when `scores` is empty call `_highlightWinner({ ruleIndex: -1, target: null, isFallback: false })` and return, mirroring the blank-input branch of `updateFrontmatterTryIt`. For the genuine-fallback-win case, add exactly these two rules after `.fallback-row select`:

```css
.fallback-row.rule-winner { opacity: 1; padding: 0.5rem; border-radius: 6px; }
.fallback-row.rule-winner select { background: transparent; }
```

`opacity: 1` is required: `.fallback-row` sets `opacity: 0.85`, so today a winning fallback row renders its highlight and text at 85% — outside what the `PAIRS` contrast check (computed at full opacity) covers. With the select transparent, the only text/background pairing on the row is `--color-text-primary` on `--color-status-success-bg`, which `PAIRS` already enforces. **Decided: no new `PAIRS` entry, no new CSS variables.**

## Integration Map

### Files to Modify
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — `updateTryIt`, `.rule-winner` / `.fallback-row` CSS

### Tests
- `.loops/probes/enh-3500-audit-probes.mjs` — optional visual check only (rerun `CASE_ONLY='auth-populated-decision_table-.*'` and eyeball the screenshot). It is a `COLLECT` data audit with no assertions; do not add any — the ACs are verified by the node `vm` test below
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` — regenerate (byte-compared in `test_enh3035_artifact_template_kit.py`)
- `scripts/tests/js/policy_validator.test.mjs` — `updateTryIt` sits outside the `_newBug3502Sandbox` slices; confirm the literal slice markers do not move

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/js/policy_validator.test.mjs` — **new test**, `BUG-3516: updateTryIt with all-blank inputs clears winner`, next to the `BUG-3502:` tests; reuse `_extractBetween(_templateSrc, "function _highlightWinner(result) {", "// FEAT-3474: the issue_lifecycle Try-it panel", …)` and a `_newBug3502Sandbox`-style `vm` context. Stub only the DOM and page state (`state`, `buildModel`, `updateFrontmatterTryIt`, `document.querySelectorAll` for `#tryit-inputs [data-dim]` / `.rule-card`, `document.querySelector` for `.rule-card[data-rule-index=…]`, and `$("fallback-row").classList`); inject the **real** `evaluateModel` imported from `policy_builder_core.mjs` — a stubbed evaluator would make the fallback assertion test the stub. Cases: all blank → no `rule-winner` anywhere; value matching rule N → only that card; value matching no rule → `#fallback-row`; **partially filled (one dim set, others blank) and no rule matches → `#fallback-row`** (pins the "at least one value" contract); re-blank → cleared. Runs under pytest via `test_policy_builder_node_gate.py` (skips without node), so it covers the AC without a browser probe [Agent 3 finding]
- `scripts/tests/test_policy_builder_emit.py` — optional text-level assertion beside `test_fallback_footer_is_structured_not_free_text` that the stamped CSS contains a `.fallback-row.rule-winner` rule; `id="fallback-row"` markup must stay `<input`-free [Agent 3 finding]
- `scripts/tests/test_enh3035_artifact_template_kit.py::test_policy_builder_renders_byte_identically_to_golden_fixture` — the only test that breaks (byte-compare); golden lines affected: `.rule-winner` CSS (~L324), `.fallback-row` (~L339-340), `_highlightWinner`/`updateTryIt` (~L6022-6033) [Agent 2/3 finding]
- `.loops/verify-enh-3506-theme.yaml` + `.loops/probes/enh-3506-theme-probes.mjs` — on-demand theme/contrast check; rerun after adding the `.fallback-row.rule-winner` rule (it measures a synthetic `.rule-card.rule-winner`, not `#fallback-row`) [Agent 1/2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/POLICY_ROUTER_GUIDE.md` (~L292) — says the Try it panel "highlights the rule that would win"; still accurate, but verify it does not imply a winner shows before input. No edit expected [Agent 2 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/artifact/policy_builder.py` — `render_policy_builder_html` stamps the template verbatim (design-token CSS + core JS) into `policy-router-builder.html`; the only producer, so no packaged/mirror copy of the template needs a parallel edit [Agent 1/2 finding]
- `policy-router-builder.html.tmpl` `updatePreview` (~L1967) and `renderTryIt` (~L1365) — both reach `updateTryIt`; `renderTryIt` rebuilds inputs blank, so the early return also fires after every render/mode switch; with zero dimensions "all blank" is vacuously true (highlight cleared, acceptable) [Agent 2 finding]
- `#fm-tryit-hint` / `#live-status` — not written by `updateTryIt`, so the early return leaves no stale result text [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- `updateTryIt` (`policy-router-builder.html.tmpl` ~1385-1401) filters blank inputs per element (`if (el.value === "") return;`, ~1396) but has no "all blank" check, so `scores` is `{}` and `evaluateModel(model, {})` still runs. `evaluateModel` (`policy_builder_core.mjs` ~452-469) compiles the authored rules plus a derived catch-all; `_traceCompiledRules` (~504) lets that catch-all win with `ruleIndex: -1, isFallback: true`.
- `_highlightWinner` (~1373-1383) is the only place `rule-winner` is added or removed. It always clears every `.rule-card` and `#fallback-row` first, then returns early when `result.target == null`. The existing no-winner shape `{ ruleIndex: -1, target: null, isFallback: false }` (used at ~1391, ~1426, ~1434) is therefore a complete clear.
- Callers of `updateTryIt`: `renderTryIt` (~1332-1365, calling `updateTryIt` at ~1365) and `updatePreview` (~1967). `renderAll` calls `renderTryIt` then `updatePreview`, so `updateTryIt` runs twice per full render — the blank-state clear must be idempotent. `policy_builder_core.mjs` has no callers of `updateTryIt`/`_highlightWinner`.
- Related disagreement: `updateFrontmatterTryIt` clears only on blank or unparseable text; a non-blank frontmatter that encodes to zero scores still reaches `evaluateModel` and can highlight the fallback. Out of scope here, but the "no input → no winner" contract is per-path, not shared.
- CSS: `.rule-winner` (~131-134) sets `outline` + `background: var(--color-status-success-bg, #d4edda)` and no `color`. `.fallback-row` (~146-147) sets only `font-style`/`opacity`/select `max-width`; there is no `.fallback-row.rule-winner` rule and no `#f-fallback` rule. The select's opaque `background: var(--color-surface-primary)` comes from the generic `input, select, textarea, button` rule (~94-101) — that is the "painted only behind the label" cause. Markup is `<div class="row fallback-row" id="fallback-row"><span>Otherwise →</span><select id="f-fallback">` (~255-258).

### Constraints

- Theme parity (`test_enh3506_policy_builder_theme_parity.py`): every `var(--x)` in the template CSS must be declared in all stamped blocks (profiles `default`, `editorial-mono`, `warm-paper`; light and dark; packaged and mirror), or `test_refs_declared_with_resolved_values` fails (~line 149). `PAIRS` (~38-48) enforces 4.5:1 contrast for `--color-text-primary` on `--color-status-success-bg` (the `.rule-winner` inherited-text pair). Any new background/text combination on the winner row is not covered by `PAIRS` unless added.
- `test_policy_builder_emit.py::test_fallback_footer_is_structured_not_free_text` asserts `id="fallback-row"`, `<select id="f-fallback"`, and that the `<div class="row fallback-row"…>` element contains no `<input` and no "del" — the fallback-row markup must keep that shape.
- Golden `golden_policy_router_builder.html` is byte-compared in `test_enh3035_artifact_template_kit.py::test_policy_builder_renders_byte_identically_to_golden_fixture` (inputs pinned by `_pin_golden_render_inputs`: `default` profile, dark, empty skill catalog, version `0.0.0-golden`). Any template edit forces regeneration. No regeneration script or flag was found; other issues disagree on the method (ENH-3513: "by hand after reviewing the diff"; FEAT-3488/3503: "through the existing generator") — **regeneration recipe (decided):** render via `cmd_policy_builder` under the same pins as `_pin_golden_render_inputs` and copy the output over the fixture:
  1. temp project dir with `.ll/ll-config.json` = `{"design_tokens": {"enabled": true, "source": "profile", "active": "default", "active_theme": "dark"}}`; `chdir` into it
  2. patch `little_loops.skill_expander.resolve_plugin_content_root` to return `None` and `little_loops.__version__` to `"0.0.0-golden"`
  3. `cmd_policy_builder(argparse.Namespace(output=<out>), Logger(use_color=False))`, then copy `<out>/policy-router-builder.html` over `golden_policy_router_builder.html`
  4. `git diff` the fixture — expect only the two new CSS rules and the `updateTryIt` early return; anything else means an input was not pinned.
- `policy_validator.test.mjs` has no references to `updateTryIt`, `_highlightWinner`, `rule-winner`, `fallback-row` or `f-fallback`. Its slice markers (`let state = seedExample();` … `function buildModel() {`; `$("open-project-input").onchange = …` … `$("undo-btn").onclick = …`) bracket regions that do not contain `updateTryIt`, so the edit is safe as long as those literal markers are untouched.
- Probe correction: `.loops/probes/enh-3500-audit-probes.mjs` is a data-collection audit (`COLLECT`, ~line 69) with no pass/fail assertions and no winner-state references; the blank/match/fallback checks are a new addition, not an extension of existing assertions. `.loops/probes/enh-3506-theme-probes.mjs` (~72, ~96) measures contrast on a synthetic `.rule-card.rule-winner` element and never drives `updateTryIt`. No existing test or probe exercises the winner class after a Try-it input event.

## Implementation Steps

1. (TDD red) Add the `BUG-3516:` node `vm` test in `scripts/tests/js/policy_validator.test.mjs` (cases under Tests above); confirm the all-blank case fails.
2. In `updateTryIt`, clear the highlight and return when no Try-it input has a value.
3. Add the two `.fallback-row.rule-winner` rules from Proposed Solution verbatim.
4. Regenerate the golden via the recipe under Constraints and review the diff.
5. Optional: rerun the ENH-3500 probe (`CASE_ONLY='auth-populated-decision_table-.*'`) and `.loops/verify-enh-3506-theme.yaml` as a visual check — not an AC verifier.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add a node `vm`-sandbox regression test in `scripts/tests/js/policy_validator.test.mjs` (blank → no winner; fallback-only match → `#fallback-row`; re-blank → cleared) — this is the pytest-gated coverage and the verifier for AC 1–2; the ENH-3500 probe is an optional visual check with no assertions
- Keep any new helper outside the `_BOOTSTRAP_SRC` / `_OPEN_HANDLER_SRC` slice markers in the template
- Regenerate `golden_policy_router_builder.html` after the template edit and review the diff
- Optionally rerun `.loops/verify-enh-3506-theme.yaml` after adding the `.fallback-row.rule-winner` rules; no `PAIRS` entry is needed (the row's only pairing, `--color-text-primary` on `--color-status-success-bg`, is already enforced)

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

- [ ] Decision-table page with all Try-it inputs blank: neither `#fallback-row` nor any `.rule-card` has `.rule-winner` (verified by the `BUG-3516:` test in `policy_validator.test.mjs`).
- [ ] Entering a value that matches no rule highlights `#fallback-row`; entering one that matches rule N highlights only that card; a partially filled input set that matches no rule highlights `#fallback-row`; clearing all inputs removes the highlight (same node test, using the real `evaluateModel`).
- [ ] `issue_lifecycle` Try-it behavior unchanged.
- [ ] A winning fallback row renders at `opacity: 1` with a transparent select (stamped CSS contains both `.fallback-row.rule-winner` rules).
- [ ] No new CSS variables and no new `PAIRS` entry; theme-parity test passes; golden `golden_policy_router_builder.html` regenerated after reviewing the diff.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-19 | Priority: P4


## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (line-number drift corrected in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- Verified against `policy-router-builder.html.tmpl`: `updateTryIt` has no all-blank guard; `_highlightWinner` clears then returns on `target == null`; `updateFrontmatterTryIt` clears on blank; `.rule-winner` / `.fallback-row` CSS and `#fallback-row` markup match the description. The bug and proposed early-return fix are sound.
- Corrected stale `~` line anchors (template grew ~150 lines): `updateTryIt` ~1385-1401, `_highlightWinner` ~1373-1383, `updatePreview` call ~1967, fallback-row markup ~255-258.
- `ll-verify-evidence`: clean (0 findings). Decisions log: no active required rules.
- `blocked_by: ENH-3514` — ENH-3514 is now Completed, so the dependency is satisfied; the confidence-check "Dependencies Hard Override" gap no longer applies (stale `blocked_by` entry removed afterward at the user's request; re-run `/ll:confidence-check` to clear the gap).
- Graph: provider=`codegraph` freshness=`stale`; used only as a lead, anchors confirmed by direct reads.

## Resolution

**Fixed** — `updateTryIt` now clears the highlight and returns when no Try-it input has a value (matching `updateFrontmatterTryIt`); added `.fallback-row.rule-winner` (`opacity: 1`, padding, radius) and `.fallback-row.rule-winner select` (transparent) rules. Added the `BUG-3516:` node `vm` test (real `evaluateModel`); regenerated the golden (diff = the 6 new lines only). Full suite: 25101 passed.

## Session Log
- `/ll:manage-issue` - 2026-09-20T04:08:58 - `ff80c8dc-c556-475d-b51f-bb1b8e7c5cf1.jsonl`
- `/ll:ready-issue` - 2026-09-20T04:02:32 - `6ae652d0-92f7-4822-bb9f-9d845a718a7e.jsonl`
- `/ll:confidence-check` - 2026-09-20T03:38:32 - `1fb0a05c-b6e2-4738-9a19-fe759b33af09.jsonl`
- `/ll:verify-issues` - 2026-09-20T03:27:54 - `60d8cbff-e55d-413c-8fb6-99a0fd5959d4.jsonl`
- `/ll:verify-issues` - 2026-09-20T03:27:31 - `60d8cbff-e55d-413c-8fb6-99a0fd5959d4.jsonl`
- `/ll:confidence-check` - 2026-09-20T00:50:23 - `b1e66617-7ca3-4c73-8eef-611558ec10fe.jsonl`
- `/ll:verify-issues` - 2026-09-20T00:42:34 - `87477791-8eac-4eaa-a6b5-62a48362f015.jsonl`
- `/ll:wire-issue` - 2026-09-19T21:26:47 - `bdde24da-3994-4eee-b745-85fb52f99de6.jsonl`
- `/ll:refine-issue` - 2026-09-19T21:23:37 - `4a41a017-324d-4857-a14c-acc7242546eb.jsonl`
- `/ll:format-issue` - 2026-09-19T21:20:52 - `92521728-42bd-4ef9-abf0-e0733de02c8f.jsonl`
