---
id: BUG-3512
type: BUG
title: 'Policy builder connected panel: focus drops to BODY after Review/Submit and
  status regions are not live'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T20:00:57Z'
relates_to:
- ENH-3500
- ENH-3511
- ENH-3514
- ENH-3513
- ENH-3510
---

# BUG-3512: Policy builder connected panel: focus drops to BODY after Review/Submit and status regions are not live

## Summary

Found by ENH-3500 audit (keyboard traces kb-happy-path, kb-outcome-unknown, kb-rejected). After Enter on Review and Enter on Submit, document.activeElement becomes BODY (control disabled/re-rendered), so keyboard users lose place. #conn-status, #conn-notices and #conn-review-info have no role=status/aria-live, so accepted/rejected/outcome-unknown transitions and review results are not announced (DOM announcement support only; no manual screen-reader check performed). Expected: focus stays on or moves to a sensible control/status; outcome text announced. Evidence: kb-*-keyboard.json.

## Current Behavior

- After pressing Enter on **Review** (`#conn-review-btn`) or **Submit** (`#conn-submit-btn`), `document.activeElement` becomes `BODY`. `renderConnected` disables the control (`st.busy`, or `rv.status !== "ready"`) and rebuilds the status DOM, so the focused element loses focus and keyboard users lose their place.
- `#conn-status`, `#conn-notices` and `#conn-review-info` carry no `role="status"` / `aria-live`, so accepted / rejected / outcome-unknown transitions and review results are not announced. This is DOM-level evidence only; no manual screen-reader check was performed.

Evidence: `kb-happy-path`, `kb-outcome-unknown`, `kb-rejected` keyboard traces (`kb-*-keyboard.json`) from the ENH-3500 audit.

## Steps to Reproduce

1. Open the policy builder in connected mode (`CONNECTED_CONTEXT` true) and select an issue in `#conn-issue`.
2. Tab to `#conn-review-btn` and press Enter.
3. Observe: `document.activeElement` is `BODY`; `#conn-review-info` updates silently.
4. Tab to `#conn-submit-btn` (enabled once review is `ready`) and press Enter.
5. Observe: `document.activeElement` is `BODY` again; the accepted / rejected / outcome-unknown result renders in `#conn-status` with no live-region announcement.

## Expected Behavior

- Focus stays on the activated control where the control is only transiently busy (Review while hashing, Refresh during a poll); otherwise it moves to `#conn-status`. It is never `BODY`.
- Review results, notices, and delivery-state transitions (accepted, rejected, outcome-unknown) are announced once per change through static live regions — polite for review/accepted/outcome-unknown, `role="alert"` for rejected. Poll re-renders with unchanged content announce nothing.

## Root Cause

- **File**: `scripts/little_loops/templates/policy-router-builder.html.tmpl`
- **Anchor**: `renderConnected(st)`, plus the `#conn-review-info`, `#conn-notices` and `#conn-status` markup in `#connected-panel`
- **Cause**: `renderConnected` sets `disabled` on the focused button and clears/rebuilds `#conn-status` and `#conn-notices` via `innerHTML = ""` on every state change, with no focus management. The three output containers are plain `<p>`, `<ul>` and `<div>` elements with no live-region semantics.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- **Where focus is actually lost**: the focus drop happens at the *disable*, not the `innerHTML` rebuild. `#conn-status`/`#conn-notices` rebuilds do not contain the buttons. The click handler calls `submissionController.review()`/`.submit()`, whose first `emit()` is synchronous inside the handler: `startReview` emits `review.status = "hashing"` (`busy = true`), and `sendPost` emits with `submitting = true`. `renderConnected` then sets `disabled` on the focused button (lines 2250-2251) and focus moves to `BODY`. Hiding a focused `#conn-again-btn`/`#conn-retry-btn`/`#conn-refresh-btn` (lines 2253-2256) does the same.
- **Re-enable is asynchronous and never restores focus**: Review re-enables when the `sha256Hex` promise resolves (`review.status = "ready"`, `busy = false`), and after submit when `submitting` clears. No code calls `.focus()`.
- **Submit does not come back after a POST**: `submit()` resets `review = {status:"none"}` before `sendPost`, so `rv.status !== "ready"` keeps `#conn-submit-btn` disabled after the response settles; it re-enables only after a new Review reaches `ready`. Focus therefore cannot be returned to Submit; the target must be another element (the status region, Review, or the next available action).
- **Announcement gap**: `#conn-review-info` is updated by `textContent` (permanent element); `#conn-notices` and `#conn-status` children are rebuilt on every emit, including every 2 s/10 s poll response. `#conn-status` itself is a permanent container, so live semantics belong on the container while the state class stays on the inner `.conn-status` child.
- **Re-announcement hazard**: because the poll rebuild replaces `#conn-status` children with identical text, a live region there may re-announce unchanged content on each poll response depending on how the region is updated; the fix has to decide what constitutes a *change* worth announcing.
- **Focus-target feasibility**: Expected Behavior ("focus stays on the activated control") is satisfiable only where the control is re-enabled in the same render; a control disabled at the emit moment cannot hold focus (`Review` while `busy`, `Submit` after submit).
- **Naming**: the template has no `SubmissionState` type; state is the `st` object from `getState()`. `_restoreConnectedFocus` and `_announceConnected` are proposed new helpers, absent from the template today.

