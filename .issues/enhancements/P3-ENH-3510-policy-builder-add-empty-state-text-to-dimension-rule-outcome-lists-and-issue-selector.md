---
id: ENH-3510
type: ENH
title: 'Policy builder: add empty-state text to dimension, rule, outcome lists and
  issue selector'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T20:00:56Z'
relates_to:
- ENH-3500
blocked_by:
- ENH-3511
- BUG-3512
parent: EPIC-3493
epic: EPIC-3493
---

# ENH-3510: Policy builder: add empty-state text to dimension, rule, outcome lists and issue selector

## Summary

Found by ENH-3500 audit. Dimensions, rules and outcomes lists render nothing when empty (children=0, no text) in decision_table/lifecycle; the connected issue selector shows no note when the issue list is empty (conn-issue-note is blank). Only scenarios has 'No scenarios yet.'. Zero-dimension rubric/decision_table also reports 'No issues detected.' with export enabled. Repro: open offline builder, Open project with dimensions=[] (or Start blank in rubric); serve with ./issues returning {issues:[]}. Expected: a consistent empty-state hint per list. Evidence (run .loops/runs/enh-3500-audit-final/evidence): auth-empty-dimensions-*, auth-empty-rules-*, auth-empty-outcomes-*, conn-issues-empty-*.

## Current Behavior

The dimensions, rules and outcomes lists render nothing when empty (0 children, no text) in `decision_table`/`issue_lifecycle`. The connected issue selector leaves `#conn-issue-note` blank when the issue list is empty. Only the scenarios list shows an empty-state ('No scenarios yet.'). Zero-dimension `rubric`/`decision_table` models also report 'No issues detected.' with export enabled.

## Expected Behavior

Each of the dimensions, rules and outcomes lists, and the connected issue selector, shows a consistent empty-state hint (in the style of 'No scenarios yet.') when it has no entries. A zero-dimension model no longer reads 'No issues detected.': `renderMessages` adds a template-side `msg-warn` ("No dimensions yet — add at least one."; mode-neutral, since `decision_table` dimensions are rule fields, not scored), the same way it already adds the unreachable-outcome warning. It is a warning, not an error, so export gating (`validateBuilderModel`) is unchanged.

## Motivation

This enhancement would:
- Blank lists read as broken or still loading rather than empty; the scenarios list already shows the intended pattern.
- ENH-3500 audit evidence: `auth-empty-dimensions-*`, `auth-empty-rules-*`, `auth-empty-outcomes-*`, `conn-issues-empty-*`.

## Scope Boundaries

- **In scope**: empty-state text for `renderDimensions`, `renderRules`, `renderOutcomes`/`renderLifecycleOutcomes`, and the `#conn-issue-note` empty-issues case.
- **In scope (decided)**: a template-side zero-dimension `msg-warn` in `renderMessages` (all modes) so 'No issues detected.' is not shown for a model with no dimensions.
- **Out of scope**: redesigning the scenarios empty-state; changing `validateBuilderModel` rules or export gating (e.g. requiring at least one dimension); styling beyond reusing the existing `.hint` treatment.

## Integration Map

### Files to Modify
- `scripts/little_loops/templates/policy-router-builder.html.tmpl`

