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
parent: EPIC-3493
epic: EPIC-3493
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
- BUG-3512 (done) covers `#conn-status`/`#conn-notices`/`#conn-review-info` live regions and connected-panel focus, and edits `renderConnected` too; ENH-3513 scope is `#messages`/`#import-diagnostics`/`alert()` only. `renderConnected` regions must stay out of this issue.

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

> **Context refresh (2026-09-19)**: BUG-3512 is **done** (2f5bdb89a). `:NNNN` line references in this issue predate it — roughly +4 up to `updatePreview` (now :1782) and +75 in the connected code (`renderConnected` now :2292). Function-name anchors remain correct; resolve by name, not line.

- **Diagnostics announcement**: `updatePreview` tracks the previous announcement key — the pair `(errorCount, hasValidatorError)` (module-level `let lastErrorKey = "0|false"`), not the count alone: going from one validator error to one unknown-skill error keeps the count at 1 but re-enables export, and must announce. When the key built from the `msg-error` items rendered by `renderMessages` (validator errors **plus** the template-side unknown-skill errors) changes, it calls `showLiveStatus`: `` `${n} error(s). ${EXPORT_DISABLED_REASON}` `` when validator errors exist, `"N error(s)."` when only non-gating unknown-skill errors exist, `"No errors."` when it returns to 0 from non-zero. No announcement for ordinary edits when the key is unchanged — this prevents per-keystroke chatter; successful Open is the explicit exception below.
- **Composition with existing `#live-status` writers**: compose one DOM write per completed authoring operation, retaining every distinct status/warning from that operation plus its validation summary. Do not consume a pending diagnostic suffix on the first status writer: Open calls persistence between rendering and its final status, and a storage warning there must not consume the summary or be overwritten. Use an operation-scoped accumulator/flush around multi-writer paths such as Open; ordinary edits may flush their changed-key summary directly. Scope pending state to that operation and clear it after the flush so later unrelated actions do not repeat it. Audit existing callers and test the emitted mutations, not just the final text. Connected announcers remain unchanged.
- **Open is an explicit summary boundary**: every successful Open includes the current error count and export availability with its completion text, even when the previous project had the same announcement key. A clean Open includes a no-errors summary. Ordinary field edits still deduplicate on `(errorCount, hasValidatorError)`; this exception must not introduce clean-load chatter.
- **Shared export-disabled string**: this issue lands before ENH-3511 and therefore defines the one constant both use — `EXPORT_DISABLED_REASON = "Copy and Download are disabled until the errors above are fixed."`. The announcement is `` `${n} error(s). ${EXPORT_DISABLED_REASON}` ``; ENH-3511 writes the same constant into `#validate-hint`.
- **Inline add errors**: two static elements, `<small class="help msg-error" id="dim-add-error" hidden>` immediately after the `#add-dim` row and `<small class="help msg-error" id="outcome-add-error" hidden>` immediately after `#outcome-add-row`, inside the outcomes fieldset. Both are siblings of their respective rows. Add an explicit `small.help[hidden] { display: none; }` rule: existing `small.help { display: block; }` overrides native hidden styling. Each of the four `alert(` sites sets text, unhides, sets `aria-invalid="true"` and `aria-describedby` on the input, and sends the same text through `showLiveStatus`; the inline elements themselves are not live. On the next input event or successful add, clear text, hide the element, and remove the error-related input attributes. Clear both add-error states on successful Open, Start blank, and mode switching. `applyModeVisibility` must explicitly hide/clear the outcome error when entering `issue_lifecycle`; a sibling does not inherit the row's hidden state.
- `storage-disabled-degrades` (`feat-3488-browser-probes.mjs`) expects exactly one live-region warning: the error-count announcement must not fire on a clean initial load (count 0 → 0).

## Acceptance Criteria

