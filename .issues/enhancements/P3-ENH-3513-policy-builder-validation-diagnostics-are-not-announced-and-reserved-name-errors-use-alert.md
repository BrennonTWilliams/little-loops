---
id: ENH-3513
type: ENH
title: 'Policy builder: validation diagnostics are not announced and reserved-name
  errors use alert()'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T20:00:57Z'
relates_to:
- ENH-3500
- BUG-3512
blocked_by:
- BUG-3512
---

# ENH-3513: Policy builder: validation diagnostics are not announced and reserved-name errors use alert()

## Summary

Found by ENH-3500 audit. #messages (Result diagnostics) is not a live region; after an edit or Open project produces msg-error diagnostics, copy/download are disabled but only #live-status ('Project opened.') is announced. #import-diagnostics is polite even for errors. add-outcome/add-dim reserved or duplicate names use blocking alert() instead of inline messages. Repro: open a project with a bogus dimension type; try adding outcome 'done' in decision_table. Expected: errors announced (assertive or status) and inline. Evidence: auth-invalid-model-*, live-import-error-offline.

## Current Behavior

`#messages` (Result diagnostics) is not a live region: after an edit or Open project yields `msg-error` diagnostics, Copy/Download disable but only `#live-status` ('Project opened.') is announced. `#import-diagnostics` is `aria-live="polite"` even for errors. The `#add-outcome`/`#add-dim` handlers report reserved or duplicate names with blocking `alert()`.

## Expected Behavior

Validation errors are announced through the existing polite `role="status"` region and shown inline. Reserved/duplicate-name errors appear as inline, announced messages instead of `alert()`. No assertive region is introduced: `role="status"` satisfies WCAG 4.1.3, and none of these errors is time-critical.

## Motivation

This enhancement would:
- Screen-reader users get no notice that the model became invalid and export was disabled.
- Blocking `alert()` interrupts flow and is inconsistent with the inline diagnostics elsewhere.
- ENH-3500 audit evidence: `auth-invalid-model-*`, `live-import-error-offline`.

## Scope Boundaries

- **In scope**: announcing `#messages` error-count changes via `showLiveStatus`; replacing `alert()` in the `add-dim`/`add-outcome` handlers with inline messages.
- **Decided out**: making `#messages` itself a live region (it is rebuilt on every `updatePreview()`, so it would re-announce the whole list per edit); severity-aware `#import-diagnostics` (toggling `role`/`aria-live` on an existing region at runtime is unreliably honored by screen readers — it stays `role="status" aria-live="polite"`, unchanged).
- **Out of scope**: rewording diagnostic text; explaining disabled controls (ENH-3511); unifying message class names (ENH-3514).

## Integration Map

### Files to Modify
- `scripts/little_loops/templates/policy-router-builder.html.tmpl`