### Tests
- Template/probe tests for the policy builder (locate via `grep -rl policy-router-builder scripts/tests/`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- All render functions named in this issue exist in `policy-router-builder.html.tmpl` (none in `policy_builder_core.mjs`, which is DOM-free): `renderDimensions` (:682), `renderOutcomes` (:776), `renderLifecycleOutcomes` (:876), `renderRules` (:1029), `renderConnected` (:2217), `renderFallback` (:743). `renderAll` (:1841) also blanks `#outcome-list`/`#rule-list` directly in rubric mode (fieldsets hidden there), so an empty-state must not leak into hidden fieldsets.
- Current empty behavior: each renderer does `host.innerHTML = ""` then `forEach`; containers are `#dim-list` (:231), `#rule-list` (:247), `#outcome-list` (:300). No empty branch anywhere.
- Convention held for empty states: `#scenario-summary` is a single always-present `<p class="hint">` (:284) whose `textContent` is swapped between "No scenarios yet." / "Not yet run — click Run all." (:1630) — not a created-on-empty element. `.hint` (:165) is monospace 0.8rem opacity 0.8; `small.help` (:168) is the other helper-text class. Both coexist.
- `#conn-issue-note` (:341) is set only in `renderConnected` (:2242-2246): "Loading issues…" / error text / "selected issue no longer listed…" / `""`. The empty-list-with-status-`ready` case falls to `""` — that is the gap. The `<select id="conn-issue">` always has a leading "Select an issue…" option (:2229-2240). `renderConnected` returns early when `CONNECTED_CONTEXT` is null (:2226), so offline builds never reach it.
- "No issues detected." is produced only at :1320 in `renderMessages` (`if (!host.children.length) add("msg-ok", …)`). Export gating is independent: `updatePreview` (:1778) sets `#copy-btn`/`#download-btn` `.disabled = hasError` from `validateBuilderModel` (:1795-1798). Deciding what a zero-dimension model reads is an implementation call the issue defers to tests.
- Fallback select: with zero outcomes `renderFallback` leaves `state.fallback = ""` (:767) — an empty-outcomes hint interacts with the fallback row.

### Conventions in Force
- Golden byte-comparison: `scripts/tests/test_enh3035_artifact_template_kit.py:93-103` renders the template with pinned inputs against `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html`; any template edit changes it and the golden must be regenerated once after reviewing the diff (no regeneration script exists; sibling ENH-3506/3507 did this by hand).
- `scripts/tests/test_policy_builder_emit.py` string-greps the rendered HTML (`in html`, `html.count('id=…') == 1`); `"/*__" not in html` must keep holding. Node core tests (`scripts/tests/js/*.test.mjs`, run via `test_policy_builder_node_gate.py`) do not assert rendered DOM. `policy_validator.test.mjs:1514-1572` slices the `.tmpl` between literal markers (`let state = seedExample();` … `function buildModel() {`) and throws "template source moved" if they shift.
- No existing pytest/Node test asserts `No scenarios yet` or any `.hint` empty-state; the ENH-3500 Playwright probe (`.loops/probes/enh-3500-audit-probes.mjs`, driver `.loops/verify-enh-3500-audit.yaml`, `CASE_ONLY=<regex>` reruns a subset, e.g. `auth-empty-.*|conn-issues-empty`) is the only DOM-level check and is on-demand, never a pytest gate.

**Tests (research)**
- Template-level tests belong in `scripts/tests/test_policy_builder_emit.py` (string/structure asserts on rendered HTML). Rendered-DOM empty states can only be verified via the on-demand probe; the issue's "template tests for each empty state" is limited to static markup unless a probe case is added.
- Golden fixture must be regenerated: `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html`.

### Documentation
- None of `docs/guides/POLICY_ROUTER_GUIDE.md` / `docs/reference/CLI.md` describe empty states; no doc change needed. (Audience gate `test_docs_audience_gate.py` scans only `*.md`, not the template.)

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `.loops/probes/feat-3488-browser-probes.mjs` — `ruleCount` counts `#rule-list .rule-card` and waits on `#rule-list`; the empty-state hint must not use the `.rule-card` class or be a `#rule-list` child that changes that count [Agent 1 finding]
- `.loops/probes/enh-3500-audit-probes.mjs` — cases `auth-empty-dimensions-*`, `auth-empty-rules-*`, `auth-empty-outcomes-*`, `conn-issues-empty-*` are the verification path; add assertions there for the new hints [Agent 3 finding]

### Wiring: Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` — regenerate by hand after reviewing the diff (byte-compared in `test_enh3035_artifact_template_kit.py`) [Agent 3 finding]
- `scripts/tests/js/policy_validator.test.mjs` — `_newBug3502Sandbox` executes the template slices `let state = seedExample();`…`function buildModel() {` (incl. `commit()`) and the Open handler `$("open-project-input").onchange`…`$("undo-btn").onclick`; any new DOM call added inside those slices needs a stub in the sandbox's `elements`/`$` [Agent 3 finding]
- `scripts/tests/test_policy_builder_emit.py` — add static-markup asserts for the hint element/text; existing `live-status`/`aria-live` asserts (:317-318) unaffected [Agent 3 finding]

## Program Design

### Types

- None — DOM/markup only; no new persisted shapes.

### Signatures

- `renderDimensions() -> void`
- `renderRules() -> void`
- `renderOutcomes() -> void`
- `renderLifecycleOutcomes() -> void`
- `renderConnected(st) -> void`
- `renderMessages(model, diagnostics) -> void`

### Call Path

`cmd_policy_builder` -> `render_policy_builder_html` (stamps the template) -> in-page `renderAll` -> `renderDimensions` / `renderRules` / `renderOutcomes` -> new empty-state branch

## Design Decisions

> **Context refresh (2026-09-19)**: BUG-3512 is **done** (2f5bdb89a). `:NNNN` line references in this issue predate it — roughly +4 up to `updatePreview` (now :1782) and +75 in the connected code (`renderConnected` now :2292). Function-name anchors remain correct; resolve by name, not line.

- **Placement**: each hint is a static, always-present sibling `<p class="hint" hidden>` placed directly after its list container — `#dim-empty` after `#dim-list`, `#rule-empty` after `#rule-list`, `#outcome-empty` after `#outcome-list` — toggled (`hidden` + `textContent`) by the renderer. This mirrors the `#scenario-summary` convention (static element, swapped text), keeps the list containers' child counts untouched (`feat-3488-browser-probes.mjs` `ruleCount`), and cannot leak in rubric mode because `#rules-fieldset`/`#outcomes-fieldset` are hidden there. `renderAll`'s rubric branch must still set `#rule-empty`/`#outcome-empty` `hidden = true` alongside its `innerHTML = ""` clears.
- **`#dim-list` is visible in every mode**, so `#dim-empty` shows in rubric mode too (intended). In `issue_lifecycle` the built-in dimensions make an empty list unreachable; `renderLifecycleOutcomes` likewise always renders the fixed verb set, so `#outcome-empty` only ever shows in `decision_table`.
- **Text**: "No dimensions yet.", "No rules yet — everything goes to the fallback." (plain "No rules yet." when `state.fallback` is `""`, i.e. outcomes are also empty — there is no fallback to go to), "No outcomes yet — add an outcome before adding rules.", and `#conn-issue-note` = "No issues found." when `st.issues.status === "ready"` and `st.issues.list` is empty (and no stale selection note applies).
- **Zero-dimension message**: template-side `msg-warn` in `renderMessages` (see Expected Behavior); `validateBuilderModel` untouched.

## Acceptance Criteria

- [ ] Rendered HTML contains exactly one each of `id="dim-empty"`, `id="rule-empty"`, `id="outcome-empty"`, each a `<p class="hint"` with `hidden` (pytest: `test_policy_builder_emit.py`, `html.count(...) == 1`).
- [ ] `decision_table` with `dimensions=[]` / `rules=[]` / `outcomes=[]`: the matching hint is visible with the text above; with ≥1 entry it is hidden (probe: `auth-empty-dimensions-*`, `auth-empty-rules-*`, `auth-empty-outcomes-*`).
- [ ] `rules=[]` **and** `outcomes=[]`: `#rule-empty` reads "No rules yet." without the fallback clause (probe).
- [ ] With no outcomes, `#outcome-empty` explains that an outcome must be added before adding rules; export gating and Add rule behavior are unchanged.
- [ ] Browser checks cover empty → populated → empty transitions through supported add/delete operations, undo/redo, Open, and mode switches. Where deletion is guarded (e.g. fallback outcome), use Open/undo to reach the empty state rather than changing the guard. Assert computed visibility and current text, with no stale hints after a mode switch; static markup and goldens alone are insufficient.
- [ ] Rubric mode: `#rule-empty`/`#outcome-empty` are never visible; `#dim-empty` is visible when there are no dimensions (probe).
- [ ] Served page with `./issues` → `{issues:[]}`: `#conn-issue-note` reads "No issues found."; loading/error/no-longer-listed texts unchanged (probe: `conn-issues-empty-*`).
- [ ] A zero-dimension model shows the `msg-warn` and not "No issues detected."; Copy/Download enablement is unchanged (probe).
- [ ] `#rule-list .rule-card` count unchanged for non-empty lists (`.loops/verify-feat-3488-browser-persistence.yaml` stays green).
- [ ] Golden regenerated after reviewing the diff; `python -m pytest scripts/tests/` exits 0.

## Implementation Steps

1. Add the three static `<p class="hint" hidden>` siblings to the markup.
2. Toggle each in `renderDimensions` / `renderRules` / `renderOutcomes` (and hide `#rule-empty`/`#outcome-empty` in `renderAll`'s rubric branch); add the empty-issues case to the `#conn-issue-note` chain in `renderConnected`.
3. Add the zero-dimension `msg-warn` to `renderMessages`, before the `msg-ok` fallthrough.
4. Add static-markup asserts to `test_policy_builder_emit.py`; add rendered-DOM visibility/text assertions and transition cases to the ENH-3500 probe, including the outcome prerequisite guidance, and rerun them.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `.loops/probes/enh-3500-audit-probes.mjs` — assert empty-state text for the four cases and rerun via `CASE_ONLY='auth-empty-.*|conn-issues-empty'`
- Sequenced via `blocked_by`: BUG-3512 → ENH-3513 → ENH-3511 → **ENH-3510** → ENH-3514 → BUG-3516 (all edit this template and regenerate the same byte-compared golden — never run in parallel)
- Regenerate `golden_policy_router_builder.html` after reviewing the diff

## Impact

- **Priority**: P3 - polish; no data or correctness impact
- **Effort**: Small - four render branches plus tests
- **Risk**: Low - additive text only
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-19 | Priority: P3


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-19T21:30:34 - `6b9c88d3-074c-4681-b7c9-240fc332f147.jsonl`
- `/ll:wire-issue` - 2026-09-19T21:05:52 - `39128071-49a7-41ee-a288-c86d0c6aa6ea.jsonl`
- `/ll:refine-issue` - 2026-09-19T20:57:35 - `dff55670-569e-48fc-a235-30c0ce66babb.jsonl`
- `/ll:format-issue` - 2026-09-19T20:40:26 - `62ea2c42-153a-4077-bc55-dc91a943784a.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Related issue ENH-3511 adds per-row `oc-del-reason-${oi}` elements in `renderOutcomes` and `aria-describedby="conn-unavailable"` on `#conn-issue`. Keep `#outcome-empty` outside `#outcome-list` and keep `#conn-issue-note` (status text) separate from the `#conn-unavailable` describedby target. BUG-3512 owns announcer semantics for `#conn-*`. **Settled (BUG-3512 landed)**: `#conn-issue-note` has no `role`/`aria-live` and `_announceConnected` never writes it, so "No issues found." is silent like its sibling loading/error texts — intended; do not make it live here.
