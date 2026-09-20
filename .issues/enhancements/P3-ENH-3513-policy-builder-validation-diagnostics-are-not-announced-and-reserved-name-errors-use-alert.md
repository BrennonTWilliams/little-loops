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
confidence_score: 100
outcome_confidence: 70
score_complexity: 17
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
---

# ENH-3513: Policy builder: validation diagnostics are not announced and reserved-name errors use alert()

## Summary

Found by ENH-3500 audit. Result diagnostics in `#messages` are not announced; validator errors disable Copy/Download, but Open announces only 'Project opened.' Reserved/duplicate names in add-outcome/add-dim use blocking `alert()` instead of inline messages. Announce validation summaries through the existing polite `#live-status` region and replace the four alerts with inline, associated errors. Repro: open a project with a bogus dimension type; try adding outcome 'done' in decision_table. Evidence: `auth-invalid-model-*`. The separate `live-import-error-offline` case exercises malformed frontmatter import and remains an unchanged-region regression check, not proof of Open announcements.

## Current Behavior

`#messages` (Result diagnostics) is not a live region: after an edit or Open project yields validator-error diagnostics, Copy/Download disable but only `#live-status` ('Project opened.') is announced. `#import-diagnostics` already uses polite announcements and remains unchanged. The `#add-outcome`/`#add-dim` handlers report reserved or duplicate names with blocking `alert()`.

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
- `scripts/tests/test_policy_builder_emit.py` — rendered markup and shared-string assertions.
- `scripts/tests/js/policy_validator.test.mjs` — tracked behavior tests, run by `scripts/tests/test_policy_builder_node_gate.py` under the local pytest suite.
- Browser probes — computed visibility, actual DOM writes, and repeated-delivery checks; retain the manual screen-reader smoke test.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- Named functions exist in `policy-router-builder.html.tmpl`: `renderMessages(model, diagnostics)` (:1296, called only from `updatePreview` :1800) and `showLiveStatus(text)` (:430, plain `textContent` overwrite, 12 callers, no clear/queue).
- Historical inventory before BUG-3512 (superseded for `#conn-*` by the context refresh below): exactly two — `#import-diagnostics` (:283, `role="status" aria-live="polite"`, hidden outside lifecycle mode by `applyModeVisibility` :1871, written directly at :1711-1746 without `showLiveStatus`) and `#live-status` (:323, same attrs). `#messages` (:315, `<ul class="messages">`), `#transition-graph`, `#conn-notices` (:350), `#conn-status` (:351) have no role/aria. No `role="alert"` or `aria-live="assertive"` exists anywhere.
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
- `.loops/probes/enh-3500-audit-probes.mjs` (:235-237 MutationObservers on `live-status`/`import-diagnostics`) — cases `auth-invalid-model-*` collect Open evidence; `live-import-error-offline` imports malformed frontmatter and checks the unchanged import region. Neither currently asserts the new announcement contract.

### Wiring: Tests

- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` — regenerate with the pinned render inputs in `test_enh3035_artifact_template_kit.py`, then review the diff.
- `scripts/tests/js/policy_validator.test.mjs` — add tracked behavioral tests for summary formatting, composition, key deduplication, startup, operation cleanup, and repeat-delivery scheduling. `_newBug3502Sandbox` executes the bootstrap slice `let state = seedExample();`…`function buildModel() {` and the Open-handler slice. Cover new module-level bindings and helper dependencies as well as DOM calls: place shared helpers/state within the bootstrap slice or explicitly supply them in the sandbox. Initialize announcement state before any storage read can invoke `warn`. The current sandbox stubs `renderAll` and has a null `getElementById`; extending stubs alone does not test real rendering/announcement integration.
- `scripts/tests/test_policy_builder_emit.py` — retain existing live-status/polite assertions; assert `#messages` remains non-live, `#import-diagnostics` markup stays unchanged, and the four `alert(` sites are gone.
- `.loops/probes/*.mjs` are gitignored, on-demand evidence collectors, not durable pytest regression coverage. Keep the core behavioral assertions in tracked `scripts/tests/js/` tests, enforced by the existing Node pytest gate. Browser checks supplement these tests for computed visibility and actual DOM behavior.
- The ENH-3500 observer reads final `textContent` once per callback and truncates it; it cannot prove one non-empty write or preservation of every message. Record individual writes or inspect each mutation record with full text. Install instrumentation before the action (before startup for startup checks), and deliberately exercise multiple synchronous writes so the recorder cannot hide an overwritten warning. Final-text snapshots and callback counts alone are insufficient.

## Program Design

### Types

- No new persisted shapes. Transient state includes the validation key, an operation-local message accumulator, and (if delivery is deferred) a pending-delivery handle/generation for cancellation.

### Signatures

- `renderMessages(model, diagnostics) -> errorCount` — return the count of all rendered errors, including template-side unknown-skill errors.
- `showLiveStatus(text) -> void` — enqueue within an operation; otherwise deliver through the repeat-aware writer.
- A synchronous operation wrapper with exception-safe flush/reset, plus shared summary formatting and inline-error cleanup helpers. Keep their dependencies available to the sliced test harness.

### Call Path

`cmd_policy_builder` -> `render_policy_builder_html` (stamps the template) -> in-page `renderMessages`; `add-dim`/`add-outcome` click handlers -> inline message replacing `alert()`

## Design Decisions

> **Context refresh (2026-09-19)**: BUG-3512 is **done** (2f5bdb89a). `:NNNN` line references in this issue predate it — roughly +4 up to `updatePreview` (now :1782) and +75 in the connected code (`renderConnected` now :2292). Function-name anchors remain correct; resolve by name, not line.

- **Diagnostics announcement**: `updatePreview` tracks the previous announcement key — the pair `(errorCount, hasValidatorError)` (module-level `let lastErrorKey = "0|false"`), not the count alone: going from one validator error to one unknown-skill error keeps the count at 1 but re-enables export, and must announce. When the key built from the `msg-error` items rendered by `renderMessages` (validator errors **plus** the template-side unknown-skill errors) changes, it calls `showLiveStatus`: `` `${n} error(s). ${EXPORT_DISABLED_REASON}` `` when validator errors exist, `"N error(s)."` when only non-gating unknown-skill errors exist, `"No errors."` when it returns to 0 from non-zero. No announcement for ordinary edits when the key is unchanged — this suppresses unchanged-key chatter; `oninput` can still change the key before a later `change` commits persistence. Successful Open is the explicit exception below.
- **Composition with existing `#live-status` writers**: compose one non-empty announcement write per synchronous authoring operation, preserving distinct statuses/warnings plus the applicable validation summary. Order completion text first (when present), warnings next, validation summary last. Do not let a persistence warning consume a pending summary or get overwritten by completion text. Nested calls join the enclosing operation; the outermost boundary flushes and resets state in `finally`, including on an exception, without inventing success text. No pending accumulator may capture later unrelated actions. Connected announcers remain unchanged.
- **Operation boundaries**: successful Open starts its scope inside `reader.onload`, after `_readStatus` checks and successful parsing, and ends after rendering, persistence, and completion status. Never keep a scope open across `FileReader` I/O. Failed, stale, and superseded reads do not force a validation summary or clear add errors. Wrap synchronous structural render-plus-persist paths too: `restoreFromSnapshot` (undo/redo), mode switching, `applyPreset`, Start blank, and successful Add handlers. Audit other structural handlers and multi-writer paths such as suggested-case additions. An `input` preview update and the later delegated `change`/`commit()` are separate operations; do not hold an accumulator across focus changes. An unchanged key suppresses only the diagnostic summary, not a new storage warning.
- **Startup**: compose initial storage/hydration warnings and the first rendered validation summary as one initialization operation, covering the first storage reads through `hydrateFromStorage()` and the initial `renderAll()`. Preserve all distinct warnings. A restored invalid draft (including unknown-skill-only errors) contributes its current summary; a clean initial model adds no validation summary. Clean startup with no warnings remains silent; clean startup with storage unavailable emits the storage warning once. Do not suppress all initial validation solely to protect warnings. A corrupted draft warning describes the fallback actually rendered and must survive that render.
- **Open is an explicit summary boundary**: every successful Open includes current error count and export availability even when the previous project had the same key. With validator errors, append `EXPORT_DISABLED_REASON`; with unknown-skill-only errors, use `"N error(s). Copy and Download are available."`; with no errors, use `"No errors. Copy and Download are available."`. Ordinary edits retain the shorter key-deduplicated summaries above. This exception must not introduce clean-startup chatter.
- **Repeated delivery and cancellation**: an empty reset before a non-empty write is permitted, but synchronous clear/set is not evidence of screen-reader delivery. Establish and document the delivery scheduling used by `showLiveStatus` during the browser/screen-reader check. If delivery is deferred, use a cancellable handle/generation: a newer announcement replaces an undelivered one; correcting/resetting an add error cancels its pending rejection, and a newer model/project state invalidates a pending obsolete validation summary. Keep operation composition synchronous, never hold its accumulator open until a timer fires, and do not replay canceled text. Browser tests must await delivery instead of assuming immediate text. Test rapid rejection→correction, invalid→clean replacement, and a subsequent unrelated status before pending delivery. Sequential repeated actions tested after each delivery must each announce once. Record the chosen scheduler and browser/screen-reader observations; DOM evidence does not substitute for the manual smoke test.
- **Shared export-disabled string**: this issue lands before ENH-3511 and therefore defines the one constant both use — `EXPORT_DISABLED_REASON = "Copy and Download are disabled until the errors above are fixed."`. The announcement is `` `${n} error(s). ${EXPORT_DISABLED_REASON}` ``; ENH-3511 writes the same constant into `#validate-hint`.
- **Inline add errors**: two static elements, `<small class="help msg-error" id="dim-add-error" hidden>` immediately after the `#add-dim` row and `<small class="help msg-error" id="outcome-add-error" hidden>` immediately after `#outcome-add-row`, inside the outcomes fieldset. Both are siblings of their respective rows. Add an explicit `small.help[hidden] { display: none; }` rule: existing `small.help { display: block; }` overrides native hidden styling. Each of the four `alert(` sites sets text, unhides, sets `aria-invalid="true"` and appends the error element ID to the input’s `aria-describedby` token list without duplicating it or replacing unrelated tokens, and sends the same text through `showLiveStatus`; the inline elements themselves are not live. On the next input event or successful add, clear text, hide the element, and remove the error-owned `aria-invalid` state and only the error ID from `aria-describedby` (remove that attribute only when no tokens remain). Cancel any pending announcement owned by the cleared error. Clear both add-error states on successful Open, Start blank, mode switching, undo/redo, and preset application. A successful structural rerender may centralize this cleanup, provided a rejected Add retains its error until correction or a subsequent reset. `applyModeVisibility` must explicitly hide/clear the outcome error when entering `issue_lifecycle`; a sibling does not inherit the row's hidden state.
- `storage-disabled-degrades` (`feat-3488-browser-probes.mjs`) expects exactly one live-region warning: the error-count announcement must not fire on a clean initial load (count 0 → 0).

## Acceptance Criteria

- [ ] `"alert(" not in html` for the rendered template (pytest: `test_policy_builder_emit.py`).
- [ ] Rendered HTML contains exactly one each of `id="dim-add-error"` / `id="outcome-add-error"`, both `hidden`, neither with `role=`/`aria-live`; `#messages` has no `aria-live`; `#import-diagnostics` markup unchanged; existing `:317-318` asserts pass (pytest).
- [ ] Adding outcome `done` in `decision_table`, a duplicate outcome, a dim name containing `:`/`|`, and a duplicate dim each show the inline message, set `aria-invalid` on the input, write the same text to `#live-status`, raise no dialog, and clear on the next input event (probe — new cases).
- [ ] Opening a project with a bogus dimension type announces one `#live-status` text containing both "Project opened." and the error count (tracked behavior test plus an instrumented Open browser case; `auth-invalid-model-*` remains supporting evidence).
- [ ] Opening an invalid project when persistence emits a storage warning produces exactly one non-empty composed `#live-status` write (an empty reset is permitted) containing completion, warning, error count, and the appropriate export clause. Multiple same-operation status writers preserve all distinct messages; later unrelated actions do not repeat them (tracked behavior test plus browser recording of individual full-text writes/mutation records, not callback counts).
- [ ] Two consecutive invalid Opens with the same error key each announce their current summary; a subsequent clean Open announces completion, no errors, and Copy/Download availability; an unknown-skill-only Open also explicitly announces availability (tracked behavior tests and browser).
- [ ] Browser computed-visibility checks show add errors hidden initially, visible on rejection, and hidden with empty text and cleared input attributes after correction/success. After a visible error, successful Open, Start blank, mode switching, undo/redo, and preset application clear stale errors; the outcome error is never visible in lifecycle mode. Markup `hidden` assertions alone are insufficient.
- [ ] A duplicate-name rejection followed by undo of the original addition clears the now-stale error and input attributes; redo and preset application also clear prior add errors (browser).
- [ ] A real screen-reader smoke test confirms repeated identical invalid Opens and repeated rejected Adds are each announced once. Record browser/screen-reader versions and observed delivery; DOM mutations alone do not satisfy this check.
- [ ] Rendered HTML contains exactly one definition of `EXPORT_DISABLED_REASON` and one copy of its literal sentence; a behavioral assertion verifies that validator-error announcements include its value.
- [ ] Replacing the only validator error with an unknown-skill error (count stays 1, export re-enables) produces a new announcement without the export-disabled clause (probe).
- [ ] Editing a field while the announcement key is unchanged and no independent status/warning occurs produces no new `#live-status` mutation; fixing the last error announces "No errors." (tracked behavior test plus browser mutation recording).
- [ ] `.loops/verify-feat-3488-browser-persistence.yaml` `storage-disabled-degrades` stays green; `_newBug3502Sandbox` covers new DOM calls, module-level state, and helper dependencies in the sliced Open handler / `commit()` regions.
- [ ] Startup tests cover a clean model without warnings (silent), clean model with storage unavailable (one warning), restored validator-invalid and unknown-skill-only drafts (summary), and corrupted-draft fallback (warning retained). Combined startup warnings and validation appear in one composed write when both occur.
- [ ] Structural edits, presets, mode changes, and undo/redo that change validation and trigger a first-time persistence warning preserve both messages. Input and later change events are separate operations; unchanged-key suppression never hides a fresh warning.
- [ ] Delayed Open tests verify that edits while reading are not captured by Open's accumulator; failed/stale/superseded reads do not force successful-Open summaries or clear add errors. An injected exception inside an operation leaves the accumulator closed, emits no invented completion, and allows the next unrelated status to be delivered normally.
- [ ] If delivery is deferred, controlled-scheduler tests prove that correction, project/model replacement, or a newer status cannot be followed by an obsolete queued announcement. Sequential identical Opens/rejected Adds still deliver once per action after waiting for each delivery.
- [ ] An unrelated `aria-describedby` token survives rejection, repeated rejection, input correction, and structural reset; the error token appears at most once and is removed on clear.
- [ ] Tracked JS regression tests run through the existing Node pytest gate. Browser instrumentation distinguishes individual non-empty writes even when several occur synchronously and retains full composed text. `live-import-error-offline` remains a regression check for unchanged frontmatter-import diagnostics, not an Open-summary test.
- [ ] Golden regenerated; `python -m pytest scripts/tests/` exits 0.

## Implementation Steps

1. Add shared summary formatting, `EXPORT_DISABLED_REASON`, and validation-key tracking. Implement exception-safe synchronous composition at the explicit Open, structural-edit, and startup boundaries; audit every `showLiveStatus` writer. Keep shared state/helpers available to the sliced test harness.
2. Implement repeat delivery with the scheduling/cancellation contract above. Verify browser/screen-reader behavior, document the chosen scheduling, and make browser assertions await actual delivery when deferred.
3. Add the two inline error elements and effective hidden CSS; replace four `alert()` sites; preserve unrelated description tokens and wire input/success/structural resets, including cancellation of stale pending error announcements.
4. Add tracked JS regression tests and rendered-markup assertions; update sandbox dependencies. Add browser checks with per-write instrumentation for composition, startup, visibility, repeat delivery, and cancellation. Run the manual screen-reader smoke test and retain its evidence separately from automated results.
5. Regenerate the golden with pinned inputs, review its diff, and run `python -m pytest scripts/tests/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Announcement mechanism is **decided** — see Design Decisions (`#messages` stays non-live; count-change announcements via `showLiveStatus`)
- Sequenced via `blocked_by`: BUG-3512 → **ENH-3513** → ENH-3511 → ENH-3510 → ENH-3514 → BUG-3516 (shared template + byte-compared golden — never run in parallel)
- Re-run `.loops/verify-feat-3488-browser-persistence.yaml` (`storage-disabled-degrades`); supplement `auth-invalid-model-*` with asserted, instrumented Open cases. Re-run `live-import-error-offline` only as an unchanged-import-region regression check.
- Regenerate the golden after reviewing the diff

## Impact

- **Priority**: P3 - accessibility and UX consistency
- **Effort**: Moderate - operation-scoped announcement composition, reset paths, four `alert()` replacements, and browser/assistive-technology verification
- **Risk**: Moderate - repeated or overwritten announcements and stale inline errors require behavioral verification
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-19 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-09-20T00:50:13 - `b1e66617-7ca3-4c73-8eef-611558ec10fe.jsonl`
- `/ll:verify-issues` - 2026-09-20T00:42:35 - `87477791-8eac-4eaa-a6b5-62a48362f015.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-19T21:30:33 - `6b9c88d3-074c-4681-b7c9-240fc332f147.jsonl`
- `/ll:wire-issue` - 2026-09-19T21:05:53 - `39128071-49a7-41ee-a288-c86d0c6aa6ea.jsonl`
- `/ll:refine-issue` - 2026-09-19T20:57:46 - `7ba3809c-e334-468e-81b6-cf0bbfd0f90c.jsonl`
- `/ll:format-issue` - 2026-09-19T20:40:37 - `62ea2c42-153a-4077-bc55-dc91a943784a.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The "no assertive region" statement applies only to `#messages` and `#import-diagnostics` diagnostics. BUG-3512 legitimately adds a static `role="alert"` (`#conn-alert`) in the connected panel; channels are disjoint — BUG-3512 owns `#conn-*`, this issue owns `#live-status`. Announcement wording for Copy/Download disabled must match ENH-3511's `#validate-hint` text — resolved: this issue defines `EXPORT_DISABLED_REASON` (see Design Decisions). Verified post-BUG-3512: the `"alert(" not in html` criterion still holds — BUG-3512's `alert` locals/keys and `role="alert"` contain no `alert(`; the only four occurrences are the handler sites (now :2001, :2006, :2021, :2025).