### Tests
- Template/probe tests for the policy builder (locate via `grep -rl policy-router-builder scripts/tests/`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- Named functions exist in `policy-router-builder.html.tmpl`: `renderMessages(model, diagnostics)` (:1296, called only from `updatePreview` :1800) and `showLiveStatus(text)` (:430, plain `textContent` overwrite, 12 callers, no clear/queue).
- Live-region inventory: exactly two — `#import-diagnostics` (:283, `role="status" aria-live="polite"`, hidden outside lifecycle mode by `applyModeVisibility` :1871, written directly at :1711-1746 without `showLiveStatus`) and `#live-status` (:323, same attrs). `#messages` (:315, `<ul class="messages">`), `#transition-graph`, `#conn-notices` (:350), `#conn-status` (:351) have no role/aria. No `role="alert"` or `aria-live="assertive"` exists anywhere.
- `renderMessages` rebuilds `#messages` via `innerHTML = ""` on every `updatePreview()` (every edit), so making `#messages` a live region announces the entire list on each keystroke-level commit unless the announcement is restricted to changes (e.g. error set becoming non-empty). This is the double-announcement / chatter risk; it also interacts with `#live-status` texts written on Open/Save ("Project opened.").
- Severity mapping is `d.severity === "error" ? "msg-error" : "msg-warn"` (:1302); unreachable-outcome warnings (:1309, decision_table only), unknown-skill errors (:1317, template-side only — they do NOT disable Copy/Download since gating uses `validateBuilderModel` diagnostics only, :1795-1798), and `msg-ok` "No issues detected." (:1320) are also written there.
- `alert(` inventory (exactly four, all in click handlers, each followed by `return` before `renderAll()`/`commit()`): #add-dim :1997 (name contains ":" or "|"), :2002 (duplicate field); #add-outcome :2017 (reserved name via `isReservedOutcomeToken`), :2021 (duplicate). add-outcome is skipped early in `issue_lifecycle` (:2011). The issue text says "four `alert()` sites" — confirmed. Any inline replacement needs a message element near `#add-dim`/`#add-outcome`, cleared on the next successful add or edit.
- BUG-3512 (open, P2) covers `#conn-status`/`#conn-notices`/`#conn-review-info` live regions and connected-panel focus, and edits `renderConnected` too; ENH-3513 scope is `#messages`/`#import-diagnostics`/`alert()` only. `renderConnected` regions must stay out of this issue.

### Conventions in Force
- `#import-diagnostics` is `<p>` with `textContent`; `#messages` uses `<li class=msg-*>`; polite regions are assigned by static markup attributes, not by JS. `test_policy_builder_emit.py:317-318` asserts `'id="live-status"' in html` and `'aria-live="polite"' in html` — that assertion must keep passing (it is satisfied by either region).
- No test currently asserts `alert(` absence; a string-grep test over the add-dim/add-outcome handler region is feasible via the template-slicing approach in `policy_validator.test.mjs:1514-1572` (literal-marker slice; throws "template source moved" if markers shift), otherwise the whole-file `"alert(" not in html` check must account for any legitimate remaining `alert(` (none found).
- ENH-3500 probe installs MutationObservers on `live-status`, `import-diagnostics`, `conn-*` (`.loops/probes/enh-3500-audit-probes.mjs:235-237`); evidence cases `auth-invalid-model-*`, `live-import-error-offline` rerun via `CASE_ONLY`.

**Tests (research)**
- `scripts/tests/test_policy_builder_emit.py`; golden `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` must be regenerated; probe cases above.

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `.loops/probes/feat-3488-browser-probes.mjs` — `liveStatus` reads `#live-status` and case `storage-disabled-degrades` expects exactly one live-region warning; making `#messages` live or changing `showLiveStatus` must keep that case green [Agent 1 finding]
- BUG-3512 owns `#conn-status`/`#conn-notices`/`#conn-review-info` — keep `renderConnected` out of this change [Agent 2 finding]
- `.loops/probes/enh-3500-audit-probes.mjs` (:235-237 MutationObservers on `live-status`/`import-diagnostics`) — cases `auth-invalid-model-*`, `live-import-error-offline` verify announcements [Agent 3 finding]

### Wiring: Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` — regenerate by hand after reviewing the diff (byte-compared in `test_enh3035_artifact_template_kit.py`) [Agent 3 finding]
- `scripts/tests/js/policy_validator.test.mjs` — `_newBug3502Sandbox` executes the template slices `let state = seedExample();`…`function buildModel() {` (incl. `commit()`) and the Open handler `$("open-project-input").onchange`…`$("undo-btn").onclick`; any new DOM call added inside those slices needs a stub in the sandbox's `elements`/`$` [Agent 3 finding]; the Open handler slice writes `#import-diagnostics`, so severity-aware role changes there run in the sandbox
- `scripts/tests/test_policy_builder_emit.py:317-318` — `'id="live-status"'`/`'aria-live="polite"'` asserts must keep passing; add role/`aria-live` asserts for `#messages`/`#import-diagnostics` and a check that the four `alert(` sites are gone [Agent 3 finding]

## Program Design

### Types

- None — DOM/markup only; no new persisted shapes.

### Signatures

- `renderMessages(model, diagnostics) -> void`
- `showLiveStatus(text) -> void`

### Call Path

`cmd_policy_builder` -> `render_policy_builder_html` (stamps the template) -> in-page `renderMessages`; `add-dim`/`add-outcome` click handlers -> inline message replacing `alert()`

## Design Decisions

- **Diagnostics announcement**: `updatePreview` tracks the previous error count (module-level `let lastErrorCount = 0`). When the count of `msg-error` items rendered by `renderMessages` (validator errors **plus** the template-side unknown-skill errors) changes, it calls `showLiveStatus`: `"N error(s) — Copy and Download are disabled."` when validator errors exist, `"N error(s)."` when only non-gating unknown-skill errors exist, `"No errors."` when it returns to 0 from non-zero. No announcement when the count is unchanged — this is what prevents per-keystroke chatter.
- **Composition with existing `#live-status` writers**: `showLiveStatus` is a plain `textContent` overwrite and the Open/Save handlers call it *after* `renderAll()`, which would clobber the error announcement ("Project opened." wins). Those callers must compose instead: when `lastErrorCount > 0` after their render, announce e.g. `"Project opened. 2 errors — Copy and Download are disabled."` in a single `showLiveStatus` call. Implement as an optional suffix helper rather than a queue.
- **Inline add errors**: two static elements, `<small class="help msg-error" id="dim-add-error" hidden>` after the `#add-dim` row and `<small … id="outcome-add-error" hidden>` after `#outcome-add-row`. Each of the four `alert(` sites sets `textContent`, unhides, sets `aria-invalid="true"` + `aria-describedby` on the input, and calls `showLiveStatus(sameText)` (the announcement channel — the inline elements themselves are **not** live, so ENH-3511's describedby-target rule holds). Cleared (hidden, attributes removed) on the input's next `input` event and on a successful add. `#outcome-add-error` sits inside/adjacent to `#outcome-add-row` so it is hidden with it in `issue_lifecycle`.
- `storage-disabled-degrades` (`feat-3488-browser-probes.mjs`) expects exactly one live-region warning: the error-count announcement must not fire on a clean initial load (count 0 → 0).

## Acceptance Criteria

- [ ] `"alert(" not in html` for the rendered template (pytest: `test_policy_builder_emit.py`).
- [ ] Rendered HTML contains exactly one each of `id="dim-add-error"` / `id="outcome-add-error"`, both `hidden`, neither with `role=`/`aria-live`; `#messages` has no `aria-live`; `#import-diagnostics` markup unchanged; existing `:317-318` asserts pass (pytest).
- [ ] Adding outcome `done` in `decision_table`, a duplicate outcome, a dim name containing `:`/`|`, and a duplicate dim each show the inline message, set `aria-invalid` on the input, write the same text to `#live-status`, raise no dialog, and clear on the next input event (probe — new cases).
- [ ] Opening a project with a bogus dimension type announces one `#live-status` text containing both "Project opened." and the error count (probe: `auth-invalid-model-*`, `live-import-error-offline`).
- [ ] Editing a field while the error count is unchanged produces no new `#live-status` mutation; fixing the last error announces "No errors." (probe MutationObserver).
- [ ] `.loops/verify-feat-3488-browser-persistence.yaml` `storage-disabled-degrades` stays green; `_newBug3502Sandbox` stubs cover new DOM calls in the sliced Open handler / `commit()` regions.
- [ ] Golden regenerated; `python -m pytest scripts/tests/` exits 0.

## Implementation Steps

1. Add `lastErrorCount` tracking + announcement to `updatePreview`/`renderMessages`; add the suffix-composition path for the Open/Save `showLiveStatus` callers.
2. Add the two inline error elements; replace the four `alert(` sites; wire clear-on-input and clear-on-success.
3. Static asserts in `test_policy_builder_emit.py`; sandbox stubs in `policy_validator.test.mjs`; new probe cases.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Announcement mechanism is **decided** — see Design Decisions (`#messages` stays non-live; count-change announcements via `showLiveStatus`)
- Sequenced via `blocked_by`: BUG-3512 → **ENH-3513** → ENH-3511 → ENH-3510 → ENH-3514 → BUG-3516 (shared template + byte-compared golden — never run in parallel)
- Re-run `.loops/verify-feat-3488-browser-persistence.yaml` (`storage-disabled-degrades`) and the ENH-3500 cases `auth-invalid-model-*`, `live-import-error-offline`
- Regenerate the golden after reviewing the diff

## Impact

- **Priority**: P3 - accessibility and UX consistency
- **Effort**: Small-Medium - count-change announcement with Open/Save composition, plus four `alert()` sites
- **Risk**: Low - watch for double announcement with `#live-status`
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-19 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-09-19T21:05:53 - `39128071-49a7-41ee-a288-c86d0c6aa6ea.jsonl`
- `/ll:refine-issue` - 2026-09-19T20:57:46 - `7ba3809c-e334-468e-81b6-cf0bbfd0f90c.jsonl`
- `/ll:format-issue` - 2026-09-19T20:40:37 - `62ea2c42-153a-4077-bc55-dc91a943784a.jsonl`
