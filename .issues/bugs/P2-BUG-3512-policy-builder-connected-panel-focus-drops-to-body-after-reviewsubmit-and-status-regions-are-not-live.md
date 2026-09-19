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
confidence_score: 100
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 18
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

- Focus stays on the activated control where the control is only transiently busy (Review while hashing); otherwise it moves to `#conn-status`. It is never `BODY`. (A poll is not a busy state: `busy` is `submitting || review.status === "hashing"` and `readback` never sets it, so Refresh is never disabled while it holds focus.)
- Review results, notices, and delivery-state transitions (accepted, rejected, outcome-unknown) are announced once per change through static live regions — polite for review/accepted/outcome-unknown, `role="alert"` for rejected. Poll re-renders with unchanged content announce nothing, the initial render of a restored session announces nothing, and a repeat of the same outcome for a *new* request is announced again.

## Root Cause

- **File**: `scripts/little_loops/templates/policy-router-builder.html.tmpl`
- **Anchor**: `renderConnected(st)`, plus the `#conn-review-info`, `#conn-notices` and `#conn-status` markup in `#connected-panel`
- **Cause**: `renderConnected` sets `disabled` on the focused button and clears/rebuilds `#conn-status` and `#conn-notices` via `innerHTML = ""` on every state change, with no focus management. The three output containers are plain `<p>`, `<ul>` and `<div>` elements with no live-region semantics.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- **Where focus is actually lost**: the focus drop happens at the *disable*, not the `innerHTML` rebuild. `#conn-status`/`#conn-notices` rebuilds do not contain the buttons. The click handler calls `submissionController.review()`/`.submit()`, whose first `emit()` is synchronous inside the handler: `startReview` emits `review.status = "hashing"` (`busy = true`), and `sendPost` emits with `submitting = true`. `renderConnected` then sets `disabled` on the focused button (lines 2250-2251) and focus moves to `BODY`. Hiding a focused `#conn-again-btn`/`#conn-retry-btn`/`#conn-refresh-btn` (lines 2253-2256) does the same.
- **Re-enable is asynchronous and never restores focus**: Review re-enables when the `sha256Hex` promise resolves (`review.status = "ready"`, `busy = false`), and after submit when `submitting` clears. No code calls `.focus()`.
- **Submit does not come back after a POST**: `submit()` resets `review = {status:"none"}` before `sendPost`, so `rv.status !== "ready"` keeps `#conn-submit-btn` disabled after the response settles; it re-enables only after a new Review reaches `ready`. Focus therefore cannot be returned to Submit; the target must be another element (the status region, Review, or the next available action).
- **Announcement gap**: `#conn-review-info` is updated by `textContent` (permanent element); `#conn-notices` and `#conn-status` children are rebuilt on every emit, including every 2 s/10 s poll response. `#conn-status` itself is a permanent container, but the proposed solution uses separate static announcers to avoid announcing rebuilt logs; the state class stays on the inner `.conn-status` child.
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
2. Add static `role="status" aria-live="polite"` to `#conn-review-info` (permanent element, already updated by `textContent`). `#conn-notices` and `#conn-status` get no live attributes. Because `renderConnected` runs on every poll emit and writing identical `textContent` still replaces the text node (some screen readers re-announce it, and the probe's MutationObserver logs it), guard the write: `if (el.textContent !== info) el.textContent = info;`.
3. Track delivery/status changes independently from notice additions. Keep `_lastConnStatusKey` (request ID + stable status summary) and `_lastConnNotices` (the previous notice set). On each render, compute the status change and notices absent from the previous set, then update both baselines. Emit only the changed status and/or newly added notices; an unchanged render does not write either announcer. Never put a transient "new notices" suffix into the status comparison key: its disappearance on the next poll must not trigger another announcement. Clearing notices updates their baseline silently so a later recurrence can be announced again. No `role` is changed at runtime.
   - **Wording — reuse the visible lines.** `accepted`: the `Status: …` line (plus the missing / conflict / paused `pollNote` / "Finished." lines when present). `rejected`: the `Rejected (code): message` or request-conflict line — include the error message. `outcome_unknown`: the matching outcome-unknown sentence. A changed rejection goes to `#conn-alert`; other status changes and notice-only updates go to `#conn-live`. Combine notices with a status change occurring in the same render into one payload; do not repeat an unchanged rejection merely because a notice was added.
   - **Expose POST activity explicitly.** Add `submitting: boolean` to `createSubmissionController.getState()`, exposing the existing internal flag without changing its lifecycle. When `st.submitting` is true, the status summary is "Submitting…", taking precedence over the stored `outcome_unknown` delivery state. `busy` is not a substitute: it also covers hashing. Test pending and settled POSTs, retries, and hashing without a POST.
   - **Comparison key includes the request.** Use the request ID plus the stable status summary (null-safe when no submission exists), so the same outcome for a second request is announced again. When a new key warrants an identical payload, ensure a real text update occurs rather than suppressing it solely because the displayed string matches.
   - **Notices without a submission.** Process notice additions even when `st.submission` is null, including storage failures before POST. Do not put announcement handling behind the existing `if (!sub) return`.
   - **Clear the other announcer when switching.** Writing a new payload to `#conn-live` clears a nonempty `#conn-alert` and vice versa. Do not clear or rewrite regions on unchanged renders. Clearing mutations are not new announcement payloads.
   - **First render is silent.** Seed both status and notice baselines with `_connAnnounceSeeded` without writing to either announcer. In the normal restoration path, `documentOpened()` calls `loadSession()` before emitting the restored state; there is no confirmed restoration-order defect. Verify this from before application bootstrap, rather than observing only after navigation. Subsequent readback changes remain announceable; unchanged restored state does not announce.

### Focus: avoid the drop first, restore only where unavoidable

4. **Transient busy → `aria-disabled`, not `disabled`.** For `#conn-review-btn` only, the `st.busy` component is expressed as `aria-disabled="true"` so the focused button keeps focus through hashing. The template has no `:disabled` / `[aria-disabled]` CSS today (buttons use browser defaults), so add a `button[aria-disabled="true"]` rule matching the default disabled look — there is nothing to reuse. `#conn-refresh-btn` keeps real `disabled = st.busy`: `busy` never coincides with Refresh holding focus (it requires activating Review/Submit), so converting it would be dead code; its hidden case (readback conflict → `rejected`) is covered by step 6. Genuine unavailability stays on real `disabled`: `!av.ok` for Review, and all of `#conn-submit-btn`'s conditions (`rv.status !== "ready"`, `outcome_unknown`, `!av.ok`, `busy`). This preserves the `enh-3507-served-page-probes.mjs` contract (`!#conn-submit-btn.disabled` after review).
5. **Click guard for the `aria-disabled` button.** `startReview` returns early only on `review.status === "hashing"` (not while `submitting`), so the template's `.onclick` handler for Review must return early when `submissionController.getState().busy`. (`submit()`/`retry()` already guard on `submitting`; Refresh stays really `disabled`.)
6. **Capture before mutations; restore after rendering.** At the top of `renderConnected`, capture `const prev = document.activeElement` before any `disabled`/`hidden` assignments, including ancestor visibility changes. After rendering the destination's current content, call `_restoreConnectedFocus(prev)`: if `prev` is one of the connected-panel buttons and has become disabled or effectively hidden, move focus to the visible destination; otherwise do nothing. Effective visibility includes hidden ancestors such as `#conn-body`, not only `prev.hidden`. `#conn-status` gets static `tabindex="-1" role="group" aria-label="Submission status"`. If it is hidden because the body became unavailable, use visible `#conn-unavailable` (static `tabindex="-1"`) instead. Never focus a hidden destination. This covers Submit, hidden Again/Retry/Refresh buttons, and a button hidden solely by its ancestor. Ordinary poll renders must not move focus from an unaffected control or elsewhere on the page.
   - **Finalize every connected render.** Run notice announcements and focus recovery even when no submission exists; replace the early `if (!sub) return` with conditional status rendering or an equivalent shared finalization path. Render the current status/unavailability content before moving focus. A pre-POST failure that leaves Submit enabled should retain its focus and announce its notice; a failure that invalidates review and disables Submit should move focus to the visible status target. The offline panel remains hidden and must not receive focus.

### Coordination

7. Land this before ENH-3510/3511/3514, which edit the same function; they re-anchor by function name, not line number. ENH-3511's `aria-describedby` reasons apply to both `disabled` and `aria-disabled` buttons — the `aria-disabled` decision in step 4 is the convention it follows. ENH-3514's `is-*` class rename is unaffected since no semantics sit on the inner `.conn-status` child.

## Implementation Steps

`commands.tdd_mode` is on — red first.

1. **Red (pytest)**: in `scripts/tests/test_policy_builder_emit.py`, add a test asserting the emitted HTML contains `id="conn-live"` with `role="status"` + `aria-live="polite"`, `id="conn-alert"` with `role="alert"`, `role="status"` on `#conn-review-info`, `tabindex="-1"` + `role="group"` + `aria-label` on `#conn-status`, `tabindex="-1"` on `#conn-unavailable`, a `button[aria-disabled="true"]` CSS rule, **no** `aria-live` on `#conn-status` or `#conn-notices`, and no `role="status"`/`role="alert"` on either. Confirm it fails.
2. **Template markup**: add the announcers, attributes and visually-hidden class in `policy-router-builder.html.tmpl`.
3. **Controller and template script**: first add failing controller tests for the exposed `submitting` flag, then expose it from `getState()`. Implement independent request-keyed status and notice baselines, silent first-render seeding, and guarded announcer clearing/writes. Add the guarded `#conn-review-info` write, Review busy `aria-disabled` and click guard, and focus capture before all visibility mutations. Render destination content and finalize announcements/focus on both submission and no-submission paths, with ancestor visibility checks and the unavailable fallback.
4. **Golden**: regenerate `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html`. No regeneration helper exists; render under the same pinned inputs as `_pin_golden_render_inputs` in `test_enh3035_artifact_template_kit.py` and write the bytes to `GOLDEN`.
5. **Probe (red before the behavioral fix)**: extend `.loops/probes/enh-3500-audit-probes.mjs` beyond adding observer IDs. Add focused BUG-3512 assertion cases with a failing exit status and retain their trace artifacts; the existing audit loop is evidence collection, not a behavioral pass/fail gate. Include `conn-live`/`conn-alert`, record `role` as well as explicit `aria-live` (alerts have implicit live semantics), and include `ariaDisabled` in `COLLECT`. Distinguish nonempty announcement payloads from clearing mutations. Install bootstrap observation through an init script before application code runs, including restored-session fixtures. Use controlled hashing/POST completion and explicit poll responses; assert focus during busy states and after settlement rather than relying on a 400 ms sample. Cover the acceptance cases below, including negative controls for unchanged renders.
6. **Verify**: run `python -m pytest scripts/tests/`, the focused browser assertions, and `.loops/verify-enh-3500-audit.yaml`. Inspect the trace artifacts as well as assertion results; `AUDIT_EVIDENCE_COLLECTED` alone is not proof of passing behavior. Playwright unavailable means browser validation remains unverified, not passed.

## Acceptance Criteria

- Pytest (step 1) passes; `test_persistence_and_history_affordances_present`, the golden byte-identity test, and the mirror/audience gates pass.
- **Probe-verified, not pytest**: in `kb-happy-path`, `kb-outcome-unknown` and `kb-rejected`, `after` is never `BODY` for "Enter on Review" (stays `conn-review-btn`) or "Enter on Submit" (`conn-status`), including after async re-enable and poll re-renders.
- For each announceable state transition, the trace shows one nonempty payload in the appropriate announcer (rejected → `conn-alert`). Empty clearing mutations are recorded separately and excluded from this count. Unchanged poll responses cause no announcer mutations. Notice additions announce once; a following unchanged poll does not re-announce the status or notice.
- `liveRegionChanges` has no `conn-review-info` entries for poll responses (guarded write), and no `conn-live`/`conn-alert` entry from the initial render of a restored session.
- Two consecutive rejections with an identical message (distinct `requestId`s) each produce a `conn-alert` entry; `#conn-alert` is empty after a later acceptance.
- Explicit browser cases cover restored accepted/rejected sessions with observation installed before bootstrap; repeated unchanged polls; two identical rejections followed by acceptance; and focus outside the connected buttons during polling. Initial restored state is silent, while subsequent changed readback status is announced.
- Controlled pending hashing and POST cases verify Review retains focus while hashing and its Enter/Space/click activations while busy start no additional review or POST. Pending POSTs announce "Submitting…", not a premature unknown outcome; settlement announces the actual outcome. Controller tests verify `submitting` for initial POST, retry, settlement, and hashing alone.
- A storage failure before any submission exists still announces its notice. If Submit remains enabled it retains focus; if the failure clears review and disables it, focus moves to visible `#conn-status`. Finalization is not skipped when `sub` is null.
- A focused button hidden only through `#conn-body` triggers recovery to visible `#conn-unavailable`; hidden Again/Retry/Refresh controls recover to visible `#conn-status`. Destination content is rendered before focus moves. Focus outside the connected buttons and focus on unaffected controls stay unchanged on polls.
- `enh-3507-served-page-probes.mjs` text/enabled contracts still hold.
- Still DOM-level evidence only; no manual screen-reader check is claimed.

## Impact

- **Priority**: P2 - keyboard and screen-reader users cannot follow the connected submit flow
- **Effort**: Small-Medium - markup, announcer diffing and focus handling, explicit controller POST-state exposure, golden regeneration, and focused browser assertions
- **Risk**: Low - additive ARIA attributes and focus moves scoped to the connected panel
- **Breaking Change**: No

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — DOM rendering and interaction changes. Static markup at `#conn-review-info` (line 349, `<p class="hint">`), `#conn-notices` (350, `<ul class="messages">`), `#conn-status` (351, `<div class="conn-block">`); `renderConnected(st)` at line 2217; button `disabled`/`hidden` assignments at 2250-2256; handlers at 2322-2326; `submissionController.onChange(renderConnected)` at 2327; initial render at 2333.
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` — byte-for-byte golden of the rendered template (`test_enh3035_artifact_template_kit.py::test_policy_builder_renders_byte_identically_to_golden_fixture`); any template edit fails that test until the golden is regenerated.
- `scripts/little_loops/templates/policy_builder_core.mjs` — expose the existing internal `submitting` flag through `createSubmissionController.getState()`. Keep the controller DOM-free; focus and announcement logic belongs in the template.
- `scripts/tests/js/policy_submission.test.mjs` — controller coverage for the exposed POST activity flag.
- `scripts/tests/test_policy_builder_emit.py` — static emitted-markup assertions.
- `.loops/probes/enh-3500-audit-probes.mjs` — bootstrap instrumentation and focused behavioral assertions, with retained trace evidence.

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

**Sibling issues on the same region** (all `relates_to: ENH-3500`): ENH-3511 adds `aria-describedby` reasons to the same disabled buttons and lists `renderConnected`; ENH-3514 may rename the `is-*` vs `msg-*` class vocabulary at line 2275, the visual status block; this fix puts alert semantics on the separate static announcer; ENH-3513 adds live semantics to `#messages`/`#import-diagnostics` (double-announcement risk with `#live-status`); ENH-3510 edits the `#conn-issue-note` line in `renderConnected`.

## Program Design

### Types

- `busy: bool` — existing submission-controller state field read by `renderConnected`
- `submitting: bool` — new public state field exposing the existing internal POST-in-flight flag
- `_lastConnStatusKey: string | null` — request ID plus stable status summary, independent of notices
- `_lastConnNotices: Set<string>` — prior render's notices; additions announce, removals silently update the baseline
- `status: str` — existing `review.status` field (`hashing|refused|ready`)

### Signatures

- `renderConnected(st: object) -> None` — existing in `policy-router-builder.html.tmpl`; captures `document.activeElement` before the `disabled`/`hidden` assignments, renders destination content, then finalizes focus and announcements even without a submission
- `_restoreConnectedFocus(prev: Element) -> None` — new private helper (`_` prefix per template convention); checks button disability and effective visibility including ancestors; focuses rendered, visible `#conn-status` or falls back to visible `#conn-unavailable`
- `_announceConnected(st: object) -> None` — new private helper; independently detects request-keyed status changes and notice additions, including no-submission notices; gives `st.submitting` precedence; first call seeds both baselines without writing; clears the opposite announcer only on a new payload

### Call Path

`cmd_policy_builder` -> `render_policy_builder_html` (inlines `policy-router-builder.html.tmpl`) -> browser-side `renderConnected` -> `_restoreConnectedFocus`, `_announceConnected`

## Status

**Open** | Created: 2026-09-19 | Priority: P2


## Verification Notes

Verdict at time of check: **VALID** (no corrections were needed, so nothing was edited in this pass) — verified 2026-09-19.

- Template anchors match: `renderConnected` (2217), `#conn-review-info`/`#conn-notices`/`#conn-status` (349-351), `#conn-unavailable` (333), `onChange` registration (2327), bootstrap call (2333); no `role`/`aria-live`/`.focus()`/visually-hidden class on the connected outputs.
- `getState()` (core.mjs 3845) has `busy: submitting || review.status === "hashing"` and does not expose `submitting`; `startReview` guards only `hashing` (4403). Both match the proposal's premises.
- Blocking edges: ENH-3510/3511/3513/3514 each list `BUG-3512` in `blocked_by`; no cycles or broken refs. Decisions check, `ll-verify-evidence` (0 findings) and proposal-vs-code trace found no conflicts.
- Graph: provider=`codegraph` freshness=`fresh` (not needed for any verdict).

## Session Log
- `/ll:verify-issues` - 2026-09-19T21:47:29 - `ec33e794-bba7-4e0f-b871-a6a89de1c001.jsonl`
- `/ll:confidence-check` - 2026-09-19T21:39:27 - `a64c7633-3845-4240-ac13-8b9cec728136.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-19T21:30:35 - `6b9c88d3-074c-4681-b7c9-240fc332f147.jsonl`
- `/ll:refine-issue` - 2026-09-19T20:55:40 - `274231e5-4fb2-4b8c-8eff-785a5007e300.jsonl`
- `/ll:format-issue` - 2026-09-19T20:39:00 - `62ea2c42-153a-4077-bc55-dc91a943784a.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Downstream issues ENH-3510, ENH-3511, ENH-3513, ENH-3514 edit the same `renderConnected` block and golden fixture; they are now `blocked_by` this issue. This issue owns `#conn-live`/`#conn-alert` and busy `aria-disabled`; ENH-3513 owns `#live-status`.

**Out of scope** (capture separately): `renderConnected` rebuilds the `#conn-issue` options (`sel.innerHTML = ""`) on every poll emit, which can disrupt an open dropdown during keyboard navigation.