## Proposed Solution

This section is the single source of truth; it supersedes the capture-time sketch (runtime `role="alert"` on `#conn-status`, "focus the Review button after Review"), both of which the research findings above rule out.

### Announcements: dedicated static announcers, not a live `#conn-status`

`#conn-status` must **not** become a live region: its children are rebuilt on every 2 s / 10 s poll emit and can contain `<details>`/`<pre>` blocks with 40 lines of stdout/stderr, so a live container would re-announce unchanged text or read log dumps aloud.

1. Add two static, visually-hidden elements inside `#conn-body`, following the `#live-status` convention (static attributes, `textContent` updates only, never rebuilt):
   - `#conn-live` — `role="status" aria-live="polite"`
   - `#conn-alert` — `role="alert"`
   A visually-hidden utility class is added if the template has none.
2. Add static `role="status" aria-live="polite"` to `#conn-review-info` (permanent element, already updated by `textContent`). `#conn-notices` and `#conn-status` get no live attributes.
3. In `renderConnected`, derive a one-line summary from state — delivery state + `sub.statusLabel` + terminal/paused flags, plus newly added `st.notices` — and write it to the announcer **only when it differs from the last announced string** (module-level `_lastConnAnnounce`). `rejected` summaries go to `#conn-alert`; everything else to `#conn-live`. This defines "a change worth announcing" and makes poll re-renders silent. No `role` is ever changed at runtime.

### Focus: avoid the drop first, restore only where unavoidable

4. **Transient busy → `aria-disabled`, not `disabled`.** For `#conn-review-btn` and `#conn-refresh-btn`, the `st.busy` component is expressed as `aria-disabled="true"` (plus disabled styling) so the focused button keeps focus through hashing / polling. Genuine unavailability stays on real `disabled`: `!av.ok` for Review, and all of `#conn-submit-btn`'s conditions (`rv.status !== "ready"`, `outcome_unknown`, `!av.ok`, `busy`). This preserves the `enh-3507-served-page-probes.mjs` contract (`!#conn-submit-btn.disabled` after review).
5. **Click guards for `aria-disabled` buttons.** `startReview` returns early only on `review.status === "hashing"` (not while `submitting`), and `refreshStatus` has no busy guard at all, so the template's `.onclick` handlers for Review and Refresh must return early when `submissionController.getState().busy`. (`submit()`/`retry()` already guard on `submitting`.)
6. **Restore after the fact is impossible — capture first.** At the top of `renderConnected`, capture `const prev = document.activeElement` *before* the `disabled`/`hidden` assignments. After them, call `_restoreConnectedFocus(prev)`: if `prev` is one of the `conn-*` buttons and is now `disabled` or `hidden`, move focus to `#conn-status` (given static `tabindex="-1"`); otherwise do nothing. This covers Submit (which stays disabled after a POST because `submit()` resets `review`) and hidden `#conn-again-btn`/`#conn-retry-btn`, and never steals focus on poll-driven renders because it fires only when the previously focused control itself became unavailable.

### Coordination