- [ ] `"alert(" not in html` for the rendered template (pytest: `test_policy_builder_emit.py`).
- [ ] Rendered HTML contains exactly one each of `id="dim-add-error"` / `id="outcome-add-error"`, both `hidden`, neither with `role=`/`aria-live`; `#messages` has no `aria-live`; `#import-diagnostics` markup unchanged; existing `:317-318` asserts pass (pytest).
- [ ] Adding outcome `done` in `decision_table`, a duplicate outcome, a dim name containing `:`/`|`, and a duplicate dim each show the inline message, set `aria-invalid` on the input, write the same text to `#live-status`, raise no dialog, and clear on the next input event (probe — new cases).
- [ ] Opening a project with a bogus dimension type announces one `#live-status` text containing both "Project opened." and the error count (probe: `auth-invalid-model-*`, `live-import-error-offline`).
- [ ] Opening an invalid project when persistence emits a storage warning produces exactly one composed `#live-status` mutation containing completion, warning, error count, and the appropriate export clause. Multiple same-operation status writers preserve all distinct messages; later unrelated actions do not repeat them (browser MutationObserver).
- [ ] Two consecutive invalid Opens with the same error key each announce their current summary; a subsequent clean Open announces completion and no errors (browser).
- [ ] Browser computed-visibility checks show add errors hidden initially, visible on rejection, and hidden with empty text and cleared input attributes after correction/success. After a visible error, successful Open, Start blank, and mode switching clear stale errors; the outcome error is never visible in lifecycle mode. Markup `hidden` assertions alone are insufficient.
- [ ] Rendered HTML contains exactly one definition of `EXPORT_DISABLED_REASON`, and the error announcement is built from it (pytest string check).
- [ ] Replacing the only validator error with an unknown-skill error (count stays 1, export re-enables) produces a new announcement without the export-disabled clause (probe).
- [ ] Editing a field while the announcement key is unchanged produces no new `#live-status` mutation; fixing the last error announces "No errors." (probe MutationObserver).
- [ ] `.loops/verify-feat-3488-browser-persistence.yaml` `storage-disabled-degrades` stays green; `_newBug3502Sandbox` stubs cover new DOM calls in the sliced Open handler / `commit()` regions.
- [ ] Golden regenerated; `python -m pytest scripts/tests/` exits 0.

## Implementation Steps

1. Add `EXPORT_DISABLED_REASON` and `lastErrorKey` tracking; implement operation-scoped status composition and audit existing writers. Make successful Open always include the current validation summary, while ordinary edits retain key-based deduplication.
2. Add the two precisely placed inline error elements and effective hidden CSS; replace the four `alert(` sites; wire clear-on-input, clear-on-success, and Open/Start-blank/mode-change resets.
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
- `/ll:audit-issue-conflicts` - 2026-09-19T21:30:33 - `6b9c88d3-074c-4681-b7c9-240fc332f147.jsonl`
- `/ll:wire-issue` - 2026-09-19T21:05:53 - `39128071-49a7-41ee-a288-c86d0c6aa6ea.jsonl`
- `/ll:refine-issue` - 2026-09-19T20:57:46 - `7ba3809c-e334-468e-81b6-cf0bbfd0f90c.jsonl`
- `/ll:format-issue` - 2026-09-19T20:40:37 - `62ea2c42-153a-4077-bc55-dc91a943784a.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The "no assertive region" statement applies only to `#messages` and `#import-diagnostics` diagnostics. BUG-3512 legitimately adds a static `role="alert"` (`#conn-alert`) in the connected panel; channels are disjoint — BUG-3512 owns `#conn-*`, this issue owns `#live-status`. Announcement wording for Copy/Download disabled must match ENH-3511's `#validate-hint` text — resolved: this issue defines `EXPORT_DISABLED_REASON` (see Design Decisions). Verified post-BUG-3512: the `"alert(" not in html` criterion still holds — BUG-3512's `alert` locals/keys and `role="alert"` contain no `alert(`; the only four occurrences are the handler sites (now :2001, :2006, :2021, :2025).
