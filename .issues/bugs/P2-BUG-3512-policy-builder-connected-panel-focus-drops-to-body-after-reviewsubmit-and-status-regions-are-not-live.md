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

- Focus stays on the activated control, or moves to a sensible target (e.g. the status region or the next available action), never `BODY`.
- Review results, `#conn-notices` messages, and delivery-state transitions (accepted, rejected, outcome-unknown) are announced by assistive technology via `role="status"` / `aria-live="polite"` regions (`assertive` / `role="alert"` for rejected).

## Root Cause

- **File**: `scripts/little_loops/templates/policy-router-builder.html.tmpl`
- **Anchor**: `renderConnected(st)`, plus the `#conn-review-info`, `#conn-notices` and `#conn-status` markup in `#connected-panel`
- **Cause**: `renderConnected` sets `disabled` on the focused button and clears/rebuilds `#conn-status` and `#conn-notices` via `innerHTML = ""` on every state change, with no focus management. The three output containers are plain `<p>`, `<ul>` and `<div>` elements with no live-region semantics.

## Proposed Solution

1. Add `role="status"` and `aria-live="polite"` to `#conn-review-info` and `#conn-notices`. Add `role="status"` to `#conn-status`, escalating to `role="alert"` for the `rejected` state.
2. In `renderConnected`, capture `document.activeElement` before disabling controls. If it is a `conn-*` button that is now disabled or hidden, move focus to a sensible target: `#conn-status` (made `tabindex="-1"`) after Submit, and the Review button after Review.
3. Keep the live regions in the DOM permanently and update their text, rather than recreating the containers, so announcements fire.

## Impact

- **Priority**: P2 - keyboard and screen-reader users cannot follow the connected submit flow
- **Effort**: Small - markup attributes plus focus handling in one render function
- **Risk**: Low - additive ARIA attributes and focus moves scoped to the connected panel
- **Breaking Change**: No

## Program Design

### Types

- `busy: bool` — existing submission-controller state field read by `renderConnected`
- `status: str` — existing `review.status` field (`hashing|refused|ready`)

### Signatures

- `renderConnected(st: SubmissionState) -> None` — existing in `policy-router-builder.html.tmpl`; capture `document.activeElement` up front and restore focus after the rebuild
- `restoreConnectedFocus(prev: Element, st: SubmissionState) -> None` — new helper; moves focus to `#conn-status` or the Review button when `prev` was disabled/hidden

### Call Path

`cmd_policy_builder` -> `render_policy_builder_html` (inlines `policy-router-builder.html.tmpl`) -> browser-side `renderConnected` -> `restoreConnectedFocus`

## Status

**Open** | Created: 2026-09-19 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-09-19T20:39:00 - `62ea2c42-153a-4077-bc55-dc91a943784a.jsonl`