7. Land this before ENH-3510/3511/3514, which edit the same function; they re-anchor by function name, not line number. ENH-3511's `aria-describedby` reasons apply to both `disabled` and `aria-disabled` buttons — the `aria-disabled` decision in step 4 is the convention it follows. ENH-3514's `is-*` class rename is unaffected since no semantics sit on the inner `.conn-status` child.

## Implementation Steps

`commands.tdd_mode` is on — red first.

1. **Red (pytest)**: in `scripts/tests/test_policy_builder_emit.py`, add a test asserting the emitted HTML contains `id="conn-live"` with `role="status"` + `aria-live="polite"`, `id="conn-alert"` with `role="alert"`, `role="status"` on `#conn-review-info`, `tabindex="-1"` on `#conn-status`, and **no** `aria-live`/`role` on `#conn-status` or `#conn-notices`. Confirm it fails.
2. **Template markup**: add the announcers, attributes and visually-hidden class in `policy-router-builder.html.tmpl`.
3. **Template script**: announcer diffing, `aria-disabled` for transient busy, click guards, `prev` capture + `_restoreConnectedFocus` in `renderConnected`.
4. **Golden**: regenerate `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html`. No regeneration helper exists; render under the same pinned inputs as `_pin_golden_render_inputs` in `test_enh3035_artifact_template_kit.py` and write the bytes to `GOLDEN`.
5. **Probe**: add `conn-live` and `conn-alert` to the MutationObserver id list in `.loops/probes/enh-3500-audit-probes.mjs` (`keyboardTrace()`), otherwise the trace keeps reporting `live: null` for `#conn-status` and misses the real announcements.
6. **Verify**: run `python -m pytest scripts/tests/` and re-run `.loops/verify-enh-3500-audit.yaml`.

## Acceptance Criteria

- Pytest (step 1) passes; `test_persistence_and_history_affordances_present`, the golden byte-identity test, and the mirror/audience gates pass.
- **Probe-verified, not pytest**: in `kb-happy-path`, `kb-outcome-unknown` and `kb-rejected`, `after` is never `BODY` for "Enter on Review" (stays `conn-review-btn`) or "Enter on Submit" (`conn-status`), including after async re-enable and poll re-renders.
- `liveRegionChanges` shows one `conn-live`/`conn-alert` entry per state transition (rejected → `conn-alert`) and none for poll responses with unchanged state.
- Focus is not moved when the user is focused outside the `conn-*` buttons during a poll render.
- `enh-3507-served-page-probes.mjs` text/enabled contracts still hold.
- Still DOM-level evidence only; no manual screen-reader check is claimed.

## Impact

- **Priority**: P2 - keyboard and screen-reader users cannot follow the connected submit flow
- **Effort**: Small-Medium - markup, announcer diffing and focus handling in one render function, plus golden regeneration and a probe id-list update
- **Risk**: Low - additive ARIA attributes and focus moves scoped to the connected panel
- **Breaking Change**: No

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — the only source file. Static markup at `#conn-review-info` (line 349, `<p class="hint">`), `#conn-notices` (350, `<ul class="messages">`), `#conn-status` (351, `<div class="conn-block">`); `renderConnected(st)` at line 2217; button `disabled`/`hidden` assignments at 2250-2256; handlers at 2322-2326; `submissionController.onChange(renderConnected)` at 2327; initial render at 2333.
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` — byte-for-byte golden of the rendered template (`test_enh3035_artifact_template_kit.py::test_policy_builder_renders_byte_identically_to_golden_fixture`); any template edit fails that test until the golden is regenerated.
- `scripts/little_loops/templates/policy_builder_core.mjs` needs no change: `createSubmissionController` (line ~3756) is DOM-free and no `document.*`/`.focus` appears in it. DOM and focus code belongs in the template's inline script.

**Dependent Files (Callers/Importers)**
- `renderConnected` has one registration site: `submissionController.onChange(renderConnected)` (line 2327) plus the bootstrap call at 2333. It runs synchronously on every controller `emit()`: review start/finish, `sendPost` start/finish, every poll response (`schedulePoll` 2000 ms, 10000 ms for `awaiting_approval`), `loadIssues`, `contextChanged`, `draftChanged`, `documentOpened`.
- `render_policy_builder_html` (`scripts/little_loops/cli/artifact/policy_builder.py`) inlines the template for both `cmd_policy_builder` (offline; `CONNECTED_CONTEXT` null, panel hidden) and the served page (`policy_builder_routes.py`, `serve.py`). The `/*__BUILDER_CORE_JS__*/` and `/*__CONNECTED_CONTEXT_JSON__*/` markers must stay literal.

**Conventions in Force**
- Live regions are static markup carrying both `role="status"` and `aria-live="polite"`, updated only via `textContent`, never rebuilt — evidence: `#import-diagnostics` (line 283), `#live-status` (line 323), `showLiveStatus` (line 430). The three `conn-*` outputs are the exception.
- No focus management exists anywhere in the template or any other template under `scripts/little_loops/templates/` (no `.focus()`, `tabindex`, `activeElement`, `aria-atomic`, `role="alert"`). Whatever this fix adds is the first instance and sets the convention; ENH-3511 and ENH-3513 will follow it.
- Roles/aria attributes are static markup; nothing in the template changes `role` at runtime.
- Private DOM helpers use a `_` prefix (`_el`, `_tailLines`, `_reviewInput`); ids resolve through `$` (line 643). Connected buttons are wired with `.onclick =`.
- The `.conn-status` CSS class (with `is-success|is-warning|is-error`, lines 170-173) is applied to an inner `div` created on each render (line 2275), not to the `#conn-status` container (class `conn-block`). Semantics on the container and state classes on the child are separate elements.

**Tests**
- `scripts/tests/test_policy_builder_emit.py::test_persistence_and_history_affordances_present` (line ~309) asserts `id="live-status"` and file-wide `'aria-live="polite"' in html`; it must keep passing. No pytest or `node --test` test references `conn-status`, `renderConnected` or `conn-review-btn`; JS tests exercise the controller only, never DOM or focus.
- Browser behavior is verified by on-demand Playwright probes, not pytest: `.loops/probes/enh-3500-audit-probes.mjs` (`keyboardTrace()` records `document.activeElement` before/after Enter on `#conn-review-btn`/`#conn-submit-btn` and a `MutationObserver` log with the enclosing `aria-live`), driven by `.loops/verify-enh-3500-audit.yaml`; `.loops/probes/enh-3507-served-page-probes.mjs` reads `#conn-status`/`#conn-review-info` `textContent` and waits on `#conn-submit-btn` becoming enabled, so those text/enabled contracts must hold.

**Sibling issues on the same region** (all `relates_to: ENH-3500`): ENH-3511 adds `aria-describedby` reasons to the same disabled buttons and lists `renderConnected`; ENH-3514 may rename the `is-*` vs `msg-*` class vocabulary at line 2275, the block where this fix would set `role="alert"` for `rejected`; ENH-3513 adds live semantics to `#messages`/`#import-diagnostics` (double-announcement risk with `#live-status`); ENH-3510 edits the `#conn-issue-note` line in `renderConnected`.

## Program Design

### Types

- `busy: bool` — existing submission-controller state field read by `renderConnected`
- `status: str` — existing `review.status` field (`hashing|refused|ready`)

### Signatures

- `renderConnected(st: object) -> None` — existing in `policy-router-builder.html.tmpl`; captures `document.activeElement` before the `disabled`/`hidden` assignments, restores focus after them, and updates the announcers on change
- `_restoreConnectedFocus(prev: Element) -> None` — new private helper (`_` prefix per template convention); focuses `#conn-status` when `prev` is a `conn-*` button that became disabled/hidden
- `_announceConnected(st: object) -> None` — new private helper; writes the derived summary to `#conn-live` / `#conn-alert` only when it differs from `_lastConnAnnounce`

### Call Path

`cmd_policy_builder` -> `render_policy_builder_html` (inlines `policy-router-builder.html.tmpl`) -> browser-side `renderConnected` -> `_restoreConnectedFocus`, `_announceConnected`

## Status

**Open** | Created: 2026-09-19 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-09-19T20:55:40 - `274231e5-4fb2-4b8c-8eff-785a5007e300.jsonl`
- `/ll:format-issue` - 2026-09-19T20:39:00 - `62ea2c42-153a-4077-bc55-dc91a943784a.jsonl`
